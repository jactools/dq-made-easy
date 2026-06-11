from __future__ import annotations

from typing import Any

from fastapi import HTTPException
from pydantic import TypeAdapter

from app.application.services.data_contract_resolver import DataContractLookupError
from app.domain.entities import rule_policy
from app.domain.entities.rule_check_type import RuleCheckTypeParams


async def apply_join_consistency_contract_mapping(
    *,
    check_type: str | None,
    check_type_params: dict | None,
    catalog_repository: Any,
    contract_resolver: Any,
    contract_cache_ttl_seconds: int,
) -> dict | None:
    if not check_type or str(check_type).upper() != "JOIN_CONSISTENCY":
        return check_type_params

    raw_params = dict(check_type_params or {})
    raw_params["checkType"] = "JOIN_CONSISTENCY"
    try:
        validated_params = TypeAdapter(RuleCheckTypeParams).validate_python(raw_params)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    params = validated_params.model_dump() if hasattr(validated_params, "model_dump") else dict(validated_params)
    left_version_id = str(params.get("leftDataObjectVersionId") or "").strip()
    right_version_id = str(params.get("rightDataObjectVersionId") or "").strip()
    versions = {str(item.id or ""): item for item in catalog_repository.list_data_object_versions()}

    left_version = versions.get(left_version_id)
    if left_version is None:
        raise HTTPException(status_code=400, detail=f"JOIN_CONSISTENCY left data object version '{left_version_id}' was not found")
    right_version = versions.get(right_version_id)
    if right_version is None:
        raise HTTPException(status_code=400, detail=f"JOIN_CONSISTENCY right data object version '{right_version_id}' was not found")

    objects_by_id = {
        str(item.id or ""): item
        for item in catalog_repository.list_data_objects_catalog()
        if str(item.id or "")
    }

    def resolve_dataset_id(version_id: str) -> str:
        version = versions.get(version_id)
        object_id = str(getattr(version, "data_object_id", "") or "").strip()
        data_object = objects_by_id.get(object_id)
        if data_object is None:
            raise HTTPException(
                status_code=400,
                detail=(
                    "JOIN_CONSISTENCY could not resolve dataset scope for data object version "
                    f"'{version_id}'"
                ),
            )
        dataset_id = str(getattr(data_object, "dataset_id", "") or "").strip()
        if not dataset_id:
            raise HTTPException(
                status_code=400,
                detail=(
                    "JOIN_CONSISTENCY data object version does not map to a dataset-level contract scope: "
                    f"'{version_id}'"
                ),
            )
        return dataset_id

    left_dataset_id = resolve_dataset_id(left_version_id)
    right_dataset_id = resolve_dataset_id(right_version_id)
    if left_dataset_id != right_dataset_id:
        raise HTTPException(
            status_code=400,
            detail=(
                "JOIN_CONSISTENCY requires left and right versions to belong to the same dataset-level contract scope "
                f"(left dataset '{left_dataset_id}', right dataset '{right_dataset_id}')"
            ),
        )

    left_attributes = {
        str(item.name or "").strip(): item
        for item in catalog_repository.list_attributes_catalog(left_version_id)
        if str(item.name or "").strip()
    }
    right_attributes = {
        str(item.name or "").strip(): item
        for item in catalog_repository.list_attributes_catalog(right_version_id)
        if str(item.name or "").strip()
    }

    def require_attribute(side: str, attribute_name: str) -> object:
        attribute_pool = left_attributes if side == "left" else right_attributes
        attribute = attribute_pool.get(attribute_name)
        if attribute is None:
            version_id = left_version_id if side == "left" else right_version_id
            raise HTTPException(
                status_code=400,
                detail=(
                    f"JOIN_CONSISTENCY {side} attribute '{attribute_name}' was not found in data object version "
                    f"'{version_id}'"
                ),
            )
        return attribute

    for join_key in params.get("joinKeys") or []:
        require_attribute("left", str(join_key.get("leftAttribute") or "").strip())
        require_attribute("right", str(join_key.get("rightAttribute") or "").strip())

    for comparison in params.get("comparisons") or []:
        require_attribute("left", str(comparison.get("leftAttribute") or "").strip())
        require_attribute("right", str(comparison.get("rightAttribute") or "").strip())

    actuality_date = dict(params.get("actualityDate") or {})
    left_actuality = require_attribute("left", str(actuality_date.get("leftAttribute") or "").strip())
    right_actuality = require_attribute("right", str(actuality_date.get("rightAttribute") or "").strip())
    if not rule_policy.is_temporal_attribute_type(getattr(left_actuality, "type", None)):
        raise HTTPException(
            status_code=400,
            detail="JOIN_CONSISTENCY left actuality-date attribute must be date/timestamp compatible",
        )
    if not rule_policy.is_temporal_attribute_type(getattr(right_actuality, "type", None)):
        raise HTTPException(
            status_code=400,
            detail="JOIN_CONSISTENCY right actuality-date attribute must be date/timestamp compatible",
        )

    contract_id = str(actuality_date.get("contractId") or "").strip()
    try:
        contract_policy = await contract_resolver.resolve_contract_policy(
            contract_id,
            dataset_id=left_dataset_id,
            cache_ttl_seconds=contract_cache_ttl_seconds,
        )
    except DataContractLookupError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc))

    override_value = actuality_date.get("overrideToleranceValue")
    override_unit = actuality_date.get("overrideToleranceUnit")
    override_requested = override_value is not None or override_unit is not None

    if override_requested and not contract_policy["overrideAllowed"]:
        raise HTTPException(
            status_code=400,
            detail=(
                f"JOIN_CONSISTENCY contract '{contract_id}' does not allow actuality-date tolerance overrides"
            ),
        )

    if override_requested:
        max_override_value = contract_policy.get("maxOverrideToleranceValue")
        max_override_unit = contract_policy.get("maxOverrideToleranceUnit")
        if max_override_value is not None and max_override_unit is not None:
            if str(override_unit or "").strip().lower() != str(max_override_unit).lower() or int(override_value) > int(max_override_value):
                raise HTTPException(
                    status_code=400,
                    detail=(
                        f"JOIN_CONSISTENCY override exceeds contract policy bound of {max_override_value} {max_override_unit}"
                    ),
                )
        actuality_date["resolvedToleranceValue"] = int(override_value)
        actuality_date["resolvedToleranceUnit"] = str(override_unit)
    else:
        actuality_date["resolvedToleranceValue"] = contract_policy["resolvedToleranceValue"]
        actuality_date["resolvedToleranceUnit"] = contract_policy["resolvedToleranceUnit"]

    actuality_date["contractVersion"] = contract_policy["contractVersion"]
    params["actualityDate"] = actuality_date
    return params