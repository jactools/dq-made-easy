"""Actuality-date resolution mapping for all cross-object DQ rules.

Applies tolerance resolution and attribute validation at rule-save time
for any check type that joins two data deliveries.
"""
from __future__ import annotations

from typing import Any

from fastapi import HTTPException
from pydantic import TypeAdapter

from app.application.services.actuality_date_resolver import ActualityDateResolutionDispatcher
from app.application.services.actuality_date_resolver import ActualityDateResolutionError
from app.application.services.actuality_date_resolver import auto_resolve_actuality_attributes
from app.domain.entities import rule_policy
from app.domain.entities.rule_check_type import RuleCheckTypeParams

CROSS_OBJECT_CHECK_TYPES = frozenset(
    ("CORRECT", "RECONCILE", "TRANSFER_MATCH", "JOIN_CONSISTENCY")
)


async def apply_actuality_date_resolution(
    *,
    check_type: str | None,
    check_type_params: dict | None,
    catalog_repository: Any,
    actuality_dispatcher: ActualityDateResolutionDispatcher,
    contract_resolver: Any | None = None,
    contract_cache_ttl_seconds: int = 300,
    delivery_repository: Any | None = None,
) -> dict | None:
    """Resolve actuality-date tolerance for cross-object check types.

    When the rule's ``check_type_params`` contain an ``actualityDate`` block,
    this function validates attribute existence, resolves tolerance values,
    and writes the resolved tolerance back into the params dict.

    Returns the (possibly mutated) ``check_type_params`` dict, or the input
    unchanged when no resolution is needed.
    """
    if not check_type or str(check_type).upper() not in CROSS_OBJECT_CHECK_TYPES:
        return check_type_params

    params = dict(check_type_params or {})

    # For JOIN_CONSISTENCY the existing dedicated mapping already handles
    # tolerance resolution; skip duplicate work here.
    if str(check_type).upper() == "JOIN_CONSISTENCY":
        return params

    actuality_date = params.get("actualityDate")
    if actuality_date is None or not isinstance(actuality_date, dict):
        return params

    if not actuality_date:
        return params

    # Determine version IDs based on check type field naming
    left_version_id, right_version_id = _resolve_version_ids(check_type, params)

    # Resolve dataset scope (same logic as join_consistency_mapping)
    dataset_id = _resolve_dataset_scope(
        catalog_repository, left_version_id, right_version_id, check_type
    )

    # Handle auto-resolve for attributes
    actuality_date = dict(actuality_date)
    auto_resolve = bool(actuality_date.get("autoResolve", False))
    left_attr = str(actuality_date.get("leftAttribute") or "").strip()
    right_attr = str(actuality_date.get("rightAttribute") or "").strip()

    if auto_resolve:
        try:
            left_attr, right_attr = auto_resolve_actuality_attributes(
                left_version_id,
                right_version_id,
                catalog_repository=catalog_repository,
                delivery_repository=delivery_repository,
            )
            actuality_date["leftAttribute"] = left_attr
            actuality_date["rightAttribute"] = right_attr
        except ActualityDateResolutionError as exc:
            raise HTTPException(
                status_code=exc.status_code,
                detail=f"Auto-resolve failed for actuality-date attributes: {exc}",
            )

    # Validate attributes exist and are temporal (skip if auto-resolved, already validated)
    if left_attr and right_attr:
        _validate_actuality_attributes(
            catalog_repository,
            left_version_id,
            right_version_id,
            left_attr,
            right_attr,
            check_type,
        )

    # Resolve tolerance
    try:
        resolved = await actuality_dispatcher.resolve(
            actuality_contract=dict(actuality_date),
            left_version_id=left_version_id,
            right_version_id=right_version_id,
            dataset_id=dataset_id,
            catalog_repository=catalog_repository,
        )
    except ActualityDateResolutionError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc))

    actuality_date.update(resolved)
    params["actualityDate"] = actuality_date
    return params


def _resolve_version_ids(
    check_type: str,
    params: dict[str, Any],
) -> tuple[str, str]:
    """Extract left/right version IDs from check-type-specific field names."""
    ct = str(check_type).upper()
    if ct == "CORRECT":
        return (
            str(params.get("sourceDataObjectVersionId") or "").strip(),
            str(params.get("referenceDataObjectVersionId") or "").strip(),
        )
    return (
        str(params.get("leftDataObjectVersionId") or "").strip(),
        str(params.get("rightDataObjectVersionId") or "").strip(),
    )


def _resolve_dataset_scope(
    catalog_repository: Any,
    left_version_id: str,
    right_version_id: str,
    check_type: str,
) -> str | None:
    """Resolve dataset scope from catalog."""
    ct = str(check_type).upper()
    try:
        versions = {
            str(item.id or ""): item
            for item in catalog_repository.list_data_object_versions()
        }
        objects_by_id = {
            str(item.id or ""): item
            for item in catalog_repository.list_data_objects_catalog()
            if str(item.id or "")
        }

        def get_dataset_id(version_id: str) -> str | None:
            version = versions.get(version_id)
            if version is None:
                return None
            obj_id = str(getattr(version, "data_object_id", "") or "").strip()
            obj = objects_by_id.get(obj_id)
            if obj is None:
                return None
            return str(getattr(obj, "dataset_id", "") or "").strip() or None

        left_ds = get_dataset_id(left_version_id)
        right_ds = get_dataset_id(right_version_id)
        if left_ds and right_ds and left_ds != right_ds:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"{ct} requires left and right versions to belong to the "
                    f"same dataset-level contract scope"
                ),
            )
        return left_ds or right_ds or None
    except HTTPException:
        raise
    except Exception:
        return None


def _validate_actuality_attributes(
    catalog_repository: Any,
    left_version_id: str,
    right_version_id: str,
    left_attr: str,
    right_attr: str,
    check_type: str,
) -> None:
    """Validate that actuality attributes exist and are temporal."""
    ct = str(check_type).upper()
    left_attrs = {
        str(item.name or "").strip(): item
        for item in catalog_repository.list_attributes_catalog(left_version_id)
        if str(item.name or "").strip()
    }
    right_attrs = {
        str(item.name or "").strip(): item
        for item in catalog_repository.list_attributes_catalog(right_version_id)
        if str(item.name or "").strip()
    }

    left_item = left_attrs.get(left_attr)
    if left_item is None:
        raise HTTPException(
            status_code=400,
            detail=(
                f"{ct} left actuality attribute '{left_attr}' not found in "
                f"data object version '{left_version_id}'"
            ),
        )
    if not rule_policy.is_temporal_attribute_type(getattr(left_item, "type", None)):
        raise HTTPException(
            status_code=400,
            detail=(
                f"{ct} left actuality attribute '{left_attr}' must be "
                "date/timestamp compatible"
            ),
        )

    right_item = right_attrs.get(right_attr)
    if right_item is None:
        raise HTTPException(
            status_code=400,
            detail=(
                f"{ct} right actuality attribute '{right_attr}' not found in "
                f"data object version '{right_version_id}'"
            ),
        )
    if not rule_policy.is_temporal_attribute_type(getattr(right_item, "type", None)):
        raise HTTPException(
            status_code=400,
            detail=(
                f"{ct} right actuality attribute '{right_attr}' must be "
                "date/timestamp compatible"
            ),
        )
