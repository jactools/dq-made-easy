from __future__ import annotations

from collections.abc import Mapping
from typing import Any


_LOGICAL_TYPE_ALIASES = {
    "char": "string",
    "date-time": "datetime",
    "datetime": "datetime",
    "datetimeoffset": "datetime",
    "double": "number",
    "float": "number",
    "int": "integer",
    "integer": "integer",
    "long": "integer",
    "number": "number",
    "numeric": "number",
    "smallint": "integer",
    "string": "string",
    "text": "string",
    "timestamp": "datetime",
    "uuid": "string",
    "varchar": "string",
    "bool": "boolean",
    "boolean": "boolean",
    "date": "date",
    "object": "object",
    "array": "array",
}


def _clean_text(value: Any) -> str:
    return str(value or "").strip()


def _clean_optional_text(value: Any) -> str | None:
    normalized = _clean_text(value)
    return normalized or None


def _coerce_bool(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    normalized = _clean_text(value).lower()
    if not normalized:
        return default
    return normalized in {"1", "true", "yes", "y", "on"}


def _normalize_logical_type(value: Any) -> str:
    normalized = _clean_text(value).lower()
    if not normalized:
        return "string"
    return _LOGICAL_TYPE_ALIASES.get(normalized, normalized)


def _schema_entry(contract_payload: Mapping[str, Any]) -> dict[str, Any]:
    schema = contract_payload.get("schema")
    if isinstance(schema, list):
        for item in schema:
            if isinstance(item, Mapping):
                return dict(item)
    if isinstance(schema, Mapping):
        return dict(schema)
    return {}


def _property_items(schema_entry: Mapping[str, Any]) -> list[dict[str, Any]]:
    properties = schema_entry.get("properties")
    if isinstance(properties, list):
        return [dict(item) for item in properties if isinstance(item, Mapping)]
    if isinstance(properties, Mapping):
        return [
            dict({"name": key, **value}) if isinstance(value, Mapping) else {"name": key, "logicalType": value}
            for key, value in properties.items()
        ]
    return []


def normalize_contract_field(property_payload: Mapping[str, Any]) -> dict[str, Any]:
    field_name = _clean_optional_text(property_payload.get("name"))
    if not field_name:
        field_name = _clean_optional_text(property_payload.get("field"))
    if not field_name:
        field_name = _clean_optional_text(property_payload.get("property"))
    if not field_name:
        field_name = ""

    required = _coerce_bool(property_payload.get("required"), default=False)
    nullable = _coerce_bool(property_payload.get("nullable"), default=not required)

    return {
        "name": field_name,
        "logical_type": _normalize_logical_type(
            property_payload.get("logicalType")
            or property_payload.get("logical_type")
            or property_payload.get("type")
            or property_payload.get("data_type")
        ),
        "physical_type": _clean_text(
            property_payload.get("physicalType")
            or property_payload.get("physical_type")
            or property_payload.get("databaseType")
            or property_payload.get("data_type")
        ).upper() or "STRING",
        "description": _clean_optional_text(property_payload.get("description")),
        "required": required,
        "nullable": nullable,
        "unique": _coerce_bool(property_payload.get("unique"), default=False),
        "classification": _clean_optional_text(property_payload.get("classification")) or "public",
        "primary_key": _coerce_bool(property_payload.get("primaryKey"), default=False),
        "primary_key_position": property_payload.get("primaryKeyPosition"),
    }


def build_canonical_contract_snapshot(
    contract_payload: Mapping[str, Any],
    *,
    data_source_id: str,
    source_kind: str,
) -> dict[str, Any]:
    schema_entry = _schema_entry(contract_payload)
    fields = [normalize_contract_field(item) for item in _property_items(schema_entry)]

    return {
        "data_source_id": _clean_text(data_source_id),
        "source_kind": _clean_text(source_kind) or "unknown",
        "api_version": _clean_text(contract_payload.get("apiVersion") or contract_payload.get("api_version")),
        "kind": _clean_text(contract_payload.get("kind")),
        "contract_id": _clean_text(contract_payload.get("id")),
        "name": _clean_text(contract_payload.get("name")),
        "version": _clean_text(contract_payload.get("version")),
        "status": _clean_text(contract_payload.get("status") or "active") or "active",
        "domain": _clean_text(contract_payload.get("domain")),
        "owner": contract_payload.get("owner") if isinstance(contract_payload.get("owner"), Mapping) else {},
        "contact": contract_payload.get("contact") if isinstance(contract_payload.get("contact"), Mapping) else {},
        "description": contract_payload.get("description") if isinstance(contract_payload.get("description"), Mapping) else {},
        "schema": {
            "name": _clean_text(schema_entry.get("name")),
            "logical_type": _normalize_logical_type(schema_entry.get("logicalType") or schema_entry.get("logical_type") or schema_entry.get("type")),
            "physical_type": _clean_text(schema_entry.get("physicalType") or schema_entry.get("physical_type") or schema_entry.get("type")).upper() or "OBJECT",
            "description": _clean_optional_text(schema_entry.get("description")),
            "fields": fields,
        },
        "quality": contract_payload.get("quality") if isinstance(contract_payload.get("quality"), Mapping) else {},
    }


def _field_map(snapshot: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    schema = snapshot.get("schema")
    fields = schema.get("fields") if isinstance(schema, Mapping) else []
    return {str(field.get("name") or ""): dict(field) for field in fields if isinstance(field, Mapping) and str(field.get("name") or "").strip()}


def diff_contract_snapshots(previous_snapshot: Mapping[str, Any], current_snapshot: Mapping[str, Any]) -> dict[str, Any]:
    previous_fields = _field_map(previous_snapshot)
    current_fields = _field_map(current_snapshot)

    changes: list[dict[str, Any]] = []
    breaking_count = 0
    compatible_count = 0
    additive_count = 0

    for field_name in sorted(previous_fields):
        if field_name not in current_fields:
            breaking_count += 1
            changes.append(
                {
                    "field_name": field_name,
                    "change_type": "removed",
                    "severity": "breaking",
                    "message": f"Field '{field_name}' was removed",
                    "previous": previous_fields[field_name],
                    "current": None,
                }
            )

    for field_name in sorted(current_fields):
        current_field = current_fields[field_name]
        previous_field = previous_fields.get(field_name)
        if previous_field is None:
            additive_count += 1
            severity = "breaking" if _coerce_bool(current_field.get("required"), default=False) else "additive"
            if severity == "breaking":
                breaking_count += 1
            changes.append(
                {
                    "field_name": field_name,
                    "change_type": "added",
                    "severity": severity,
                    "message": f"Field '{field_name}' was added",
                    "previous": None,
                    "current": current_field,
                }
            )
            continue

        field_changes: list[str] = []
        severity = "compatible"
        if _normalize_logical_type(previous_field.get("logical_type")) != _normalize_logical_type(current_field.get("logical_type")):
            severity = "breaking"
            field_changes.append(
                f"logical type changed from {previous_field.get('logical_type')} to {current_field.get('logical_type')}"
            )
        if bool(previous_field.get("nullable", True)) and not bool(current_field.get("nullable", True)):
            severity = "breaking"
            field_changes.append("field became non-nullable")
        if not bool(previous_field.get("required", False)) and bool(current_field.get("required", False)):
            severity = "breaking"
            field_changes.append("field became required")
        if bool(previous_field.get("required", False)) and not bool(current_field.get("required", False)):
            field_changes.append("field became optional")
        if not bool(previous_field.get("nullable", True)) and bool(current_field.get("nullable", True)):
            field_changes.append("field became nullable")
        if previous_field.get("classification") != current_field.get("classification"):
            field_changes.append(
                f"classification changed from {previous_field.get('classification')} to {current_field.get('classification')}"
            )
        if previous_field.get("description") != current_field.get("description"):
            field_changes.append("description changed")

        if field_changes:
            if severity == "breaking":
                breaking_count += 1
            else:
                compatible_count += 1
            changes.append(
                {
                    "field_name": field_name,
                    "change_type": "modified",
                    "severity": severity,
                    "message": "; ".join(field_changes),
                    "previous": previous_field,
                    "current": current_field,
                }
            )

    if breaking_count > 0:
        change_classification = "breaking"
    elif additive_count > 0:
        change_classification = "additive"
    elif compatible_count > 0:
        change_classification = "compatible"
    else:
        change_classification = "identical"

    return {
        "previous_version": _clean_text(previous_snapshot.get("version")),
        "current_version": _clean_text(current_snapshot.get("version")),
        "change_classification": change_classification,
        "summary": {
            "breaking_changes": breaking_count,
            "compatible_changes": compatible_count,
            "additive_changes": additive_count,
            "total_changes": len(changes),
        },
        "changes": changes,
    }


def build_observed_fields_from_data_asset_version(version: Any) -> list[dict[str, Any]]:
    observed_fields: list[dict[str, Any]] = []
    observed_names: set[str] = set()

    def _append_field(name: str, logical_type: str, physical_type: str, nullable: bool) -> None:
        normalized_name = _clean_text(name)
        if not normalized_name or normalized_name in observed_names:
            return
        observed_names.add(normalized_name)
        observed_fields.append(
            {
                "name": normalized_name,
                "logical_type": _normalize_logical_type(logical_type),
                "physical_type": _clean_text(physical_type).upper() or "STRING",
                "description": None,
                "required": not nullable,
                "nullable": nullable,
                "unique": False,
                "classification": "public",
                "primary_key": False,
                "primary_key_position": None,
            }
        )

    for binding in getattr(version, "source_bindings", []) or []:
        _append_field(
            getattr(binding, "source_field_name", "") or getattr(binding, "source_field_id", ""),
            getattr(binding, "source_field_type", "") or "string",
            getattr(binding, "source_field_type", "") or "string",
            bool(getattr(binding, "nullable", True)),
        )

    for derived_field in getattr(version, "derived_fields", []) or []:
        _append_field(
            getattr(derived_field, "name", ""),
            getattr(derived_field, "data_type", "") or "string",
            getattr(derived_field, "data_type", "") or "string",
            bool(getattr(derived_field, "nullable", True)) if getattr(derived_field, "nullable", None) is not None else True,
        )

    upload_preview = getattr(version, "upload_preview", None)
    for preview_column in getattr(upload_preview, "columns", []) or []:
        _append_field(
            getattr(preview_column, "name", ""),
            getattr(preview_column, "data_type", "") or "string",
            getattr(preview_column, "data_type", "") or "string",
            bool(getattr(preview_column, "nullable", True)),
        )

    return observed_fields


def validate_contract_conformance(
    contract_snapshot: Mapping[str, Any],
    observed_fields: list[Mapping[str, Any]],
) -> dict[str, Any]:
    contract_fields = _field_map(contract_snapshot)
    observed_field_map = {
        str(field.get("name") or ""): dict(field)
        for field in observed_fields
        if isinstance(field, Mapping) and str(field.get("name") or "").strip()
    }

    issues: list[dict[str, Any]] = []
    breaking_issues = 0
    warning_issues = 0

    for field_name, contract_field in sorted(contract_fields.items()):
        observed_field = observed_field_map.get(field_name)
        if observed_field is None:
            if bool(contract_field.get("required", False)):
                breaking_issues += 1
                issues.append(
                    {
                        "field_name": field_name,
                        "issue_type": "missing_required_field",
                        "severity": "breaking",
                        "message": f"Required field '{field_name}' is missing from the observed schema",
                    }
                )
            else:
                warning_issues += 1
                issues.append(
                    {
                        "field_name": field_name,
                        "issue_type": "missing_optional_field",
                        "severity": "warning",
                        "message": f"Optional field '{field_name}' is missing from the observed schema",
                    }
                )
            continue

        if _normalize_logical_type(contract_field.get("logical_type")) != _normalize_logical_type(observed_field.get("logical_type")):
            breaking_issues += 1
            issues.append(
                {
                    "field_name": field_name,
                    "issue_type": "logical_type_mismatch",
                    "severity": "breaking",
                    "message": (
                        f"Field '{field_name}' has logical type {observed_field.get('logical_type')} "
                        f"but the contract expects {contract_field.get('logical_type')}"
                    ),
                }
            )

        if bool(contract_field.get("required", False)) and bool(observed_field.get("nullable", True)):
            breaking_issues += 1
            issues.append(
                {
                    "field_name": field_name,
                    "issue_type": "nullable_mismatch",
                    "severity": "breaking",
                    "message": f"Field '{field_name}' is nullable in the observed schema but required by the contract",
                }
            )

    for field_name in sorted(observed_field_map):
        if field_name not in contract_fields:
            warning_issues += 1
            issues.append(
                {
                    "field_name": field_name,
                    "issue_type": "undocumented_field",
                    "severity": "warning",
                    "message": f"Field '{field_name}' exists in the observed schema but is not defined by the contract",
                }
            )

    return {
        "ok": breaking_issues == 0,
        "summary": {
            "breaking_issues": breaking_issues,
            "warning_issues": warning_issues,
            "total_issues": len(issues),
        },
        "issues": issues,
    }