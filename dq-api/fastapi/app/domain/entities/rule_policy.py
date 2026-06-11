from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timezone
import json
from typing import Any

from fastapi import HTTPException
from pydantic import TypeAdapter
from pydantic import ValidationError

from app.application.services.check_type_expression_generator import generate_expression_from_check_type
from app.domain.status_governance import canonicalize_status
from app.domain.entities.rule import build_rule_taxonomy_entity
from app.domain.entities.rule_check_type import RuleCheckTypeParams


@dataclass(frozen=True, slots=True)
class RuleNameValue:
    raw: str
    normalized: str

    @classmethod
    def from_value(cls, value: str | None) -> "RuleNameValue":
        raw = str(value or "").strip()
        return cls(raw=raw, normalized=raw.lower())


@dataclass(frozen=True, slots=True)
class ReferentialIntegrityReference:
    data_object_version_id: str
    data_object_id: str
    attribute: str

    @classmethod
    def from_params(cls, params: dict[str, Any]) -> "ReferentialIntegrityReference":
        return cls(
            data_object_version_id=str(params.get("refDataObjectVersionId") or "").strip(),
            data_object_id=str(params.get("refDataObjectId") or "").strip(),
            attribute=str(params.get("refAttribute") or "").strip(),
        )


@dataclass(frozen=True, slots=True)
class RuleCheckTypeValidationResult:
    valid: bool
    normalized_params: dict[str, Any] | None
    message: str | None = None
    field_errors: dict[str, str] | None = None


def normalize_rule_name(value: str | None) -> str:
    return RuleNameValue.from_value(value).normalized


def _normalize_check_type_name(check_type: Any) -> str:
    raw_value = getattr(check_type, "value", check_type)
    return str(raw_value or "").strip().upper()


def _validation_error_to_field_errors(exc: ValidationError) -> dict[str, str]:
    field_errors: dict[str, str] = {}
    for error in exc.errors():
        loc = [str(part) for part in error.get("loc") or [] if str(part)]
        if not loc:
            continue
        field_name = next((part for part in reversed(loc) if part not in {"body", "input", "checkType", "check_type"}), loc[-1])
        message = str(error.get("msg") or "Invalid value")
        field_errors[field_name] = message
    if not field_errors:
        field_errors["checkTypeParams"] = "Invalid check type parameters."
    return field_errors


def _semantic_error_to_field_errors(check_type: str, message: str) -> dict[str, str]:
    normalized_message = message.strip().lower()
    if not normalized_message:
        return {}

    if "operator" in normalized_message and check_type.upper() == "THRESHOLD":
        return {"operator": "Use greater than or equal (>=) or less than or equal (<=)."}

    if "quantile" in normalized_message:
        return {"quantile": "Provide a quantile between 0 and 1."}

    if "range" in normalized_message and "minimum or maximum" in normalized_message:
        return {
            "minValue": "Provide at least one range boundary.",
            "maxValue": "Provide at least one range boundary.",
        }

    if "numeric tolerance" in normalized_message:
        return {"comparisonTolerance": "Provide a numeric tolerance for numeric_tolerance mode."}

    return {}


def validate_rule_check_type_params_detailed(
    *,
    check_type: str | None,
    check_type_params: dict | None,
) -> RuleCheckTypeValidationResult:
    normalized_check_type = _normalize_check_type_name(check_type)
    if not normalized_check_type or check_type_params is None:
        return RuleCheckTypeValidationResult(
            valid=True,
            normalized_params=check_type_params,
            message=None,
            field_errors={},
        )

    raw_params = dict(check_type_params)
    raw_params.setdefault("checkType", normalized_check_type)

    try:
        validated = TypeAdapter(RuleCheckTypeParams).validate_python(raw_params)
    except ValidationError as exc:
        field_errors = _validation_error_to_field_errors(exc)
        message = next(iter(field_errors.values()), str(exc))
        return RuleCheckTypeValidationResult(
            valid=False,
            normalized_params=None,
            message=message,
            field_errors=field_errors,
        )
    except ValueError as exc:
        message = str(exc)
        return RuleCheckTypeValidationResult(
            valid=False,
            normalized_params=None,
            message=message,
            field_errors={},
        )

    if hasattr(validated, "model_dump"):
        normalized_params = validated.model_dump(exclude_none=True) if normalized_check_type == "ROW_COUNT" else validated.model_dump()
    else:
        normalized_params = dict(validated)

    try:
        generate_expression_from_check_type(normalized_check_type, normalized_params)
    except ValueError as exc:
        message = str(exc)
        return RuleCheckTypeValidationResult(
            valid=False,
            normalized_params=normalized_params,
            message=message,
            field_errors=_semantic_error_to_field_errors(normalized_check_type, message),
        )

    return RuleCheckTypeValidationResult(
        valid=True,
        normalized_params=normalized_params,
        message=None,
        field_errors={},
    )


async def ensure_unique_rule_name(
    *,
    repository: Any,
    name: str,
    workspace: str,
    exclude_rule_id: str | None = None,
) -> None:
    candidate_name = RuleNameValue.from_value(name)
    if not candidate_name.normalized:
        raise HTTPException(status_code=400, detail="Rule name is required")

    existing = await repository.list_rule_records(
        workspace=workspace,
        include_deleted=False,
        is_template=False,
        limit=500,
        offset=0,
    )

    for row in existing:
        existing_id = str(read_row_field(row, "id") or "").strip()
        if exclude_rule_id and existing_id == exclude_rule_id:
            continue
        existing_name = RuleNameValue.from_value(str(read_row_field(row, "name") or ""))
        if existing_name.normalized == candidate_name.normalized:
            raise HTTPException(
                status_code=409,
                detail=f"A rule with name '{candidate_name.raw}' already exists in this workspace",
            )


def read_row_field(row: object, key: str) -> object:
    if isinstance(row, dict):
        return row.get(key)

    snake_key = "".join([f"_{c.lower()}" if c.isupper() else c for c in key]).lstrip("_")

    if hasattr(row, key):
        return getattr(row, key)
    if hasattr(row, snake_key):
        return getattr(row, snake_key)

    return None


def require_workspace(*values: object) -> str:
    for value in values:
        normalized = str(value or "").strip()
        if normalized:
            return normalized
    raise HTTPException(status_code=400, detail="Workspace is required")


def parse_effective_at_param(value: str | None) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None

    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except Exception as exc:
        raise HTTPException(status_code=422, detail="effective_at must be a valid RFC3339 timestamp") from exc

    if parsed.tzinfo is None or parsed.tzinfo.utcoffset(parsed) is None:
        raise HTTPException(status_code=422, detail="effective_at must include a timezone offset")

    return parsed.astimezone(timezone.utc)


def derive_rule_status_from_row(row: object) -> str:
    removed = read_row_field(row, "removed")
    removed_at = read_row_field(row, "removed_at")
    deleted_on = read_row_field(row, "deleted_on")
    if bool(removed) or bool(removed_at) or bool(deleted_on):
        return "removed"

    active = bool(read_row_field(row, "active"))
    if active:
        return "activated"

    approval_status = read_row_field(row, "last_approval_status")
    normalized = canonicalize_status(entity="rule", status=str(approval_status or ""))
    if normalized:
        return normalized

    return "draft"


def derive_rule_lifecycle_status_from_row(row: object) -> str:
    lifecycle_status = read_row_field(row, "lifecycle_status")
    normalized = canonicalize_status(entity="rule_lifecycle", status=str(lifecycle_status or ""))
    if normalized:
        return normalized

    removed = read_row_field(row, "removed")
    removed_at = read_row_field(row, "removed_at")
    deleted_on = read_row_field(row, "deleted_on")
    if bool(removed) or bool(removed_at) or bool(deleted_on):
        return "retired"

    return "active"


def parse_check_type_params(raw_value: object) -> dict | None:
    if raw_value is None:
        return None
    if isinstance(raw_value, dict):
        return raw_value
    if isinstance(raw_value, str):
        payload = raw_value.strip()
        if not payload:
            return None
        try:
            parsed = json.loads(payload)
            return parsed if isinstance(parsed, dict) else None
        except Exception:
            return None
    return None


def normalize_rule_row_contract(row: dict) -> dict:
    normalized = dict(row)
    raw_params = normalized.get("check_type_params")
    normalized_params = parse_check_type_params(raw_params)
    if normalized_params is not None:
        normalized["check_type_params"] = normalized_params
    normalized["taxonomy"] = build_rule_taxonomy_entity(
        workspace=str(normalized.get("workspace") or "").strip() or None,
        created_by=str(normalized.get("created_by") or "").strip() or None,
        created_by_user_id=str(normalized.get("created_by_user_id") or "").strip() or None,
        check_type=str(normalized.get("check_type") or "").strip() or None,
        dsl=normalized.get("dsl") if isinstance(normalized.get("dsl"), dict) else None,
        existing=normalized.get("taxonomy"),
    ).model_dump(mode="python", exclude_none=True)
    normalized["lifecycle_status"] = derive_rule_lifecycle_status_from_row(normalized)
    return normalized


def approval_timestamp_key(approval: dict) -> tuple[datetime, str]:
    raw_requested_at = approval.get("requestedAt") or approval.get("requested_at")
    timestamp = datetime.min.replace(tzinfo=UTC)
    if raw_requested_at:
        try:
            parsed = datetime.fromisoformat(str(raw_requested_at).replace("Z", "+00:00"))
            if parsed.tzinfo is not None and parsed.tzinfo.utcoffset(parsed) is not None:
                timestamp = parsed.astimezone(UTC)
        except (TypeError, ValueError):
            pass
    approval_id = str(approval.get("id") or "").strip()
    return timestamp, approval_id


def build_pending_deactivation_rule_ids(approvals: list[dict]) -> set[str]:
    latest_deactivation_by_rule: dict[str, tuple[tuple[datetime, str], str]] = {}
    for approval in approvals:
        rule_id = str(approval.get("ruleId") or approval.get("rule_id") or "").strip()
        status = str(approval.get("status") or "").strip().lower()
        request_type = str(approval.get("requestType") or approval.get("request_type") or "").strip().lower()
        if not rule_id or request_type != "deactivation":
            continue

        timestamp_key = approval_timestamp_key(approval)
        current = latest_deactivation_by_rule.get(rule_id)
        if current is None or timestamp_key >= current[0]:
            latest_deactivation_by_rule[rule_id] = (timestamp_key, status)

    return {
        rule_id
        for rule_id, (_, status) in latest_deactivation_by_rule.items()
        if status == "pending"
    }


def has_upstream_validation_issue(diagnostics: list[dict[str, Any]] | None) -> bool:
    if not diagnostics:
        return False
    for item in diagnostics:
        if not isinstance(item, dict):
            continue
        message = str(item.get("message") or "").strip().lower()
        if not message:
            continue
        if "upstream" in message or "econnrefused" in message:
            return True
    return False


def should_preserve_manual_expression(*, generated: bool | None, expression: str | None) -> bool:
    if generated is not False:
        return False
    return bool(str(expression or "").strip())


def validate_rule_check_type_params(
    *,
    check_type: str | None,
    check_type_params: dict | None,
) -> dict | None:
    result = validate_rule_check_type_params_detailed(
        check_type=check_type,
        check_type_params=check_type_params,
    )
    if not result.valid:
        raise HTTPException(status_code=400, detail=str(result.message or "Invalid check type parameters"))
    return result.normalized_params


def apply_threshold_default_from_config(
    *,
    check_type: str | None,
    check_type_params: dict | None,
    config_repository: Any,
) -> dict | None:
    if not check_type or str(check_type).upper() != "THRESHOLD":
        return check_type_params
    params = dict(check_type_params or {})
    if str(params.get("metric") or "null_pct").strip().lower() == "quantile":
        return params
    if params.get("threshold") is not None:
        return params
    app_config = config_repository.get_app_config()
    configured_threshold = getattr(app_config, "defaultRuleThresholdPct", None)
    if configured_threshold is None:
        raise HTTPException(status_code=503, detail="defaultRuleThresholdPct is required for THRESHOLD rules")
    try:
        params["threshold"] = float(configured_threshold)
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=503, detail="defaultRuleThresholdPct must be numeric") from exc
    return params


def resolve_openmetadata_contract_cache_ttl_seconds(config_repository: Any) -> int:
    app_config = config_repository.get_app_config()
    raw_ttl = getattr(app_config, "openMetadataContractCacheTtlSeconds", None)
    if raw_ttl is None:
        raise HTTPException(status_code=503, detail="openMetadataContractCacheTtlSeconds is required")
    try:
        return max(int(raw_ttl), 0)
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=503, detail="openMetadataContractCacheTtlSeconds must be an integer") from exc


def apply_referential_integrity_version_mapping(
    *,
    check_type: str | None,
    check_type_params: dict | None,
    catalog_repository: Any,
) -> dict | None:
    if not check_type or str(check_type).upper() != "REFERENTIAL_INTEGRITY":
        return check_type_params

    params = dict(check_type_params or {})
    reference = ReferentialIntegrityReference.from_params(params)
    if not reference.data_object_version_id:
        raise HTTPException(status_code=400, detail="REFERENTIAL_INTEGRITY check requires 'refDataObjectVersionId'")

    versions = catalog_repository.list_data_object_versions()
    target_version = next(
        (item for item in versions if str(item.id or "") == reference.data_object_version_id),
        None,
    )
    if target_version is None:
        raise HTTPException(
            status_code=400,
            detail=(
                "Reference data object version "
                f"'{reference.data_object_version_id}' was not found"
            ),
        )

    resolved_object_id = str(target_version.data_object_id or "").strip()
    if reference.data_object_id and resolved_object_id and reference.data_object_id != resolved_object_id:
        raise HTTPException(
            status_code=400,
            detail=(
                "Reference data object ID does not match the selected reference version "
                f"('{reference.data_object_id}' vs '{resolved_object_id}')"
            ),
        )
    if resolved_object_id:
        params["refDataObjectId"] = resolved_object_id

    attributes = catalog_repository.list_attributes_catalog(reference.data_object_version_id)
    attribute_names = {str(item.name or "").strip() for item in attributes if str(item.name or "").strip()}
    if reference.attribute and attribute_names and reference.attribute not in attribute_names:
        raise HTTPException(
            status_code=400,
            detail=(
                "Reference attribute "
                f"'{reference.attribute}' is not present in reference version "
                f"'{reference.data_object_version_id}'"
            ),
        )

    return params


def is_temporal_attribute_type(attribute_type: str | None) -> bool:
    normalized = str(attribute_type or "").strip().lower()
    return any(token in normalized for token in ("date", "time", "timestamp", "datetime"))