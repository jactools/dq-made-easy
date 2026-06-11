from __future__ import annotations

import base64
from collections import Counter, defaultdict
from collections.abc import Iterable
from datetime import UTC, datetime
import json
import re
from typing import Any
from uuid import uuid4

from rapidfuzz import fuzz

from app.domain.entities.catalog_governance import build_catalog_term_entities


_CATALOG_TERM_STOP_WORDS = {
    'a',
    'an',
    'and',
    'are',
    'as',
    'at',
    'be',
    'been',
    'being',
    'but',
    'by',
    'can',
    'could',
    'did',
    'do',
    'does',
    'done',
    'for',
    'from',
    'had',
    'has',
    'have',
    'if',
    'in',
    'into',
    'is',
    'it',
    'its',
    'least',
    'less',
    'lower',
    'max',
    'maximum',
    'minimum',
    'more',
    'may',
    'might',
    'must',
    'no',
    'not',
    'of',
    'on',
    'or',
    'over',
    'our',
    'percentages',
    'shall',
    'should',
    'than',
    'that',
    'the',
    'their',
    'then',
    'there',
    'these',
    'this',
    'to',
    'under',
    'below',
    'up',
    'upper',
    'was',
    'were',
    'when',
    'where',
    'which',
    'with',
    'within',
    'would',
    'above',
    'at',
    'between',
    'equal',
    'equals',
    'greater',
    'most',
    'maximums',
    'minimums',
    'you',
    'your',
}

_CATALOG_TERM_SEARCH_THRESHOLD = 70.0


def _normalize_catalog_term_search_text(value: Any) -> str:
    tokens = [token for token in re.split(r"[^a-z0-9]+", str(value or "").lower()) if token]
    meaningful_tokens = [
        'percent' if token in {'percent', 'percentage', 'percentages'} else token
        for token in tokens
        if token not in _CATALOG_TERM_STOP_WORDS
    ]
    return " ".join(meaningful_tokens)


def _catalog_term_search_text(row: dict[str, Any]) -> str:
    parts = [str(row.get(field) or "").strip() for field in ("termName", "termKey", "description")]
    return " ".join(part for part in parts if part)


def _catalog_term_search_score(row: dict[str, Any], search: str) -> float:
    normalized_search = _normalize_catalog_term_search_text(search)
    if not normalized_search:
        return 0.0

    normalized_term = _normalize_catalog_term_search_text(_catalog_term_search_text(row))
    if not normalized_term:
        return 0.0

    overlap = set(normalized_search.split()) & set(normalized_term.split())
    score = max(
        float(fuzz.token_set_ratio(normalized_search, normalized_term)),
        float(fuzz.partial_ratio(normalized_search, normalized_term)),
    )
    if overlap:
        score = min(100.0, score + (10.0 * len(overlap)))
    return score


def current_catalog_governance_timestamp() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def build_catalog_term_payloads(rows: Iterable[Any]) -> list[dict[str, Any]]:
    return [term.model_dump(mode="python") for term in build_catalog_term_entities(rows)]


def encode_revalidation_job_id(*, queued: int, triggered_by_term: str, started_at: str) -> str:
    payload = {
        "queued": int(max(0, queued)),
        "triggeredByTerm": str(triggered_by_term or "N/A"),
        "startedAt": str(started_at),
        "token": uuid4().hex[:8],
    }
    raw = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    encoded = base64.urlsafe_b64encode(raw).decode("utf-8").rstrip("=")
    return f"job-{encoded}"


def decode_revalidation_job_id(job_id: str) -> dict[str, Any] | None:
    if not job_id.startswith("job-"):
        return None
    encoded = job_id[4:]
    if not encoded:
        return None
    padding = "=" * ((4 - (len(encoded) % 4)) % 4)
    try:
        raw = base64.urlsafe_b64decode(f"{encoded}{padding}")
        payload = json.loads(raw.decode("utf-8"))
    except Exception:
        return None
    if not isinstance(payload, dict):
        return None
    return payload


def filter_catalog_term_payloads(
    rows: list[dict[str, Any]],
    *,
    domain: str | None = None,
    search: str | None = None,
    match_threshold_pct: float = 70.0,
) -> list[dict[str, Any]]:
    filtered = list(rows)
    if domain:
        filtered = [row for row in filtered if str(row.get("domain") or "").lower() == domain.lower()]
    if search is None:
        return filtered

    normalized_search = _normalize_catalog_term_search_text(search)
    if not normalized_search:
        return []

    threshold = float(match_threshold_pct)
    if threshold < 0:
        threshold = 0.0
    elif threshold > 100:
        threshold = 100.0

    scored_rows: list[tuple[float, str, dict[str, Any]]] = []
    for row in filtered:
        score = _catalog_term_search_score(row, search)
        if score < threshold:
            continue
        scored_row = dict(row)
        scored_row["matchScorePct"] = round(score, 2)
        scored_rows.append((score, str(row.get("termName") or "").lower(), scored_row))

    scored_rows.sort(key=lambda item: (-item[0], item[1]))
    filtered = [row for _, _, row in scored_rows]
    return filtered


def build_catalog_health_payload(*, term_count: int, last_sync: str) -> dict[str, Any]:
    return {
        "status": "healthy",
        "last_sync": last_sync,
        "term_count": term_count,
        "message": "Catalog metadata is available",
    }


def build_catalog_terms_response(*, rows: list[dict[str, Any]], last_synced: str) -> dict[str, Any]:
    return {
        "terms": rows,
        "lastSynced": last_synced,
    }


def build_rule_drift_response(
    *,
    rule_id: str,
    rule_name: str,
    version_id: str,
    version_number: int,
    affected_aliases: list[str],
    drifts: list[dict[str, Any]],
    last_validated_at: str,
    detected_at: str,
) -> dict[str, Any]:
    return {
        "ruleId": rule_id,
        "ruleName": rule_name,
        "ruleVersionId": version_id,
        "versionNumber": version_number,
        "affectedAliases": affected_aliases,
        "drifts": drifts,
        "totalDrifts": len(drifts),
        "needsRevalidation": len(drifts) > 0,
        "lastValidatedAt": last_validated_at,
        "detectedAt": detected_at,
    }


def build_drift_summary_response(
    *,
    total_rules_checked: int,
    affected_rules: list[dict[str, Any]],
) -> dict[str, Any]:
    total_drifts_detected = 0
    critical_drifts = 0
    warning_drifts = 0
    by_drift_type: dict[str, int] = {}
    affected_rule_summaries: list[dict[str, Any]] = []

    for rule in affected_rules:
        drifts = [item for item in rule.get("drifts", []) if isinstance(item, dict)]
        total_drifts = int(rule.get("totalDrifts") or len(drifts))
        total_drifts_detected += total_drifts
        for drift in drifts:
            drift_type = str(drift.get("driftType") or "unknown").strip() or "unknown"
            by_drift_type[drift_type] = by_drift_type.get(drift_type, 0) + 1
            severity = str(drift.get("severity") or "").strip().lower()
            if severity == "critical":
                critical_drifts += 1
            elif severity == "warning":
                warning_drifts += 1

        affected_rule_summaries.append(
            {
                "ruleId": str(rule.get("ruleId") or ""),
                "ruleName": str(rule.get("ruleName") or ""),
                "ruleVersionId": str(rule.get("ruleVersionId") or ""),
                "versionNumber": int(rule.get("versionNumber") or 0),
                "affectedAliases": list(rule.get("affectedAliases") or []),
                "totalDrifts": total_drifts,
                "needsRevalidation": bool(rule.get("needsRevalidation")),
            }
        )

    return {
        "totalRulesChecked": total_rules_checked,
        "rulesWithDrift": len(affected_rules),
        "totalDriftsDetected": total_drifts_detected,
        "criticalDrifts": critical_drifts,
        "warningDrifts": warning_drifts,
        "byDriftType": by_drift_type,
        "affectedRules": affected_rule_summaries,
    }


def build_affected_rules_response(*, term_id: str, affected_rules: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "termId": term_id,
        "affectedRulesCount": len(affected_rules),
        "affectedRules": affected_rules,
    }


def build_revalidation_job_response(
    *,
    job_id: str,
    queued: int,
    triggered_by_term: str,
    started_at: str,
) -> dict[str, Any]:
    return {
        "jobId": job_id,
        "status": "completed",
        "ruleVersionsQueued": queued,
        "triggeredByTerm": triggered_by_term,
        "startedAt": started_at,
    }


def build_revalidation_job_status_response(
    *,
    job_id: str,
    queued: int,
    triggered_by_term: str,
    started_at: str,
) -> dict[str, Any]:
    return {
        "job_id": job_id,
        "status": "completed",
        "progress": "100%",
        "queued": queued,
        "completed": queued,
        "failed": 0,
        "validation_improved": 0,
        "validation_degraded": 0,
        "validation_unchanged": queued,
        "triggered_by_term": triggered_by_term,
        "started_at": started_at,
        "completed_at": started_at,
        "duration_seconds": 0,
        "results": [],
    }


def _build_monitor_schedule_payload(*, scope_kind: str) -> dict[str, Any]:
    if scope_kind == "data_asset":
        return {
            "cron_expression": "0 1 * * *",
            "timezone": "UTC",
            "window_minutes": 1440,
        }
    return {
        "cron_expression": "0 */6 * * *",
        "timezone": "UTC",
        "window_minutes": 360,
    }


def _build_monitor_definition_payload(
    *,
    monitor_id: str,
    scope_kind: str,
    scope_id: str,
    scope_name: str,
    workspace_id: str,
    signals: list[str],
) -> dict[str, Any]:
    return {
        "monitor_id": monitor_id,
        "monitor_type": "scheduled_monitor",
        "scope_kind": scope_kind,
        "scope_id": scope_id,
        "scope_name": scope_name,
        "workspace_id": workspace_id,
        "status": "active",
        "signals": signals,
        "schedule_definition": _build_monitor_schedule_payload(scope_kind=scope_kind),
        "description": f"Scheduled monitor for {scope_name}",
    }


def build_monitor_definition_payloads(
    *,
    data_assets: Iterable[Any],
    data_sets: Iterable[Any],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []

    for asset in data_assets:
        asset_id = str(getattr(asset, "id", "") or "").strip()
        if not asset_id:
            continue
        rows.append(
            _build_monitor_definition_payload(
                monitor_id=f"data_asset-{asset_id}",
                scope_kind="data_asset",
                scope_id=asset_id,
                scope_name=str(getattr(asset, "name", "") or asset_id).strip() or asset_id,
                workspace_id=str(getattr(asset, "workspace_id", "") or "").strip(),
                signals=["freshness", "schema_drift"],
            )
        )

    for data_set in data_sets:
        data_set_id = str(getattr(data_set, "id", "") or "").strip()
        if not data_set_id:
            continue
        rows.append(
            _build_monitor_definition_payload(
                monitor_id=f"source_dataset-{data_set_id}",
                scope_kind="source_dataset",
                scope_id=data_set_id,
                scope_name=str(getattr(data_set, "name", "") or data_set_id).strip() or data_set_id,
                workspace_id=str(getattr(data_set, "workspace_id", "") or "").strip(),
                signals=["volume", "distribution", "null_rate", "freshness"],
            )
        )

    rows.sort(
        key=lambda row: (
            str(row.get("workspace_id") or ""),
            str(row.get("scope_kind") or ""),
            str(row.get("scope_name") or ""),
            str(row.get("monitor_id") or ""),
        )
    )
    return rows


def build_monitor_definitions_response(*, rows: list[dict[str, Any]], last_synced: str) -> dict[str, Any]:
    data_asset_monitor_count = sum(1 for row in rows if str(row.get("scope_kind") or "") == "data_asset")
    source_dataset_monitor_count = sum(1 for row in rows if str(row.get("scope_kind") or "") == "source_dataset")
    workspace_count = len({str(row.get("workspace_id") or "").strip() for row in rows if str(row.get("workspace_id") or "").strip()})
    return {
        "monitor_definitions": rows,
        "summary": {
            "total_monitor_definitions": len(rows),
            "data_asset_monitor_count": data_asset_monitor_count,
            "source_dataset_monitor_count": source_dataset_monitor_count,
            "workspace_count": workspace_count,
        },
        "last_synced": last_synced,
    }


def _anomaly_failure_condition(signal_kind: str, threshold_value: int, threshold_unit: str) -> str:
    if signal_kind == "volume":
        return f"Triggers when row count changes by more than {threshold_value}% relative to baseline"
    if signal_kind == "distribution":
        return f"Triggers when statistical distribution score deviates by more than {threshold_value} points from baseline"
    if signal_kind == "null_rate":
        return f"Triggers when null rate increases by more than {threshold_value} percentage points"
    if signal_kind == "freshness":
        return f"Triggers when data is more than {threshold_value} hours stale (no new rows detected)"
    return f"Triggers when {signal_kind.replace('_', ' ')} exceeds {threshold_value} {threshold_unit}"


def _build_anomaly_monitor_payload(
    *,
    monitor_id: str,
    scope_kind: str,
    scope_id: str,
    scope_name: str,
    workspace_id: str,
    signal_kind: str,
    threshold_kind: str,
    threshold_value: int,
    threshold_unit: str,
    severity: str,
) -> dict[str, Any]:
    return {
        "monitor_id": monitor_id,
        "monitor_type": "anomaly_monitor",
        "scope_kind": scope_kind,
        "scope_id": scope_id,
        "scope_name": scope_name,
        "workspace_id": workspace_id,
        "signal_kind": signal_kind,
        "threshold_kind": threshold_kind,
        "threshold_value": threshold_value,
        "threshold_unit": threshold_unit,
        "severity": severity,
        "status": "active",
        "failure_condition": _anomaly_failure_condition(signal_kind, threshold_value, threshold_unit),
        "description": f"{signal_kind.replace('_', ' ').title()} anomaly monitor for {scope_name}",
    }


def build_monitor_anomaly_payloads(
    *,
    data_assets: Iterable[Any],
    data_sets: Iterable[Any],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []

    anomaly_specs = (
        ("volume", "percentage", 25, "percent", "warning"),
        ("distribution", "score", 15, "points", "warning"),
        ("null_rate", "percentage", 5, "percent", "critical"),
        ("freshness", "hours", 24, "hours", "critical"),
    )

    for asset in data_assets:
        asset_id = str(getattr(asset, "id", "") or "").strip()
        if not asset_id:
            continue
        scope_name = str(getattr(asset, "name", "") or asset_id).strip() or asset_id
        workspace_id = str(getattr(asset, "workspace_id", "") or "").strip()
        for signal_kind, threshold_kind, threshold_value, threshold_unit, severity in anomaly_specs:
            rows.append(
                _build_anomaly_monitor_payload(
                    monitor_id=f"data_asset-{asset_id}-{signal_kind}",
                    scope_kind="data_asset",
                    scope_id=asset_id,
                    scope_name=scope_name,
                    workspace_id=workspace_id,
                    signal_kind=signal_kind,
                    threshold_kind=threshold_kind,
                    threshold_value=threshold_value,
                    threshold_unit=threshold_unit,
                    severity=severity,
                )
            )

    for data_set in data_sets:
        data_set_id = str(getattr(data_set, "id", "") or "").strip()
        if not data_set_id:
            continue
        scope_name = str(getattr(data_set, "name", "") or data_set_id).strip() or data_set_id
        workspace_id = str(getattr(data_set, "workspace_id", "") or "").strip()
        for signal_kind, threshold_kind, threshold_value, threshold_unit, severity in anomaly_specs:
            rows.append(
                _build_anomaly_monitor_payload(
                    monitor_id=f"source_dataset-{data_set_id}-{signal_kind}",
                    scope_kind="source_dataset",
                    scope_id=data_set_id,
                    scope_name=scope_name,
                    workspace_id=workspace_id,
                    signal_kind=signal_kind,
                    threshold_kind=threshold_kind,
                    threshold_value=threshold_value,
                    threshold_unit=threshold_unit,
                    severity=severity,
                )
            )

    rows.sort(
        key=lambda row: (
            str(row.get("workspace_id") or ""),
            str(row.get("scope_kind") or ""),
            str(row.get("scope_name") or ""),
            str(row.get("signal_kind") or ""),
            str(row.get("monitor_id") or ""),
        )
    )
    return rows


def build_monitor_anomalies_response(*, rows: list[dict[str, Any]], last_synced: str) -> dict[str, Any]:
    signal_counts: dict[str, int] = {}
    data_asset_monitor_count = sum(1 for row in rows if str(row.get("scope_kind") or "") == "data_asset")
    source_dataset_monitor_count = sum(1 for row in rows if str(row.get("scope_kind") or "") == "source_dataset")
    workspace_count = len({str(row.get("workspace_id") or "").strip() for row in rows if str(row.get("workspace_id") or "").strip()})

    for row in rows:
        signal_kind = str(row.get("signal_kind") or "unknown").strip() or "unknown"
        signal_counts[signal_kind] = signal_counts.get(signal_kind, 0) + 1

    return {
        "monitor_anomalies": rows,
        "summary": {
            "total_monitor_anomalies": len(rows),
            "data_asset_anomaly_count": data_asset_monitor_count,
            "source_dataset_anomaly_count": source_dataset_monitor_count,
            "workspace_count": workspace_count,
            "signal_counts": signal_counts,
        },
        "last_synced": last_synced,
    }


def _build_drift_monitor_schedule_payload(*, scope_kind: str, drift_kind: str) -> dict[str, Any]:
    if scope_kind == "data_asset":
        if drift_kind == "schema":
            return {"cron_expression": "0 2 * * *", "timezone": "UTC", "window_minutes": 1440}
        if drift_kind == "field_level":
            return {"cron_expression": "0 */12 * * *", "timezone": "UTC", "window_minutes": 720}
        return {"cron_expression": "0 */6 * * *", "timezone": "UTC", "window_minutes": 360}

    if drift_kind == "schema":
        return {"cron_expression": "0 3 * * *", "timezone": "UTC", "window_minutes": 1440}
    if drift_kind == "field_level":
        return {"cron_expression": "0 */12 * * *", "timezone": "UTC", "window_minutes": 720}
    return {"cron_expression": "0 */6 * * *", "timezone": "UTC", "window_minutes": 360}


def _drift_failure_condition(drift_kind: str, comparison_window_days: int) -> str:
    if drift_kind == "schema":
        return f"Triggers when column additions, removals, or type changes are detected within the {comparison_window_days}-day schema baseline"
    if drift_kind == "field_level":
        return f"Triggers when field statistics deviate from the {comparison_window_days}-day baseline profile"
    if drift_kind == "behavioral":
        return f"Triggers when behavioral patterns shift beyond normal ranges in the {comparison_window_days}-day observation window"
    return f"Triggers when {drift_kind.replace('_', ' ')} drift is detected in the {comparison_window_days}-day window"


def _build_drift_monitor_payload(
    *,
    monitor_id: str,
    scope_kind: str,
    scope_id: str,
    scope_name: str,
    workspace_id: str,
    drift_kind: str,
    baseline_strategy: str,
    comparison_window_days: int,
    severity: str,
) -> dict[str, Any]:
    return {
        "monitor_id": monitor_id,
        "monitor_type": "drift_monitor",
        "scope_kind": scope_kind,
        "scope_id": scope_id,
        "scope_name": scope_name,
        "workspace_id": workspace_id,
        "drift_kind": drift_kind,
        "baseline_strategy": baseline_strategy,
        "comparison_window_days": comparison_window_days,
        "severity": severity,
        "status": "active",
        "failure_condition": _drift_failure_condition(drift_kind, comparison_window_days),
        "schedule_definition": _build_drift_monitor_schedule_payload(scope_kind=scope_kind, drift_kind=drift_kind),
        "description": f"{drift_kind.replace('_', ' ').title()} drift monitor for {scope_name}",
    }


def build_monitor_drift_payloads(
    *,
    data_assets: Iterable[Any],
    data_sets: Iterable[Any],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []

    drift_specs = (
        ("schema", "schema_signature", 7, "critical"),
        ("field_level", "field_profile", 14, "high"),
        ("behavioral", "behavior_pattern", 30, "warning"),
    )

    for asset in data_assets:
        asset_id = str(getattr(asset, "id", "") or "").strip()
        if not asset_id:
            continue
        scope_name = str(getattr(asset, "name", "") or asset_id).strip() or asset_id
        workspace_id = str(getattr(asset, "workspace_id", "") or "").strip()
        for drift_kind, baseline_strategy, comparison_window_days, severity in drift_specs:
            rows.append(
                _build_drift_monitor_payload(
                    monitor_id=f"data_asset-{asset_id}-{drift_kind}",
                    scope_kind="data_asset",
                    scope_id=asset_id,
                    scope_name=scope_name,
                    workspace_id=workspace_id,
                    drift_kind=drift_kind,
                    baseline_strategy=baseline_strategy,
                    comparison_window_days=comparison_window_days,
                    severity=severity,
                )
            )

    for data_set in data_sets:
        data_set_id = str(getattr(data_set, "id", "") or "").strip()
        if not data_set_id:
            continue
        scope_name = str(getattr(data_set, "name", "") or data_set_id).strip() or data_set_id
        workspace_id = str(getattr(data_set, "workspace_id", "") or "").strip()
        for drift_kind, baseline_strategy, comparison_window_days, severity in drift_specs:
            rows.append(
                _build_drift_monitor_payload(
                    monitor_id=f"source_dataset-{data_set_id}-{drift_kind}",
                    scope_kind="source_dataset",
                    scope_id=data_set_id,
                    scope_name=scope_name,
                    workspace_id=workspace_id,
                    drift_kind=drift_kind,
                    baseline_strategy=baseline_strategy,
                    comparison_window_days=comparison_window_days,
                    severity=severity,
                )
            )

    rows.sort(
        key=lambda row: (
            str(row.get("workspace_id") or ""),
            str(row.get("scope_kind") or ""),
            str(row.get("scope_name") or ""),
            str(row.get("drift_kind") or ""),
            str(row.get("monitor_id") or ""),
        )
    )
    return rows


def build_monitor_drifts_response(*, rows: list[dict[str, Any]], last_synced: str) -> dict[str, Any]:
    drift_counts: dict[str, int] = {}
    data_asset_monitor_count = sum(1 for row in rows if str(row.get("scope_kind") or "") == "data_asset")
    source_dataset_monitor_count = sum(1 for row in rows if str(row.get("scope_kind") or "") == "source_dataset")
    workspace_count = len({str(row.get("workspace_id") or "").strip() for row in rows if str(row.get("workspace_id") or "").strip()})

    for row in rows:
        drift_kind = str(row.get("drift_kind") or "unknown").strip() or "unknown"
        drift_counts[drift_kind] = drift_counts.get(drift_kind, 0) + 1

    return {
        "monitor_drifts": rows,
        "summary": {
            "total_monitor_drifts": len(rows),
            "data_asset_drift_count": data_asset_monitor_count,
            "source_dataset_drift_count": source_dataset_monitor_count,
            "workspace_count": workspace_count,
            "drift_counts": drift_counts,
        },
        "last_synced": last_synced,
    }


_ROOT_CAUSE_SOURCE_KEYWORDS = {
    "column",
    "distribution",
    "field",
    "format",
    "missing",
    "null",
    "profile",
    "schema",
    "shape",
    "source",
    "value",
    "volume",
}

_MONITOR_NOTIFICATION_CATEGORIES = ["anomaly", "drift", "root_cause"]
_MONITOR_NOTIFICATION_CHANNELS = ["email", "in_app", "teams"]


def _unique_text_values(values: list[str]) -> list[str]:
    unique_values: list[str] = []
    for value in values:
        normalized = str(value or "").strip()
        if normalized and normalized not in unique_values:
            unique_values.append(normalized)
    return unique_values


def _build_monitor_notification_preference_row(
    *,
    workspace_id: str,
    enabled: bool = False,
    categories: list[str] | None = None,
    channels: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "workspace_id": workspace_id,
        "enabled": bool(enabled),
        "categories": _unique_text_values(list(categories or [])),
        "channels": _unique_text_values(list(channels or [])),
    }


def build_monitor_notification_preferences_response(
    *,
    accessible_workspace_ids: list[str],
    rows: list[dict[str, Any]],
    last_synced: str,
) -> dict[str, Any]:
    row_by_workspace_id = {
        str(row.get("workspace_id") or "").strip(): row
        for row in rows
        if str(row.get("workspace_id") or "").strip()
    }
    preferences = [
        _build_monitor_notification_preference_row(
            workspace_id=workspace_id,
            enabled=bool(row.get("enabled", False)),
            categories=[str(item) for item in list(row.get("categories") or [])],
            channels=[str(item) for item in list(row.get("channels") or [])],
        )
        for workspace_id in accessible_workspace_ids
        for row in [row_by_workspace_id.get(workspace_id, {})]
    ]

    return {
        "accessible_workspace_ids": accessible_workspace_ids,
        "available_categories": list(_MONITOR_NOTIFICATION_CATEGORIES),
        "available_channels": list(_MONITOR_NOTIFICATION_CHANNELS),
        "monitor_notification_preferences": preferences,
        "summary": {
            "workspace_count": len(accessible_workspace_ids),
            "workspace_preference_count": len(preferences),
            "category_count": len(_MONITOR_NOTIFICATION_CATEGORIES),
        },
        "last_synced": last_synced,
    }
_ROOT_CAUSE_RULE_KEYWORDS = {
    "check",
    "constraint",
    "policy",
    "rule",
    "threshold",
    "validation",
}
_ROOT_CAUSE_UPSTREAM_KEYWORDS = {
    "arrival",
    "delay",
    "delivery",
    "freshness",
    "ingest",
    "lag",
    "pipeline",
    "timeout",
    "upstream",
}


def _classify_root_cause_group(reason_code: str) -> str:
    tokens = {token for token in re.split(r"[^a-z0-9]+", reason_code.lower()) if token}
    if tokens & _ROOT_CAUSE_SOURCE_KEYWORDS:
        return "source_change"
    if tokens & _ROOT_CAUSE_RULE_KEYWORDS:
        return "rule_change"
    if tokens & _ROOT_CAUSE_UPSTREAM_KEYWORDS:
        return "upstream_event"
    return "unclassified"


def _root_cause_confidence_band(*, share: float) -> str:
    if share >= 0.5:
        return "high"
    if share >= 0.25:
        return "medium"
    return "low"


def build_monitor_root_cause_response(
    *,
    data_object_version_id: str,
    lookback_amount: int,
    lookback_unit: str,
    analytics: Any,
    delivery_id: str | None,
    execution_plan_id: str | None,
    rule_version_id: str | None,
    suite_id: str | None,
    last_synced: str,
) -> dict[str, Any]:
    total_failed_records = int(getattr(analytics, "totalFailedRecords", 0) or 0)
    runs_with_failures = int(getattr(analytics, "runsWithFailures", 0) or 0)
    top_rules = list(getattr(analytics, "topRules", []) or [])
    top_data_objects = list(getattr(analytics, "topDataObjects", []) or [])
    reason_rows = list(getattr(analytics, "topReasons", []) or [])
    reason_trend_rows = list(getattr(analytics, "reasonTrendBuckets", []) or [])

    cause_group_failed_records: Counter[str] = Counter()
    cause_group_reason_codes: dict[str, set[str]] = defaultdict(set)
    cause_group_bucket_totals: dict[str, Counter[str]] = defaultdict(Counter)

    for row in reason_rows:
        reason_code = str(getattr(row, "reasonCode", None) or getattr(row, "reason_code", None) or "").strip()
        group = _classify_root_cause_group(reason_code)
        total = int(getattr(row, "total", 0) or 0)
        if total < 0:
            total = 0
        cause_group_failed_records[group] += total
        if reason_code:
            cause_group_reason_codes[group].add(reason_code)

    for row in reason_trend_rows:
        reason_code = str(getattr(row, "reasonCode", None) or getattr(row, "reason_code", None) or "").strip()
        bucket_start = str(getattr(row, "bucketStart", None) or getattr(row, "bucket_start", None) or "").strip()
        if not reason_code or not bucket_start:
            continue
        group = _classify_root_cause_group(reason_code)
        total = int(getattr(row, "total", 0) or 0)
        if total < 0:
            total = 0
        cause_group_bucket_totals[group][bucket_start] += total

    likely_causes: list[dict[str, Any]] = []
    correlated_changes: list[dict[str, Any]] = []
    ordered_groups = sorted(
        {group for group, total in cause_group_failed_records.items() if total > 0} | {group for group, buckets in cause_group_bucket_totals.items() if buckets},
        key=lambda group: (-cause_group_failed_records.get(group, 0), group),
    )

    for group in ordered_groups:
        bucket_totals = cause_group_bucket_totals.get(group, Counter())
        ordered_buckets = sorted(bucket_totals.items(), key=lambda item: item[0])
        bucket_count = len(ordered_buckets)
        first_total = int(ordered_buckets[0][1]) if ordered_buckets else 0
        latest_total = int(ordered_buckets[-1][1]) if ordered_buckets else 0
        net_change = latest_total - first_total
        trend_direction = "flat"
        if net_change > 0:
            trend_direction = "up"
        elif net_change < 0:
            trend_direction = "down"
        failed_record_count = int(cause_group_failed_records.get(group, 0) or 0)
        share = (failed_record_count / total_failed_records) if total_failed_records else 0.0

        likely_causes.append(
            {
                "cause_group": group,
                "failed_record_count": failed_record_count,
                "reason_variant_count": len(cause_group_reason_codes.get(group, set())),
                "confidence_band": _root_cause_confidence_band(share=share),
            }
        )
        correlated_changes.append(
            {
                "cause_group": group,
                "trend_direction": trend_direction,
                "net_change": net_change,
                "bucket_count": bucket_count,
                "evidence_weight": failed_record_count,
            }
        )

    return {
        "scope": {
            "data_object_version_id": data_object_version_id,
            "delivery_id": delivery_id,
            "execution_plan_id": execution_plan_id,
            "rule_version_id": rule_version_id,
            "suite_id": suite_id,
            "lookback_amount": lookback_amount,
            "lookback_unit": lookback_unit,
        },
        "summary": {
            "total_failed_records": total_failed_records,
            "runs_with_failures": runs_with_failures,
            "affected_rule_count": len(top_rules),
            "affected_data_object_version_count": len(top_data_objects),
            "cause_group_count": len(likely_causes),
            "correlated_change_count": len(correlated_changes),
            "trend_bucket_count": len(list(getattr(analytics, "trendBuckets", []) or [])),
        },
        "likely_causes": likely_causes,
        "correlated_changes": correlated_changes,
        "last_synced": last_synced,
    }


def build_monitor_schedule_response(
    schedule: dict,
    last_synced: str,
) -> dict:
    """Build a response payload for a single monitor schedule looked up by scope."""
    return {
        "monitor_schedule": build_monitor_schedules_response([schedule], last_synced)["monitor_schedules"][0],
        "last_synced": last_synced,
    }


def build_monitor_schedules_response(
    schedules: list[dict],
    last_synced: str,
) -> dict:
    """Build a response payload for monitor schedule list or single-save."""
    result: list[dict] = []
    for s in schedules:
        result.append(
            {
                "id": str(s.get("id") or ""),
                "scope_kind": str(s.get("scope_kind") or ""),
                "scope_id": str(s.get("scope_id") or ""),
                "workspace_id": str(s.get("workspace_id") or ""),
                "monitor_type": str(s.get("monitor_type") or "scheduled_monitor"),
                "cron_expression": str(s.get("cron_expression") or ""),
                "timezone": str(s.get("timezone") or "UTC"),
                "window_minutes": int(s.get("window_minutes") or 1440),
                "enabled": bool(s.get("enabled", True)),
                "signals": list(s.get("signals") or []),
                "created_by": s.get("created_by"),
                "created_at": s.get("created_at"),
                "updated_by": s.get("updated_by"),
                "updated_at": s.get("updated_at"),
            }
        )
    return {
        "monitor_schedules": result,
        "last_synced": last_synced,
    }
