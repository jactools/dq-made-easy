from __future__ import annotations

from collections.abc import Callable, Mapping
from hashlib import sha256
import math
from typing import Any

from fastapi import HTTPException

from app.domain.entities.gx_execution_run import build_gx_dispatch_payload_entity


def build_data_catalog_page_payload(rows: list[dict[str, Any]], page: int, limit: int) -> dict[str, Any]:
    safe_page = max(1, page)
    safe_limit = max(1, min(100, limit))
    offset = (safe_page - 1) * safe_limit
    total = len(rows)
    total_pages = math.ceil(total / safe_limit) if total else 0

    return {
        "data": rows[offset : offset + safe_limit],
        "pagination": {
            "total": total,
            "page": safe_page,
            "limit": safe_limit,
            "total_pages": total_pages,
            "has_next": safe_page < total_pages,
            "has_previous": safe_page > 1,
        },
    }


def _entity_payload(value: Any) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    model_dump = getattr(value, "model_dump", None)
    if callable(model_dump):
        dumped = model_dump(exclude_none=False)
        if isinstance(dumped, Mapping):
            return dict(dumped)
    return {}


def resolve_delivery_inventory_location(
    *,
    delivery_location: str,
    layer: str | None,
    workspace: str | None,
    data_object_id: str | None,
    data_object_name: str | None,
) -> str:
    raw_location = str(delivery_location or "").strip()
    if not raw_location:
        raise HTTPException(
            status_code=422,
            detail={
                "error": "invalid_delivery_location",
                "message": "delivery_location must not be empty",
                "delivery_location": delivery_location,
            },
        )

    if raw_location.startswith("s3://"):
        return "s3a://" + raw_location[len("s3://") :]
    if raw_location.startswith("s3a://"):
        return raw_location

    bucket = str(workspace or "").strip()
    if not bucket:
        raise HTTPException(
            status_code=422,
            detail={
                "error": "invalid_delivery_location",
                "message": "logical delivery_location requires a workspace to resolve storage",
                "delivery_location": delivery_location,
            },
        )

    layer_name = str(layer or "").strip()
    object_name = str(data_object_name or "").strip()
    logical_location = raw_location.replace(":", "/")
    segments = [segment for segment in logical_location.split("/") if segment]
    if layer_name and segments and segments[0] == layer_name:
        segments = segments[1:]
    if data_object_id and object_name:
        segments = [object_name if segment == data_object_id else segment for segment in segments]

    normalized_location = "/".join(segments)
    if not normalized_location:
        raise HTTPException(
            status_code=422,
            detail={
                "error": "invalid_delivery_location",
                "message": "delivery_location could not be resolved to a storage path",
                "delivery_location": delivery_location,
            },
        )

    return f"s3a://{bucket}/{layer_name}/{normalized_location}" if layer_name else f"s3a://{bucket}/{normalized_location}"


def resolve_delivery_linked_execution_delivery_id(
    run: Any,
    *,
    dispatch_payload_builder: Callable[[Any], Any] = build_gx_dispatch_payload_entity,
) -> str:
    run_payload = _entity_payload(run)
    execution_contract = run_payload.get("executionContract") if isinstance(run_payload.get("executionContract"), Mapping) else {}
    linked_data_delivery_id = str(
        execution_contract.get("resolvedDataDeliveryId")
        or execution_contract.get("resolved_data_delivery_id")
        or ""
    ).strip()
    if linked_data_delivery_id:
        return linked_data_delivery_id

    handoff_payload = run_payload.get("handoffPayload")
    if isinstance(handoff_payload, Mapping):
        raw_delivery_snapshot = handoff_payload.get("deliverySnapshot")
        if not isinstance(raw_delivery_snapshot, Mapping):
            raw_delivery_snapshot = handoff_payload.get("delivery_snapshot")
        if isinstance(raw_delivery_snapshot, Mapping):
            linked_data_delivery_id = str(
                raw_delivery_snapshot.get("resolvedDataDeliveryId")
                or raw_delivery_snapshot.get("resolved_data_delivery_id")
                or ""
            ).strip()
            if linked_data_delivery_id:
                return linked_data_delivery_id

    dispatch_payload = dispatch_payload_builder(handoff_payload)
    delivery_snapshot = dispatch_payload.deliverySnapshot if dispatch_payload is not None else None
    linked_data_delivery_id = str(
        delivery_snapshot.resolvedDataDeliveryId if delivery_snapshot is not None else ""
    ).strip()
    if linked_data_delivery_id:
        return linked_data_delivery_id

    return ""


def resolve_delivery_linked_execution_sort_key(run: Mapping[str, object]) -> tuple[str, str, str, str]:
    run_payload = _entity_payload(run)
    return (
        str(run_payload.get("completedAt") or ""),
        str(run_payload.get("submittedAt") or ""),
        str(run_payload.get("createdAt") or ""),
        str(run_payload.get("id") or ""),
    )


def build_delivery_linked_execution_note_enrichment(
    *,
    delivery_id: str,
    runs: list[Any],
    dispatch_payload_builder: Callable[[Any], Any] = build_gx_dispatch_payload_entity,
) -> dict[str, object]:
    linked_runs = [
        run
        for run in runs
        if resolve_delivery_linked_execution_delivery_id(run, dispatch_payload_builder=dispatch_payload_builder) == delivery_id
    ]
    if not linked_runs:
        return {}

    linked_runs.sort(key=resolve_delivery_linked_execution_sort_key, reverse=True)
    status_counts: dict[str, int] = {}
    execution_references: list[dict[str, object]] = []

    for run in linked_runs:
        run_payload = _entity_payload(run)
        execution_status = str(run_payload.get("status") or "unknown").strip() or "unknown"
        status_counts[execution_status] = status_counts.get(execution_status, 0) + 1
        execution_references.append(
            {
                "execution_run_id": str(run_payload.get("id") or ""),
                "execution_status": execution_status,
                "correlation_id": str(run_payload.get("correlationId") or ""),
                "requested_by": str(run_payload.get("requestedBy") or "").strip() or None,
                "suite_id": str(run_payload.get("suiteId") or "").strip() or None,
                "suite_version": run_payload.get("suiteVersion"),
                "rule_id": str(run_payload.get("ruleId") or "").strip() or None,
                "rule_version_id": str(run_payload.get("ruleVersionId") or "").strip() or None,
                "engine_target": str(run_payload.get("engineTarget") or "").strip() or None,
                "execution_shape": str(run_payload.get("executionShape") or "").strip() or None,
                "submitted_at": str(run_payload.get("submittedAt") or ""),
                "started_at": str(run_payload.get("startedAt") or "").strip() or None,
                "completed_at": str(run_payload.get("completedAt") or "").strip() or None,
            }
        )

    latest_run = _entity_payload(linked_runs[0])
    return {
        "execution_summary": {
            "total_execution_runs": len(linked_runs),
            "status_counts": status_counts,
            "latest_execution_run_id": str(latest_run.get("id") or "").strip() or None,
            "latest_execution_status": str(latest_run.get("status") or "").strip() or None,
            "latest_execution_submitted_at": str(latest_run.get("submittedAt") or "").strip() or None,
            "latest_execution_completed_at": str(latest_run.get("completedAt") or "").strip() or None,
        },
        "execution_references": execution_references,
    }


def resolve_catalog_materialization_selection(
    payload: Any,
    repository: Any,
) -> tuple[list[dict[str, object]], dict[str, object]]:
    selector_candidates = {
        "data_product_id": str(payload.data_product_id or "").strip(),
        "data_set_id": str(payload.data_set_id or "").strip(),
        "data_object_id": str(payload.data_object_id or "").strip(),
        "data_object_version_id": str(payload.data_object_version_id or "").strip(),
    }
    provided = {key: value for key, value in selector_candidates.items() if value}
    if len(provided) != 1:
        raise HTTPException(
            status_code=422,
            detail={
                "error": "invalid_materialization_selector",
                "message": "Provide exactly one of data_product_id, data_set_id, data_object_id, or data_object_version_id",
                "provided_selector_types": sorted(provided.keys()),
            },
        )

    selector_type, selector_value = next(iter(provided.items()))

    def _resolve_for_object_id(
        object_id: str,
        *,
        requested_selector_type: str,
        requested_selector_value: str,
        data_set_id: str | None = None,
        data_product_id: str | None = None,
    ) -> dict[str, object]:
        objects = repository.list_data_objects_catalog()
        data_object = next((row for row in objects if str(row.id or "") == object_id), None)
        if data_object is None:
            raise HTTPException(
                status_code=404,
                detail={
                    "error": "materialization_scope_not_found",
                    "message": f"Data object '{object_id}' was not found",
                    "selector_type": requested_selector_type,
                    "selector_value": requested_selector_value,
                },
            )

        latest_version_id = str(getattr(data_object, "latest_version_id", None) or "").strip()
        if not latest_version_id:
            versions = repository.list_data_object_versions(object_id)
            if not versions:
                raise HTTPException(
                    status_code=404,
                    detail={
                        "error": "materialization_scope_not_found",
                        "message": f"Data object '{object_id}' has no versions to materialize",
                        "selector_type": requested_selector_type,
                        "selector_value": requested_selector_value,
                    },
                )
            if len(versions) != 1:
                raise HTTPException(
                    status_code=409,
                    detail={
                        "error": "materialization_scope_ambiguous",
                        "message": f"Data object '{object_id}' does not resolve unambiguously to one version",
                        "selector_type": requested_selector_type,
                        "selector_value": requested_selector_value,
                        "candidate_data_object_version_ids": [str(version.id or "") for version in versions],
                    },
                )
            resolved_version = versions[0]
        else:
            resolved_version = repository.get_data_object_version(latest_version_id)
            if resolved_version is None:
                raise HTTPException(
                    status_code=404,
                    detail={
                        "error": "materialization_scope_not_found",
                        "message": f"Latest version '{latest_version_id}' for data object '{object_id}' was not found",
                        "selector_type": requested_selector_type,
                        "selector_value": requested_selector_value,
                    },
                )

        return {
            "data_product_id": data_product_id,
            "data_set_id": data_set_id or str(getattr(data_object, "dataset_id", "") or "").strip() or None,
            "data_object_id": str(data_object.id or ""),
            "data_object_version_id": str(resolved_version.id or ""),
            "version": int(getattr(resolved_version, "version", 0) or 0),
        }

    def _build_selection(targets: list[dict[str, object]]) -> dict[str, object]:
        product_ids = sorted(
            {str(target.get("data_product_id") or "").strip() for target in targets if str(target.get("data_product_id") or "").strip()}
        )
        data_set_ids = sorted(
            {str(target.get("data_set_id") or "").strip() for target in targets if str(target.get("data_set_id") or "").strip()}
        )
        return {
            "selector_type": selector_type,
            "requested": {selector_type: selector_value},
            "resolved": {
                "data_product_id": product_ids[0] if len(product_ids) == 1 else None,
                "data_product_ids": product_ids,
                "data_set_id": data_set_ids[0] if len(data_set_ids) == 1 else None,
                "data_set_ids": data_set_ids,
                "data_object_id": str(targets[0].get("data_object_id") or "") if len(targets) == 1 else None,
                "data_object_ids": [str(target.get("data_object_id") or "") for target in targets],
                "data_object_version_id": str(targets[0].get("data_object_version_id") or "") if len(targets) == 1 else None,
                "data_object_version_ids": [str(target.get("data_object_version_id") or "") for target in targets],
                "target_count": len(targets),
                "targets": [
                    {
                        "data_product_id": target.get("data_product_id"),
                        "data_set_id": target.get("data_set_id"),
                        "data_object_id": target.get("data_object_id"),
                        "data_object_version_id": target.get("data_object_version_id"),
                        "version": target.get("version"),
                    }
                    for target in targets
                ],
            },
        }

    if selector_type == "data_object_version_id":
        version = repository.get_data_object_version(selector_value)
        if version is None:
            raise HTTPException(
                status_code=404,
                detail={
                    "error": "materialization_scope_not_found",
                    "message": f"Data object version '{selector_value}' was not found",
                    "selector_type": selector_type,
                    "selector_value": selector_value,
                },
            )
        target = {
            "data_object_version_id": str(version.id or ""),
            "data_object_id": str(getattr(version, "data_object_id", "") or ""),
            "version": int(getattr(version, "version", 0) or 0),
        }
        return [target], _build_selection([target])

    if selector_type == "data_object_id":
        target = _resolve_for_object_id(
            selector_value,
            requested_selector_type=selector_type,
            requested_selector_value=selector_value,
        )
        return [target], _build_selection([target])

    if selector_type == "data_set_id":
        objects = sorted(repository.list_data_objects_catalog(selector_value), key=lambda row: str(row.id or ""))
        if not objects:
            raise HTTPException(
                status_code=404,
                detail={
                    "error": "materialization_scope_not_found",
                    "message": f"Data set '{selector_value}' was not found or has no data objects",
                    "selector_type": selector_type,
                    "selector_value": selector_value,
                },
            )
        targets = [
            _resolve_for_object_id(
                str(obj.id or ""),
                requested_selector_type=selector_type,
                requested_selector_value=selector_value,
                data_set_id=selector_value,
            )
            for obj in objects
        ]
        return targets, _build_selection(targets)

    data_sets = sorted(repository.list_data_sets(selector_value), key=lambda row: str(row.id or ""))
    if not data_sets:
        raise HTTPException(
            status_code=404,
            detail={
                "error": "materialization_scope_not_found",
                "message": f"Data product '{selector_value}' was not found or has no data sets",
                "selector_type": selector_type,
                "selector_value": selector_value,
            },
        )
    targets: list[dict[str, object]] = []
    for data_set in data_sets:
        objects = sorted(repository.list_data_objects_catalog(str(data_set.id or "")), key=lambda row: str(row.id or ""))
        for obj in objects:
            targets.append(
                _resolve_for_object_id(
                    str(obj.id or ""),
                    requested_selector_type=selector_type,
                    requested_selector_value=selector_value,
                    data_set_id=str(data_set.id or ""),
                    data_product_id=selector_value,
                )
            )
    if not targets:
        raise HTTPException(
            status_code=404,
            detail={
                "error": "materialization_scope_not_found",
                "message": f"Data product '{selector_value}' resolves to no materializable data objects",
                "selector_type": selector_type,
                "selector_value": selector_value,
            },
        )
    return targets, _build_selection(targets)


def build_catalog_materialization_targets(
    *,
    payload: Any,
    resolved_targets: list[dict[str, object]],
    selection: dict[str, object],
    repository: Any,
    build_attribute_payloads: Callable[[list[Any]], list[dict[str, Any]]],
    normalize_s3_uri: Callable[[str], str],
    resolve_test_data_output_prefix: Callable[[], str],
    default_materialization_output_uri: Callable[..., str],
) -> tuple[list[dict[str, object]], dict[str, object], str]:
    selected = [str(name or "").strip() for name in (payload.selected_attribute_names or []) if str(name or "").strip()]
    base_output_uri = normalize_s3_uri(str(payload.output_uri or "").strip())
    if not base_output_uri:
        base_output_uri = resolve_test_data_output_prefix()

    queue_targets: list[dict[str, object]] = []
    selection_targets: list[dict[str, object]] = []
    for target in resolved_targets:
        version_id = str(target.get("data_object_version_id") or "").strip()
        attributes = build_attribute_payloads(repository.list_attributes_catalog(version_id))
        if not attributes:
            raise HTTPException(
                status_code=422,
                detail={
                    "error": "missing_attributes",
                    "message": "Data object version has no attributes to generate test data",
                    "data_object_version_id": version_id,
                },
            )

        attribute_hash = "all"
        if selected:
            selected_set = {name for name in selected}
            filtered = [item for item in attributes if str(item.get("name") or "").strip() in selected_set]
            missing = sorted(selected_set.difference({str(item.get("name") or "").strip() for item in filtered}))
            if missing:
                raise HTTPException(
                    status_code=422,
                    detail={
                        "error": "unknown_attributes",
                        "message": "One or more selected_attribute_names were not found on the data object version",
                        "data_object_version_id": version_id,
                        "missing_attribute_names": missing,
                    },
                )
            attributes = filtered
            attribute_hash = sha256(",".join(sorted(selected_set)).encode("utf-8")).hexdigest()[:12]

        if not attributes:
            raise HTTPException(
                status_code=422,
                detail={
                    "error": "missing_attributes",
                    "message": "No attributes remain after applying selected_attribute_names",
                    "data_object_version_id": version_id,
                },
            )

        if len(resolved_targets) == 1 and str(payload.output_uri or "").strip():
            target_output_uri = normalize_s3_uri(str(payload.output_uri or "").strip())
        else:
            target_output_uri = default_materialization_output_uri(
                output_prefix=base_output_uri,
                version_id=version_id,
                output_format=str(payload.output_format),
                sample_count=int(payload.sample_count),
                attribute_hash=attribute_hash,
            )

        queue_targets.append(
            {
                "data_object_version_id": version_id,
                "sample_count": int(payload.sample_count),
                "output_format": str(payload.output_format).strip().lower(),
                "output_uri": target_output_uri,
                "attributes": attributes,
            }
        )
        selection_targets.append(
            {
                **target,
                "sample_count": int(payload.sample_count),
                "output_format": str(payload.output_format).strip().lower(),
                "output_uri": target_output_uri,
                "selected_attribute_names": selected,
            }
        )

    normalized_selection = dict(selection)
    resolved = dict(normalized_selection.get("resolved") or {})
    resolved["targets"] = selection_targets
    resolved["data_object_version_ids"] = [str(target.get("data_object_version_id") or "") for target in selection_targets]
    resolved["target_count"] = len(selection_targets)
    normalized_selection["resolved"] = resolved

    request_output_uri = queue_targets[0]["output_uri"] if len(queue_targets) == 1 else base_output_uri
    return queue_targets, normalized_selection, str(request_output_uri)
