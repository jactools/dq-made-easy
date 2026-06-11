from __future__ import annotations

import asyncio
from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from app.domain.entities import GxExecutionRunEntity
from app.domain.entities import GxExecutionExceptionAnalyticsEntity
from app.domain.entities import GxExecutionRunCountEntity
from app.domain.entities import GxExecutionRunSummaryEntity
from app.domain.entities import GxExecutionRunStatisticsEntity
from app.domain.entities import build_gx_execution_contract_entity
from app.domain.entities import build_gx_execution_exception_analytics_entity
from app.domain.entities import build_gx_execution_result_item_entities
from app.domain.entities import build_gx_execution_result_summary_entity
from app.domain.entities.gx_execution_run import build_gx_execution_run_summary_entity
from app.domain.interfaces import DataCatalogRepository
from app.domain.interfaces import ExceptionReasonAnalyticsProjectionRepository
from app.domain.interfaces import GxExecutionRunRepository
from app.domain.interfaces import GxRunPlanRepository
from app.domain.interfaces import GxSuiteRepository
from app.domain.interfaces import RulesRepository


@dataclass(slots=True)
class ListGxExecutionRunsQuery:
    lookback_amount: int = 24
    lookback_unit: str = "hours"
    status: str | None = None
    rule_name: str | None = None
    owner: str | None = None
    domain: str | None = None
    severity: str | None = None
    data_object_name: str | None = None
    search: str | None = None
    limit: int | None = 25
    data_product_id: str | None = None
    dataset_id: str | None = None
    data_object_id: str | None = None
    data_object_version_id: str | None = None
    delivery_id: str | None = None
    workspace_id: str | None = None
    run_plan_id: str | None = None


@dataclass(slots=True)
class GxExecutionRunStatisticsQuery:
    lookback_amount: int = 24
    lookback_unit: str = "hours"
    recent_limit: int = 10
    status: str | None = None
    rule_name: str | None = None
    owner: str | None = None
    domain: str | None = None
    severity: str | None = None
    data_object_name: str | None = None
    search: str | None = None
    data_product_id: str | None = None
    dataset_id: str | None = None
    data_object_id: str | None = None
    data_object_version_id: str | None = None
    delivery_id: str | None = None
    workspace_id: str | None = None
    run_plan_id: str | None = None


@dataclass(slots=True)
class GxExecutionExceptionAnalyticsQuery:
    lookback_amount: int = 24
    lookback_unit: str = "hours"
    status: str | None = None
    rule_name: str | None = None
    data_object_name: str | None = None
    search: str | None = None
    reason_code: str | None = None
    suite_id: str | None = None
    data_product_id: str | None = None
    dataset_id: str | None = None
    data_object_id: str | None = None
    data_object_version_id: str | None = None
    delivery_id: str | None = None
    rule_version_id: str | None = None
    workspace_id: str | None = None


@dataclass(slots=True)
class ScopedGxExecutionExceptionAnalyticsQuery:
    lookback_amount: int = 24
    lookback_unit: str = "hours"
    status: str | None = None
    rule_name: str | None = None
    data_object_name: str | None = None
    search: str | None = None
    reason_code: str | None = None
    delivery_id: str | None = None
    execution_plan_id: str | None = None
    suite_id: str | None = None
    data_object_version_id: str | None = None
    rule_version_id: str | None = None


@dataclass(slots=True)
class ScopedGxExecutionExceptionAnalyticsResult:
    analytics: GxExecutionExceptionAnalyticsEntity
    execution_run_ids: list[str]
    data_object_version_ids: list[str]


def _normalize_search_term(value: str | None) -> str:
    return str(value or "").strip().casefold()


def _normalize_scope_term(value: str | None) -> str:
    return str(value or "").strip()


def _extract_run_plan_id(run: GxExecutionRunEntity) -> str | None:
    handoff_payload = getattr(run, "handoffPayload", None)
    candidate = _optional_payload_text(handoff_payload, "run_plan_id", "runPlanId")
    if candidate:
        return candidate

    status_details = getattr(run, "statusDetails", None)
    candidate = _optional_payload_text(status_details, "run_plan_id", "runPlanId")
    if candidate:
        return candidate

    return _optional_payload_text(run, "runPlanId", "run_plan_id")


def _extract_run_delivery_id(run: GxExecutionRunEntity) -> str | None:
    execution_contract = _extract_run_execution_contract(run)
    if execution_contract is not None:
        normalized_delivery_id = str(execution_contract.resolvedDataDeliveryId or "").strip()
        if normalized_delivery_id:
            return normalized_delivery_id

    handoff_payload = getattr(run, "handoffPayload", None)
    delivery_snapshot = getattr(handoff_payload, "deliverySnapshot", None)
    delivery_id = _optional_payload_text(
        delivery_snapshot,
        "resolved_data_delivery_id",
        "resolvedDataDeliveryId",
    )
    if delivery_id:
        return delivery_id
    delivery_id = _optional_payload_text(handoff_payload, "resolved_data_delivery_id", "resolvedDataDeliveryId")
    if delivery_id:
        return delivery_id

    return _optional_payload_text(
        run,
        "resolvedDataDeliveryId",
        "resolved_data_delivery_id",
        "deliveryId",
        "delivery_id",
    )


def _extract_run_suite_refs(run: GxExecutionRunEntity) -> set[tuple[str, int]]:
    refs: set[tuple[str, int]] = set()
    if str(run.suiteId or "").strip() and run.suiteVersion is not None:
        refs.add((str(run.suiteId or "").strip(), int(run.suiteVersion)))

    handoff_payload = getattr(run, "handoffPayload", None)
    raw_suite_refs = getattr(handoff_payload, "suiteRefs", None)
    if isinstance(raw_suite_refs, list):
        for entry in raw_suite_refs:
            if not isinstance(entry, Mapping):
                continue
            suite_id = str(entry.get("suiteId") or entry.get("suite_id") or "").strip()
            suite_version_value = entry.get("suiteVersion") if entry.get("suiteVersion") is not None else entry.get("suite_version")
            try:
                suite_version = int(suite_version_value) if suite_version_value is not None else None
            except (TypeError, ValueError):
                suite_version = None
            if suite_id and suite_version is not None:
                refs.add((suite_id, suite_version))

    return refs


def _run_matches_scope(
    run: GxExecutionRunEntity,
    *,
    workspace_run_plan_ids: set[str] | None = None,
    run_plan_id: str | None = None,
    suite_keys: set[tuple[str, int]] | None = None,
    delivery_id: str | None = None,
) -> bool:
    if workspace_run_plan_ids is not None:
        workspace_candidate_run_plan_id = _extract_run_execution_plan_id(run)
        if not workspace_candidate_run_plan_id or workspace_candidate_run_plan_id not in workspace_run_plan_ids:
            return False

    normalized_run_plan_id = _normalize_scope_term(run_plan_id)
    if normalized_run_plan_id:
        candidate_run_plan_id = _extract_run_execution_plan_id(run)
        if candidate_run_plan_id != normalized_run_plan_id:
            return False

    normalized_delivery_id = _normalize_scope_term(delivery_id)
    if normalized_delivery_id:
        return _extract_run_delivery_id(run) == normalized_delivery_id

    if suite_keys:
        run_suite_refs = _extract_run_suite_refs(run)
        if not run_suite_refs:
            return False
        return bool(run_suite_refs.intersection(suite_keys))

    return True


async def _resolve_workspace_run_plan_ids(
    *,
    workspace_id: str | None,
    repository: GxRunPlanRepository,
) -> set[str] | None:
    normalized_workspace_id = _normalize_scope_term(workspace_id)
    if not normalized_workspace_id:
        return None

    run_plans = await repository.list_plans(workspace_id=normalized_workspace_id)
    return {
        str(getattr(run_plan, "runPlanId", None) or "").strip()
        for run_plan in run_plans
        if str(getattr(run_plan, "runPlanId", None) or "").strip()
    }


async def _resolve_suite_keys_for_scope(
    *,
    data_product_id: str | None,
    dataset_id: str | None,
    data_object_id: str | None,
    data_object_version_id: str | None,
    repository: GxSuiteRepository,
) -> set[tuple[str, int]]:
    normalized_data_product_id = _normalize_scope_term(data_product_id)
    normalized_dataset_id = _normalize_scope_term(dataset_id)
    normalized_data_object_id = _normalize_scope_term(data_object_id)
    normalized_data_object_version_id = _normalize_scope_term(data_object_version_id)
    if not any((normalized_data_product_id, normalized_dataset_id, normalized_data_object_id, normalized_data_object_version_id)):
        return set()

    suite_keys: set[tuple[str, int]] = set()
    for status in ("active", "deprecated", "disabled"):
        suite_rows = await repository.list_suites(
            data_object_id=normalized_data_object_id or None,
            data_object_version_id=normalized_data_object_version_id or None,
            dataset_id=normalized_dataset_id or None,
            data_product_id=normalized_data_product_id or None,
            status=status,
            latest_only=False,
        )
        for row in suite_rows:
            suite_id = str(getattr(row, "suiteId", "") or "").strip()
            suite_version = getattr(row, "suiteVersion", None)
            if not suite_id or suite_version is None:
                continue
            try:
                suite_version_number = int(suite_version)
            except (TypeError, ValueError):
                continue
            suite_keys.add((suite_id, suite_version_number))

    return suite_keys


def _optional_payload_text(value: Any, *keys: str) -> str | None:
    candidates: list[Any] = []
    if isinstance(value, Mapping):
        candidates.append(value)
    model_extra = getattr(value, "model_extra", None)
    if isinstance(model_extra, Mapping):
        candidates.append(model_extra)

    for candidate in candidates:
        for key in keys:
            normalized = str(candidate.get(key) or "").strip()
            if normalized:
                return normalized

    for key in keys:
        attr_value = getattr(value, key, None)
        normalized = str(attr_value or "").strip()
        if normalized:
            return normalized

    return None


def _extract_run_execution_contract(run: GxExecutionRunEntity):
    return build_gx_execution_contract_entity(run.executionContract)


def _extract_run_delivery_id(run: GxExecutionRunEntity) -> str | None:
    execution_contract = _extract_run_execution_contract(run)
    if execution_contract is not None:
        normalized_delivery_id = str(execution_contract.resolvedDataDeliveryId or "").strip()
        if normalized_delivery_id:
            return normalized_delivery_id

    handoff_payload = getattr(run, "handoffPayload", None)
    delivery_snapshot = getattr(handoff_payload, "deliverySnapshot", None)
    delivery_id = _optional_payload_text(
        delivery_snapshot,
        "resolved_data_delivery_id",
        "resolvedDataDeliveryId",
    )
    if delivery_id:
        return delivery_id
    delivery_id = _optional_payload_text(handoff_payload, "resolved_data_delivery_id", "resolvedDataDeliveryId")
    if delivery_id:
        return delivery_id

    return _optional_payload_text(
        run,
        "resolvedDataDeliveryId",
        "resolved_data_delivery_id",
        "deliveryId",
        "delivery_id",
    )


def _extract_run_execution_plan_id(run: GxExecutionRunEntity) -> str | None:
    handoff_payload = getattr(run, "handoffPayload", None)
    run_plan_id = _optional_payload_text(handoff_payload, "run_plan_id", "runPlanId")
    if run_plan_id:
        return run_plan_id

    status_details = getattr(run, "statusDetails", None)
    run_plan_id = _optional_payload_text(status_details, "run_plan_id", "runPlanId")
    if run_plan_id:
        return run_plan_id

    return _optional_payload_text(run, "runPlanId", "run_plan_id", "executionPlanId", "execution_plan_id")


def _extract_run_suite_id(run: GxExecutionRunEntity) -> str | None:
    execution_contract = _extract_run_execution_contract(run)
    if execution_contract is not None:
        traceability = execution_contract.traceability
        if traceability is not None:
            normalized_suite_id = str(traceability.gxSuiteId or "").strip()
            if normalized_suite_id:
                return normalized_suite_id
    return _optional_payload_text(run, "suiteId", "suite_id")


def _extract_run_data_object_version_id(run: GxExecutionRunEntity) -> str | None:
    execution_contract = _extract_run_execution_contract(run)
    if execution_contract is not None:
        traceability = execution_contract.traceability
        if traceability is not None:
            normalized_data_object_version_id = str(traceability.dataObjectVersionId or "").strip()
            if normalized_data_object_version_id:
                return normalized_data_object_version_id
    return _optional_payload_text(run, "dataObjectVersionId", "data_object_version_id")


def _extract_run_rule_version_id(run: GxExecutionRunEntity) -> str | None:
    execution_contract = _extract_run_execution_contract(run)
    if execution_contract is not None:
        traceability = execution_contract.traceability
        if traceability is not None:
            normalized_rule_version_id = str(traceability.ruleVersionId or "").strip()
            if normalized_rule_version_id:
                return normalized_rule_version_id
    return _optional_payload_text(run, "ruleVersionId", "rule_version_id")


def _filter_runs_for_exception_scope(
    runs: list[GxExecutionRunEntity],
    *,
    delivery_id: str | None = None,
    execution_plan_id: str | None = None,
    suite_id: str | None = None,
    data_object_version_id: str | None = None,
    rule_version_id: str | None = None,
) -> list[GxExecutionRunEntity]:
    normalized_delivery_id = str(delivery_id or "").strip()
    normalized_execution_plan_id = str(execution_plan_id or "").strip()
    normalized_suite_id = str(suite_id or "").strip()
    normalized_data_object_version_id = str(data_object_version_id or "").strip()
    normalized_rule_version_id = str(rule_version_id or "").strip()
    if (
        not normalized_delivery_id
        and not normalized_execution_plan_id
        and not normalized_suite_id
        and not normalized_data_object_version_id
        and not normalized_rule_version_id
    ):
        return list(runs)

    filtered: list[GxExecutionRunEntity] = []
    for run in runs:
        if normalized_delivery_id:
            run_delivery_id = _extract_run_delivery_id(run)
            if run_delivery_id != normalized_delivery_id:
                continue
        if normalized_execution_plan_id:
            run_execution_plan_id = _extract_run_execution_plan_id(run)
            if run_execution_plan_id != normalized_execution_plan_id:
                continue
        if normalized_suite_id:
            run_suite_id = _extract_run_suite_id(run)
            if run_suite_id != normalized_suite_id:
                continue
        if normalized_data_object_version_id:
            run_data_object_version_id = _extract_run_data_object_version_id(run)
            if run_data_object_version_id != normalized_data_object_version_id:
                continue
        if normalized_rule_version_id:
            run_rule_version_id = _extract_run_rule_version_id(run)
            if run_rule_version_id != normalized_rule_version_id:
                continue
        filtered.append(run)
    return filtered


def _collect_data_object_names(
    run: GxExecutionRunEntity,
    data_object_name_by_id: dict[str, str],
    data_object_name_by_version_id: dict[str, str],
) -> tuple[str | None, list[str]]:
    execution_contract = _extract_run_execution_contract(run)
    traceability = execution_contract.traceability if execution_contract is not None else None
    source_materialization = execution_contract.sourceMaterialization if execution_contract is not None else None

    data_object_version_id = str(traceability.dataObjectVersionId or "").strip() or None if traceability is not None else None
    names: list[str] = []
    if data_object_version_id and data_object_version_id in data_object_name_by_version_id:
        names.append(data_object_name_by_version_id[data_object_version_id])

    if source_materialization is not None:
        for source in (source_materialization.leftSource, source_materialization.rightSource):
            source_object_id = str(source.dataObjectId or "").strip() if source is not None else ""
            if source_object_id and source_object_id in data_object_name_by_id:
                names.append(data_object_name_by_id[source_object_id])

    deduped_names: list[str] = []
    for value in names:
        if value not in deduped_names:
            deduped_names.append(value)
    return data_object_version_id, deduped_names
async def resolve_rule_name_map(
    *,
    rule_ids: set[str],
    repository: RulesRepository,
) -> dict[str, str]:
    ordered_ids = sorted(rule_ids)
    if not ordered_ids:
        return {}

    rule_rows = await asyncio.gather(*(repository.get_rule_by_id(rule_id) for rule_id in ordered_ids))
    mapping: dict[str, str] = {}
    for rule_id, row in zip(ordered_ids, rule_rows, strict=False):
        rule_name = str(getattr(row, "name", "") or "").strip() if row is not None else ""
        if rule_name:
            mapping[rule_id] = rule_name
    return mapping


async def resolve_rule_taxonomy_map(
    *,
    rule_ids: set[str],
    repository: RulesRepository,
) -> dict[str, dict[str, str | None]]:
    ordered_ids = sorted(rule_ids)
    if not ordered_ids:
        return {}

    rule_rows = await asyncio.gather(*(repository.get_rule_by_id(rule_id) for rule_id in ordered_ids))
    mapping: dict[str, dict[str, str | None]] = {}
    for rule_id, row in zip(ordered_ids, rule_rows, strict=False):
        taxonomy = getattr(row, "taxonomy", None) if row is not None else None

        def _read_taxonomy_value(field_name: str) -> str | None:
            candidates: list[Any] = []
            if taxonomy is not None:
                candidates.append(getattr(taxonomy, field_name, None))
            if row is not None:
                candidates.append(getattr(row, field_name, None))
            for candidate in candidates:
                normalized = str(candidate or "").strip()
                if normalized:
                    return normalized
            return None

        owner = _read_taxonomy_value("owner")
        domain = _read_taxonomy_value("domain")
        severity = _read_taxonomy_value("severity")
        if owner or domain or severity:
            mapping[rule_id] = {
                "owner": owner,
                "domain": domain,
                "severity": severity,
            }
    return mapping


def resolve_data_object_name_maps(*, repository: DataCatalogRepository) -> tuple[dict[str, str], dict[str, str]]:
    data_object_name_by_id = {
        str(item.id): str(item.name)
        for item in repository.list_data_objects_catalog()
        if str(getattr(item, "id", "") or "").strip() and str(getattr(item, "name", "") or "").strip()
    }
    data_object_name_by_version_id = {
        str(item.id): data_object_name_by_id.get(str(item.data_object_id), str(item.id))
        for item in repository.list_data_object_versions()
        if str(getattr(item, "id", "") or "").strip()
    }
    return data_object_name_by_id, data_object_name_by_version_id


def _read_non_negative_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return int(value)
    if value is None:
        return None
    try:
        number = int(value)
    except (TypeError, ValueError):
        return None
    if number < 0:
        return None
    return number


def _extract_failed_record_count(run: GxExecutionRunEntity) -> int:
    result_summary = build_gx_execution_result_summary_entity(run.resultSummary)
    if result_summary is not None:
        for candidate in (result_summary.recordsFailed, result_summary.failedCount, result_summary.violationCount):
            direct_count = _read_non_negative_int(candidate)
            if direct_count is not None:
                return direct_count

    total = 0
    for item in build_gx_execution_result_item_entities(result_summary):
        for candidate in (item.recordsFailed, item.failedCount, item.violationCount):
            item_count = _read_non_negative_int(candidate)
            if item_count is not None:
                total += item_count
                break
        else:
            if item.ok is False:
                total += 1
    return total


def build_gx_execution_run_summary(
    run: GxExecutionRunEntity,
    rule_name_by_id: dict[str, str],
    rule_taxonomy_by_id: dict[str, dict[str, str | None]],
    data_object_name_by_id: dict[str, str],
    data_object_name_by_version_id: dict[str, str],
) -> GxExecutionRunSummaryEntity:
    rule_id = str(run.ruleId or "").strip() or None
    data_object_version_id, data_object_names = _collect_data_object_names(
        run=run,
        data_object_name_by_id=data_object_name_by_id,
        data_object_name_by_version_id=data_object_name_by_version_id,
    )
    if data_object_version_id is None:
        result_summary = build_gx_execution_result_summary_entity(run.resultSummary)
        candidate_ids = [
            str(item.dataObjectVersionId or "").strip()
            for item in build_gx_execution_result_item_entities(result_summary)
        ]
        candidate_ids = [value for value in candidate_ids if value]
        if candidate_ids:
            data_object_version_id = candidate_ids[0]
            for candidate_id in candidate_ids:
                candidate_name = data_object_name_by_version_id.get(candidate_id) or candidate_id
                if candidate_name not in data_object_names:
                    data_object_names.append(candidate_name)

    execution_shape = str(run.executionShape or "single_object")
    rule_name = rule_name_by_id.get(rule_id or "") if rule_id is not None else None
    rule_taxonomy = rule_taxonomy_by_id.get(rule_id or "") if rule_id is not None else None
    if not rule_name and execution_shape == "grouped_scope":
        rule_name = "Grouped scope run"

    return build_gx_execution_run_summary_entity(
        {
            "id": run.id,
            "suiteId": run.suiteId,
            "suiteVersion": run.suiteVersion,
            "ruleId": rule_id,
            "ruleName": rule_name,
            "owner": rule_taxonomy.get("owner") if rule_taxonomy is not None else None,
            "domain": rule_taxonomy.get("domain") if rule_taxonomy is not None else None,
            "severity": rule_taxonomy.get("severity") if rule_taxonomy is not None else None,
            "runPlanId": _extract_run_execution_plan_id(run),
            "dataObjectVersionId": data_object_version_id,
            "dataObjectNames": data_object_names,
            "resolvedDataDeliveryId": _extract_run_delivery_id(run),
            "correlationId": run.correlationId,
            "requestedBy": run.requestedBy,
            "engineType": run.engineType,
            "engineTarget": str(run.engineTarget or "pyspark"),
            "executionShape": execution_shape,
            "status": str(run.status or "pending"),
            "failedRecordCount": _extract_failed_record_count(run),
            "submittedAt": run.submittedAt,
            "startedAt": run.startedAt,
            "completedAt": run.completedAt,
            "createdAt": run.createdAt,
            "updatedAt": run.updatedAt,
        }
    )


def filter_gx_execution_run_summaries(
    *,
    runs: list[GxExecutionRunEntity],
    rule_name_by_id: dict[str, str],
    rule_taxonomy_by_id: dict[str, dict[str, str | None]],
    data_object_name_by_id: dict[str, str],
    data_object_name_by_version_id: dict[str, str],
    rule_name: str | None,
    owner: str | None,
    domain: str | None,
    severity: str | None,
    data_object_name: str | None,
    search: str | None,
    limit: int | None,
    workspace_run_plan_ids: set[str] | None = None,
    run_plan_id: str | None = None,
    suite_keys: set[tuple[str, int]] | None = None,
    delivery_id: str | None = None,
) -> list[GxExecutionRunSummaryEntity]:
    normalized_rule_name = _normalize_search_term(rule_name)
    normalized_owner = _normalize_search_term(owner)
    normalized_domain = _normalize_search_term(domain)
    normalized_severity = _normalize_search_term(severity)
    normalized_data_object_name = _normalize_search_term(data_object_name)
    normalized_search = _normalize_search_term(search)

    summaries: list[GxExecutionRunSummaryEntity] = []
    for run in runs:
        if not _run_matches_scope(
            run,
            workspace_run_plan_ids=workspace_run_plan_ids,
            run_plan_id=run_plan_id,
            suite_keys=suite_keys,
            delivery_id=delivery_id,
        ):
            continue
        summary = build_gx_execution_run_summary(
            run=run,
            rule_name_by_id=rule_name_by_id,
            rule_taxonomy_by_id=rule_taxonomy_by_id,
            data_object_name_by_id=data_object_name_by_id,
            data_object_name_by_version_id=data_object_name_by_version_id,
        )

        summary_rule_name = _normalize_search_term(summary.ruleName)
        summary_rule_id = _normalize_search_term(summary.ruleId)
        summary_owner = _normalize_search_term(summary.owner)
        summary_domain = _normalize_search_term(summary.domain)
        summary_severity = _normalize_search_term(summary.severity)
        summary_engine_type = _normalize_search_term(summary.engineType)
        summary_data_object_names = [_normalize_search_term(value) for value in summary.dataObjectNames]
        summary_haystack = [
            _normalize_search_term(summary.id),
            _normalize_search_term(summary.suiteId),
            _normalize_search_term(summary.correlationId),
            _normalize_search_term(summary.requestedBy),
            _normalize_search_term(summary.dataObjectVersionId),
            _normalize_search_term(summary.executionShape),
            _normalize_search_term(summary.status),
            summary_engine_type,
            _normalize_search_term(summary.engineTarget),
            summary_rule_name,
            summary_rule_id,
            summary_owner,
            summary_domain,
            summary_severity,
            *summary_data_object_names,
        ]

        if normalized_rule_name and normalized_rule_name not in summary_rule_name and normalized_rule_name not in summary_rule_id:
            continue
        if normalized_owner and normalized_owner not in summary_owner:
            continue
        if normalized_domain and normalized_domain not in summary_domain:
            continue
        if normalized_severity and normalized_severity not in summary_severity:
            continue
        if normalized_data_object_name and not any(
            normalized_data_object_name in candidate for candidate in summary_data_object_names
        ):
            continue
        if normalized_search and not any(normalized_search in candidate for candidate in summary_haystack if candidate):
            continue

        summaries.append(summary)
        if limit is not None and len(summaries) >= limit:
            break

    return summaries


def build_gx_exception_bucket_frames(
    *,
    lookback_amount: int,
    lookback_unit: str,
    now: datetime,
) -> tuple[list[dict[str, int | str]], datetime, int]:
    bucket_count = min(max(lookback_amount, 1), 8 if lookback_unit == "hours" else 7)
    lookback_delta = timedelta(hours=lookback_amount) if lookback_unit == "hours" else timedelta(days=lookback_amount)
    bucket_window_start = now - lookback_delta
    bucket_size_seconds = max(int(lookback_delta.total_seconds() / bucket_count), 1)

    trend_buckets: list[dict[str, int | str]] = []
    for bucket_index in range(bucket_count):
        bucket_start = bucket_window_start + timedelta(seconds=bucket_size_seconds * bucket_index)
        trend_buckets.append(
            {
                "bucketStart": bucket_start.isoformat(),
                "total": 0,
            }
        )

    return trend_buckets, bucket_window_start, bucket_size_seconds


def _resolve_submitted_after(*, lookback_amount: int, lookback_unit: str, now: datetime) -> datetime:
    lookback_delta = timedelta(hours=lookback_amount) if lookback_unit == "hours" else timedelta(days=lookback_amount)
    return now - lookback_delta


async def _build_gx_execution_exception_analytics_from_runs(
    *,
    runs: list[GxExecutionRunEntity],
    lookback_amount: int,
    lookback_unit: str,
    status: str | None,
    rule_name: str | None,
    data_object_name: str | None,
    search: str | None,
    reason_code: str | None,
    projection_repository: ExceptionReasonAnalyticsProjectionRepository,
    rules_repository: RulesRepository,
    data_catalog_repository: DataCatalogRepository,
    now: datetime,
) -> tuple[GxExecutionExceptionAnalyticsEntity, list[str], list[str]]:
    submitted_after = _resolve_submitted_after(
        lookback_amount=lookback_amount,
        lookback_unit=lookback_unit,
        now=now,
    )
    trend_buckets, bucket_window_start, bucket_size_seconds = build_gx_exception_bucket_frames(
        lookback_amount=lookback_amount,
        lookback_unit=lookback_unit,
        now=now,
    )

    data_object_name_by_id, data_object_name_by_version_id = resolve_data_object_name_maps(repository=data_catalog_repository)
    rule_name_by_id = await resolve_rule_name_map(
        rule_ids={str(run.ruleId or "") for run in runs if str(run.ruleId or "").strip()},
        repository=rules_repository,
    )
    rule_taxonomy_by_id = await resolve_rule_taxonomy_map(
        rule_ids={str(run.ruleId or "") for run in runs if str(run.ruleId or "").strip()},
        repository=rules_repository,
    )
    summaries = filter_gx_execution_run_summaries(
        runs=runs,
        rule_name_by_id=rule_name_by_id,
        rule_taxonomy_by_id=rule_taxonomy_by_id,
        data_object_name_by_id=data_object_name_by_id,
        data_object_name_by_version_id=data_object_name_by_version_id,
        rule_name=rule_name,
        owner=None,
        domain=None,
        severity=None,
        data_object_name=data_object_name,
        search=search,
        limit=None,
    )
    if not summaries:
        return (
            build_gx_execution_exception_analytics_entity(
                {
                    "totalFailedRecords": 0,
                    "runsWithFailures": 0,
                    "trendBuckets": trend_buckets,
                    "topRules": [],
                    "topDataObjects": [],
                    "topReasons": [],
                    "reasonTrendBuckets": [],
                    "reasonFluctuations": [],
                }
            ),
            [],
            [],
        )

    matched_run_ids = sorted({str(summary.id or "").strip() for summary in summaries if str(summary.id or "").strip()})
    matched_scope_ids = sorted(
        {
            str(summary.dataObjectVersionId or "").strip()
            for summary in summaries
            if str(summary.dataObjectVersionId or "").strip()
        }
    )
    normalized_reason_code = str(reason_code or "").strip()
    summary = await projection_repository.summarize_reason_analytics(
        data_object_version_ids=matched_scope_ids,
        execution_run_ids=matched_run_ids,
        reason_codes=[normalized_reason_code] if normalized_reason_code else None,
        detected_after=submitted_after.isoformat(),
        detected_before=now.isoformat(),
        bucket_origin=bucket_window_start.isoformat(),
        bucket_size_seconds=bucket_size_seconds,
        bucket_count=len(trend_buckets),
    )

    violation_rule_ids = {str(item.rule_id or "").strip() for item in summary.rule_totals if str(item.rule_id or "").strip()}
    unresolved_rule_ids = violation_rule_ids.difference(rule_name_by_id)
    if unresolved_rule_ids:
        rule_name_by_id.update(await resolve_rule_name_map(rule_ids=unresolved_rule_ids, repository=rules_repository))

    trend_totals = {
        str(item.bucket_start or "").strip(): int(item.total or 0)
        for item in summary.trend_totals
        if str(item.bucket_start or "").strip()
    }
    for bucket in trend_buckets:
        bucket["total"] = trend_totals.get(str(bucket.get("bucketStart") or ""), 0)

    top_rules = [
        {
            "ruleId": rule_id,
            "ruleName": rule_name_by_id.get(rule_id) or rule_id,
            "total": int(item.total or 0),
        }
        for item in summary.rule_totals
        for rule_id in [str(item.rule_id or "").strip()]
        if rule_id
    ]
    top_data_objects = [
        {
            "dataObjectVersionId": data_object_version_id,
            "dataObjectName": data_object_name_by_version_id.get(data_object_version_id) or data_object_version_id,
            "total": int(item.total or 0),
        }
        for item in summary.data_object_totals
        for data_object_version_id in [str(item.data_object_version_id or "").strip()]
        if data_object_version_id
    ]
    top_reasons = [
        {
            "reasonCode": normalized_reason,
            "reasonText": str(item.reason_text or "").strip(),
            "total": int(item.total or 0),
        }
        for item in summary.reason_totals
        for normalized_reason in [str(item.reason_code or "").strip()]
        if normalized_reason and str(item.reason_text or "").strip()
    ]
    reason_trend_buckets = [
        {
            "bucketStart": bucket_start,
            "reasonCode": normalized_reason,
            "reasonText": reason_text,
            "total": int(item.total or 0),
        }
        for item in summary.reason_trend_totals
        for bucket_start in [str(item.bucket_start or "").strip()]
        for normalized_reason in [str(item.reason_code or "").strip()]
        for reason_text in [str(item.reason_text or "").strip()]
        if bucket_start and normalized_reason and reason_text
    ]
    reason_fluctuations = _build_reason_fluctuations(reason_trend_buckets=reason_trend_buckets)

    return (
        build_gx_execution_exception_analytics_entity(
            {
                "totalFailedRecords": int(summary.total_failed_records or 0),
                "runsWithFailures": int(summary.runs_with_failures or 0),
                "trendBuckets": trend_buckets,
                "topRules": top_rules,
                "topDataObjects": top_data_objects,
                "topReasons": top_reasons,
                "reasonTrendBuckets": reason_trend_buckets,
                "reasonFluctuations": reason_fluctuations,
            }
        ),
        matched_run_ids,
        matched_scope_ids,
    )


def _build_reason_fluctuations(*, reason_trend_buckets: list[dict[str, int | str]]) -> list[dict[str, int | str]]:
    grouped: dict[tuple[str, str], list[dict[str, int | str]]] = {}
    for item in reason_trend_buckets:
        reason_code = str(item.get("reasonCode") or "").strip()
        reason_text = str(item.get("reasonText") or "").strip()
        bucket_start = str(item.get("bucketStart") or "").strip()
        if not reason_code or not reason_text or not bucket_start:
            continue
        grouped.setdefault((reason_code, reason_text), []).append(item)

    fluctuations: list[dict[str, int | str]] = []
    for (reason_code, reason_text), rows in grouped.items():
        ordered_rows = sorted(rows, key=lambda item: str(item.get("bucketStart") or ""))
        first_row = ordered_rows[0]
        latest_row = ordered_rows[-1]
        peak_row = max(
            ordered_rows,
            key=lambda item: (int(item.get("total") or 0), str(item.get("bucketStart") or "")),
        )
        first_total = int(first_row.get("total") or 0)
        latest_total = int(latest_row.get("total") or 0)
        net_change = latest_total - first_total
        direction = "flat"
        if net_change > 0:
            direction = "up"
        elif net_change < 0:
            direction = "down"
        fluctuations.append(
            {
                "reasonCode": reason_code,
                "reasonText": reason_text,
                "firstBucketStart": str(first_row.get("bucketStart") or ""),
                "firstTotal": first_total,
                "latestBucketStart": str(latest_row.get("bucketStart") or ""),
                "latestTotal": latest_total,
                "netChange": net_change,
                "direction": direction,
                "peakBucketStart": str(peak_row.get("bucketStart") or ""),
                "peakTotal": int(peak_row.get("total") or 0),
                "bucketCount": len(ordered_rows),
            }
        )

    return sorted(
        fluctuations,
        key=lambda item: (
            -abs(int(item.get("netChange") or 0)),
            -int(item.get("latestTotal") or 0),
            str(item.get("reasonCode") or ""),
        ),
    )


async def list_gx_execution_run_summaries(
    query: ListGxExecutionRunsQuery,
    repository: GxExecutionRunRepository,
    run_plan_repository: GxRunPlanRepository,
    rules_repository: RulesRepository,
    data_catalog_repository: DataCatalogRepository,
    suite_repository: GxSuiteRepository,
    *,
    now: datetime | None = None,
) -> list[GxExecutionRunSummaryEntity]:
    current_time = now or datetime.now(UTC)
    submitted_after = _resolve_submitted_after(
        lookback_amount=query.lookback_amount,
        lookback_unit=query.lookback_unit,
        now=current_time,
    )
    runs = await repository.list_runs(
        {
            "submitted_after": submitted_after,
            "status": query.status,
        }
    )
    workspace_run_plan_ids = await _resolve_workspace_run_plan_ids(
        workspace_id=query.workspace_id,
        repository=run_plan_repository,
    )
    suite_keys = await _resolve_suite_keys_for_scope(
        data_product_id=query.data_product_id,
        dataset_id=query.dataset_id,
        data_object_id=query.data_object_id,
        data_object_version_id=query.data_object_version_id,
        repository=suite_repository,
    )
    data_object_name_by_id, data_object_name_by_version_id = resolve_data_object_name_maps(repository=data_catalog_repository)
    rule_name_by_id = await resolve_rule_name_map(
        rule_ids={str(run.ruleId or "") for run in runs if str(run.ruleId or "").strip()},
        repository=rules_repository,
    )
    rule_taxonomy_by_id = await resolve_rule_taxonomy_map(
        rule_ids={str(run.ruleId or "") for run in runs if str(run.ruleId or "").strip()},
        repository=rules_repository,
    )
    return filter_gx_execution_run_summaries(
        runs=runs,
        rule_name_by_id=rule_name_by_id,
        rule_taxonomy_by_id=rule_taxonomy_by_id,
        data_object_name_by_id=data_object_name_by_id,
        data_object_name_by_version_id=data_object_name_by_version_id,
        rule_name=query.rule_name,
        owner=query.owner,
        domain=query.domain,
        severity=query.severity,
        data_object_name=query.data_object_name,
        search=query.search,
        limit=query.limit,
        workspace_run_plan_ids=workspace_run_plan_ids,
        run_plan_id=query.run_plan_id,
        suite_keys=suite_keys or None,
        delivery_id=query.delivery_id,
    )


async def get_gx_execution_run_statistics(
    query: GxExecutionRunStatisticsQuery,
    repository: GxExecutionRunRepository,
    run_plan_repository: GxRunPlanRepository,
    rules_repository: RulesRepository,
    data_catalog_repository: DataCatalogRepository,
    suite_repository: GxSuiteRepository,
    *,
    now: datetime | None = None,
) -> GxExecutionRunStatisticsEntity:
    current_time = now or datetime.now(UTC)
    summary_rows = await list_gx_execution_run_summaries(
        query=ListGxExecutionRunsQuery(
            lookback_amount=query.lookback_amount,
            lookback_unit=query.lookback_unit,
            status=query.status,
            rule_name=query.rule_name,
            owner=query.owner,
            domain=query.domain,
            severity=query.severity,
            data_object_name=query.data_object_name,
            search=query.search,
            limit=None,
            data_product_id=query.data_product_id,
            dataset_id=query.dataset_id,
            data_object_id=query.data_object_id,
            data_object_version_id=query.data_object_version_id,
            delivery_id=query.delivery_id,
            workspace_id=query.workspace_id,
            run_plan_id=query.run_plan_id,
        ),
        repository=repository,
        run_plan_repository=run_plan_repository,
        rules_repository=rules_repository,
        data_catalog_repository=data_catalog_repository,
        suite_repository=suite_repository,
        now=current_time,
    )

    status_totals = Counter(str(summary.status or "").strip() for summary in summary_rows if str(summary.status or "").strip())
    engine_target_totals = Counter(str(summary.engineTarget or "").strip() for summary in summary_rows if str(summary.engineTarget or "").strip())
    execution_shape_totals = Counter(str(summary.executionShape or "").strip() for summary in summary_rows if str(summary.executionShape or "").strip())

    def _build_count_rows(counter: Counter[str]) -> list[GxExecutionRunCountEntity]:
        return [
            GxExecutionRunCountEntity(name=name, count=count)
            for name, count in sorted(counter.items(), key=lambda item: (-item[1], item[0]))
        ]

    return GxExecutionRunStatisticsEntity(
        lookbackAmount=query.lookback_amount,
        lookbackUnit=query.lookback_unit,
        recentLimit=query.recent_limit,
        totalRuns=len(summary_rows),
        pendingRuns=int(status_totals.get("pending", 0)),
        runningRuns=int(status_totals.get("running", 0)),
        succeededRuns=int(status_totals.get("succeeded", 0)),
        failedRuns=int(status_totals.get("failed", 0)),
        cancelledRuns=int(status_totals.get("cancelled", 0)),
        statusBreakdown=_build_count_rows(status_totals),
        engineTargetBreakdown=_build_count_rows(engine_target_totals),
        executionShapeBreakdown=_build_count_rows(execution_shape_totals),
        recentRuns=summary_rows[: query.recent_limit],
    )


async def get_gx_execution_exception_analytics(
    query: GxExecutionExceptionAnalyticsQuery,
    repository: GxExecutionRunRepository,
    run_plan_repository: GxRunPlanRepository,
    projection_repository: ExceptionReasonAnalyticsProjectionRepository,
    rules_repository: RulesRepository,
    data_catalog_repository: DataCatalogRepository,
    suite_repository: GxSuiteRepository,
    *,
    now: datetime | None = None,
) -> GxExecutionExceptionAnalyticsEntity:
    current_time = now or datetime.now(UTC)
    submitted_after = _resolve_submitted_after(
        lookback_amount=query.lookback_amount,
        lookback_unit=query.lookback_unit,
        now=current_time,
    )
    trend_buckets, bucket_window_start, bucket_size_seconds = build_gx_exception_bucket_frames(
        lookback_amount=query.lookback_amount,
        lookback_unit=query.lookback_unit,
        now=current_time,
    )

    runs = await repository.list_runs(
        {
            "submitted_after": submitted_after,
            "status": query.status,
        }
    )
    workspace_run_plan_ids = await _resolve_workspace_run_plan_ids(
        workspace_id=query.workspace_id,
        repository=run_plan_repository,
    )
    suite_keys = await _resolve_suite_keys_for_scope(
        data_product_id=query.data_product_id,
        dataset_id=query.dataset_id,
        data_object_id=query.data_object_id,
        data_object_version_id=query.data_object_version_id,
        repository=suite_repository,
    )
    scoped_runs = _filter_runs_for_exception_scope(
        runs,
        suite_id=query.suite_id,
        data_object_version_id=query.data_object_version_id,
        rule_version_id=query.rule_version_id,
    )
    scoped_runs = [
        run for run in scoped_runs
        if _run_matches_scope(run, suite_keys=suite_keys or None, delivery_id=query.delivery_id)
    ]
    analytics, _, _ = await _build_gx_execution_exception_analytics_from_runs(
        runs=scoped_runs,
        lookback_amount=query.lookback_amount,
        lookback_unit=query.lookback_unit,
        status=query.status,
        rule_name=query.rule_name,
        data_object_name=query.data_object_name,
        search=query.search,
        reason_code=query.reason_code,
        projection_repository=projection_repository,
        rules_repository=rules_repository,
        data_catalog_repository=data_catalog_repository,
        now=current_time,
    )
    return analytics


async def get_gx_execution_exception_analytics_for_scope(
    query: ScopedGxExecutionExceptionAnalyticsQuery,
    repository: GxExecutionRunRepository,
    projection_repository: ExceptionReasonAnalyticsProjectionRepository,
    rules_repository: RulesRepository,
    data_catalog_repository: DataCatalogRepository,
    *,
    now: datetime | None = None,
) -> ScopedGxExecutionExceptionAnalyticsResult:
    current_time = now or datetime.now(UTC)
    submitted_after = _resolve_submitted_after(
        lookback_amount=query.lookback_amount,
        lookback_unit=query.lookback_unit,
        now=current_time,
    )
    runs = await repository.list_runs(
        {
            "submitted_after": submitted_after,
            "status": query.status,
        }
    )
    scoped_runs = _filter_runs_for_exception_scope(
        runs,
        delivery_id=query.delivery_id,
        execution_plan_id=query.execution_plan_id,
        suite_id=query.suite_id,
        data_object_version_id=query.data_object_version_id,
        rule_version_id=query.rule_version_id,
    )
    analytics, execution_run_ids, data_object_version_ids = await _build_gx_execution_exception_analytics_from_runs(
        runs=scoped_runs,
        lookback_amount=query.lookback_amount,
        lookback_unit=query.lookback_unit,
        status=query.status,
        rule_name=query.rule_name,
        data_object_name=query.data_object_name,
        search=query.search,
        reason_code=query.reason_code,
        projection_repository=projection_repository,
        rules_repository=rules_repository,
        data_catalog_repository=data_catalog_repository,
        now=current_time,
    )
    return ScopedGxExecutionExceptionAnalyticsResult(
        analytics=analytics,
        execution_run_ids=execution_run_ids,
        data_object_version_ids=data_object_version_ids,
    )