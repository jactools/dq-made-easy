from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from app.domain.entities import DqResultEventEntity
from app.domain.entities import DqResultScoreDimensionEntity
from app.domain.interfaces import DqResultEventRepository


@dataclass(slots=True)
class DqResultDriftQuery:
    lookback_amount: int = 24
    lookback_unit: str = "hours"
    status: str | None = None
    rule_id: str | None = None
    dataset_id: str | None = None
    domain_id: str | None = None
    data_product_id: str | None = None


def _normalize_text(value: Any) -> str:
    return str(value or "").strip()


def _normalize_key(value: Any) -> str | None:
    normalized = _normalize_text(value)
    return normalized or None


def _lookback_delta(*, lookback_amount: int, lookback_unit: str) -> timedelta:
    return timedelta(hours=lookback_amount) if lookback_unit == "hours" else timedelta(days=lookback_amount)


def _parse_iso_datetime(value: str | None) -> datetime | None:
    if value is None:
        return None
    payload = str(value).strip()
    if not payload:
        return None
    return datetime.fromisoformat(payload.replace("Z", "+00:00"))


def _event_observed_at(event: DqResultEventEntity) -> datetime | None:
    return _parse_iso_datetime(event.runOutcome.observedAt) or _parse_iso_datetime(event.emittedAt)


def _event_scope_key(event: DqResultEventEntity) -> tuple[str | None, str | None, str | None, str | None]:
    dataset_id = _normalize_key(event.dataset.id)
    rule_id = _normalize_key(event.rule.id)
    domain_id = _normalize_key(event.domain.id if event.domain is not None else None)
    data_product_id = _normalize_key(event.dataset.dataProductId)
    return rule_id, dataset_id, domain_id, data_product_id


def _dimension_names(event: DqResultEventEntity) -> tuple[str, ...]:
    return tuple(sorted(_normalize_text(item.name).casefold() for item in event.scoreDimensions if _normalize_text(item.name)))


def _dimension_value(event: DqResultEventEntity, *name_fragments: str) -> float | int | None:
    fragments = tuple(fragment.casefold() for fragment in name_fragments)
    for dimension in event.scoreDimensions:
        normalized_name = _normalize_text(dimension.name).casefold()
        if any(fragment in normalized_name for fragment in fragments):
            if isinstance(dimension.value, (int, float)):
                return dimension.value
            if isinstance(dimension.maximum, (int, float)) and isinstance(dimension.value, (int, float)):
                return dimension.value
    return None


def _total_count(event: DqResultEventEntity) -> int | None:
    if isinstance(event.runOutcome.totalCount, int) and event.runOutcome.totalCount >= 0:
        return event.runOutcome.totalCount
    valid_count = event.runOutcome.validCount if isinstance(event.runOutcome.validCount, int) else None
    invalid_count = event.runOutcome.invalidCount if isinstance(event.runOutcome.invalidCount, int) else None
    if valid_count is None and invalid_count is None:
        return None
    return int((valid_count or 0) + (invalid_count or 0))


def _null_rate(event: DqResultEventEntity) -> float | None:
    null_rate_value = _dimension_value(event, "null_rate", "null rate")
    if null_rate_value is not None:
        return float(null_rate_value)

    completeness_value = _dimension_value(event, "completeness")
    if completeness_value is not None:
        return max(0.0, 100.0 - float(completeness_value))

    total_count = _total_count(event)
    invalid_count = event.runOutcome.invalidCount if isinstance(event.runOutcome.invalidCount, int) else None
    if total_count is None or invalid_count is None or total_count <= 0:
        return None
    return round((invalid_count / total_count) * 100.0, 2)


def _distribution_score(event: DqResultEventEntity) -> float | None:
    value = _dimension_value(event, "distribution", "entropy", "skew", "shape", "quantile", "histogram")
    return float(value) if value is not None else None


def _mean(values: list[float]) -> float | None:
    if not values:
        return None
    return sum(values) / len(values)


def _severity_for_delta(*, detector_type: str, delta: float | int) -> str:
    absolute_delta = abs(float(delta))
    if detector_type == "schema_change":
        return "critical"
    if detector_type == "null_rate_shift":
        return "critical" if absolute_delta >= 10 else "warning"
    if detector_type == "distribution_change":
        return "critical" if absolute_delta >= 30 else "warning"
    if detector_type == "volume_anomaly":
        return "critical" if absolute_delta >= 50 else "warning"
    return "warning"


def _build_detection(
    *,
    detector_type: str,
    severity: str,
    scope_key: tuple[str | None, str | None, str | None, str | None],
    observed_at: datetime,
    baseline_value: float | int | None,
    current_value: float | int | None,
    delta: float | int | None,
    threshold: float | int | None,
    message: str,
    evidence: dict[str, Any],
) -> dict[str, Any]:
    rule_id, dataset_id, domain_id, data_product_id = scope_key
    return {
        "detector_type": detector_type,
        "severity": severity,
        "scope": {
            "rule_id": rule_id,
            "dataset_id": dataset_id,
            "domain_id": domain_id,
            "data_product_id": data_product_id,
        },
        "observed_at": observed_at.isoformat(),
        "baseline_value": baseline_value,
        "current_value": current_value,
        "delta": delta,
        "threshold": threshold,
        "message": message,
        "evidence": evidence,
    }


async def get_dq_result_drift_summary(
    *,
    query: DqResultDriftQuery,
    repository: DqResultEventRepository,
) -> dict[str, Any]:
    now = datetime.now(UTC)
    lookback_after = now - _lookback_delta(lookback_amount=max(1, int(query.lookback_amount or 24)), lookback_unit=query.lookback_unit)

    events = await repository.list_result_events(
        rule_id=query.rule_id,
        dataset_id=query.dataset_id,
        domain_id=query.domain_id,
        data_product_id=query.data_product_id,
        status=query.status,
        emitted_after=lookback_after.isoformat(),
        limit=500,
    )
    grouped_events: dict[tuple[str | None, str | None, str | None, str | None], list[DqResultEventEntity]] = defaultdict(list)
    for event in events:
        grouped_events[_event_scope_key(event)].append(event)

    drift_rows: list[dict[str, Any]] = []
    for scope_key, scope_events in grouped_events.items():
        ordered_events = sorted(scope_events, key=lambda event: _event_observed_at(event) or datetime.min.replace(tzinfo=UTC))
        if len(ordered_events) < 2:
            continue

        baseline_events = ordered_events[:-1]
        latest_event = ordered_events[-1]
        latest_observed_at = _event_observed_at(latest_event) or now
        latest_signature = _dimension_names(latest_event)
        baseline_signatures = Counter(_dimension_names(event) for event in baseline_events)
        baseline_signature = baseline_signatures.most_common(1)[0][0] if baseline_signatures else ()
        if latest_signature != baseline_signature:
            drift_rows.append(
                _build_detection(
                    detector_type="schema_change",
                    severity="critical",
                    scope_key=scope_key,
                    observed_at=latest_observed_at,
                    baseline_value=len(baseline_signature),
                    current_value=len(latest_signature),
                    delta=len(latest_signature) - len(baseline_signature),
                    threshold=0,
                    message="The result score-dimension schema changed compared with the prior baseline.",
                    evidence={
                        "baseline_dimensions": list(baseline_signature),
                        "current_dimensions": list(latest_signature),
                        "baseline_event_count": len(baseline_events),
                    },
                )
            )

        baseline_null_rates = [value for value in (_null_rate(event) for event in baseline_events) if value is not None]
        latest_null_rate = _null_rate(latest_event)
        baseline_null_rate = _mean(baseline_null_rates)
        if latest_null_rate is not None and baseline_null_rate is not None:
            null_rate_delta = round(latest_null_rate - baseline_null_rate, 2)
            if null_rate_delta >= 5:
                drift_rows.append(
                    _build_detection(
                        detector_type="null_rate_shift",
                        severity=_severity_for_delta(detector_type="null_rate_shift", delta=null_rate_delta),
                        scope_key=scope_key,
                        observed_at=latest_observed_at,
                        baseline_value=round(baseline_null_rate, 2),
                        current_value=round(latest_null_rate, 2),
                        delta=null_rate_delta,
                        threshold=5,
                        message="Null-rate increased beyond the baseline tolerance.",
                        evidence={
                            "baseline_null_rates": [round(value, 2) for value in baseline_null_rates],
                            "latest_invalid_count": latest_event.runOutcome.invalidCount,
                            "latest_total_count": _total_count(latest_event),
                        },
                    )
                )

        baseline_distribution_values = [value for value in (_distribution_score(event) for event in baseline_events) if value is not None]
        latest_distribution_value = _distribution_score(latest_event)
        baseline_distribution_value = _mean([float(value) for value in baseline_distribution_values])
        if latest_distribution_value is not None and baseline_distribution_value is not None:
            distribution_delta = round(latest_distribution_value - baseline_distribution_value, 2)
            if abs(distribution_delta) >= 15:
                drift_rows.append(
                    _build_detection(
                        detector_type="distribution_change",
                        severity=_severity_for_delta(detector_type="distribution_change", delta=distribution_delta),
                        scope_key=scope_key,
                        observed_at=latest_observed_at,
                        baseline_value=round(baseline_distribution_value, 2),
                        current_value=round(latest_distribution_value, 2),
                        delta=distribution_delta,
                        threshold=15,
                        message="A tracked distribution score moved materially away from baseline.",
                        evidence={
                            "baseline_distribution_scores": [round(float(value), 2) for value in baseline_distribution_values],
                            "latest_score_dimensions": [dimension.name for dimension in latest_event.scoreDimensions],
                        },
                    )
                )

        baseline_total_counts = [value for value in (_total_count(event) for event in baseline_events) if value is not None]
        latest_total_count = _total_count(latest_event)
        baseline_total_count = _mean([float(value) for value in baseline_total_counts])
        if latest_total_count is not None and baseline_total_count is not None and baseline_total_count > 0:
            volume_delta = round(((latest_total_count - baseline_total_count) / baseline_total_count) * 100.0, 2)
            if abs(volume_delta) >= 25:
                drift_rows.append(
                    _build_detection(
                        detector_type="volume_anomaly",
                        severity=_severity_for_delta(detector_type="volume_anomaly", delta=volume_delta),
                        scope_key=scope_key,
                        observed_at=latest_observed_at,
                        baseline_value=round(baseline_total_count, 2),
                        current_value=latest_total_count,
                        delta=volume_delta,
                        threshold=25,
                        message="Result volume changed materially relative to the prior baseline.",
                        evidence={
                            "baseline_total_counts": baseline_total_counts,
                            "latest_total_count": latest_total_count,
                        },
                    )
                )

    drift_rows.sort(
        key=lambda row: (
            {"critical": 0, "warning": 1}.get(str(row.get("severity") or "warning"), 2),
            str(row.get("observed_at") or ""),
            str(row.get("detector_type") or ""),
        )
    )

    detections_by_type = Counter(str(row.get("detector_type") or "unknown") for row in drift_rows)
    detections_by_severity = Counter(str(row.get("severity") or "warning") for row in drift_rows)
    latest_observed_at = max((_event_observed_at(event) for event in events if _event_observed_at(event) is not None), default=None)

    return {
        "lookback_amount": int(query.lookback_amount or 24),
        "lookback_unit": query.lookback_unit,
        "total_events": len(events),
        "scoped_groups": len(grouped_events),
        "total_detections": len(drift_rows),
        "detections_by_type": dict(sorted(detections_by_type.items())),
        "detections_by_severity": dict(sorted(detections_by_severity.items())),
        "latest_observed_at": latest_observed_at.isoformat() if latest_observed_at is not None else None,
        "drifts": drift_rows,
    }