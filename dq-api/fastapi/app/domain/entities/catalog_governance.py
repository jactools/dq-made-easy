from __future__ import annotations

from collections.abc import Iterable, Mapping
import json
from typing import Any

from app.domain.entities.base import EntityModel


class CatalogTermEntity(EntityModel):
    termKey: str
    termName: str
    description: str
    dataType: str = ""
    domain: str = "catalog"
    glossaryId: str


class AliasResolutionEntity(EntityModel):
    aliasName: str
    source: str
    resolvedTermKey: str | None = None
    resolvedTermName: str | None = None
    resolvedDataType: str | None = None
    domain: str | None = None
    confidence: float = 0.0


def catalog_term_key_from_name(name: str) -> str:
    return "_".join(part for part in str(name or "").strip().lower().replace("-", " ").split(" ") if part)


def build_catalog_term_entities(rows: Iterable[Any]) -> list[CatalogTermEntity]:
    terms_by_key: dict[str, CatalogTermEntity] = {}
    for row in rows:
        name = str(getattr(row, "name", "") or "").strip()
        if not name:
            continue
        term_key = catalog_term_key_from_name(name)
        if not term_key or term_key in terms_by_key:
            continue
        row_id = str(getattr(row, "id", "") or term_key).strip() or term_key
        terms_by_key[term_key] = CatalogTermEntity(
            termKey=term_key,
            termName=name,
            description=f"Catalog attribute {name}",
            dataType=str(getattr(row, "type", "") or ""),
            domain=str(getattr(row, "data_object_id", "") or "catalog"),
            glossaryId=f"attr-{row_id}",
        )
    return sorted(terms_by_key.values(), key=lambda value: str(value.termName or "").lower())


def extract_rule_aliases(rule_payload: Any) -> list[str]:
    if not isinstance(rule_payload, Mapping):
        return []
    raw = rule_payload.get("alias_mappings")
    if not isinstance(raw, Mapping):
        raw = rule_payload.get("aliasMappings")
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except json.JSONDecodeError:
            raw = None
    if not isinstance(raw, Mapping):
        return []
    aliases = [str(key or "").strip() for key in raw.keys()]
    return [alias for alias in aliases if alias]


def extract_rule_aliases_from_record(rule_record: object) -> list[str]:
    if isinstance(rule_record, Mapping):
        return extract_rule_aliases(rule_record)
    to_payload = getattr(rule_record, "to_payload", None)
    if callable(to_payload):
        payload = to_payload()
        if isinstance(payload, Mapping):
            return extract_rule_aliases(payload)
    return []


def resolve_rule_aliases(
    aliases: Iterable[Any],
    manual_mappings: Mapping[str, Any] | None,
    catalog_terms: Iterable[CatalogTermEntity],
) -> dict[str, dict[str, Any]]:
    catalog_lookup = {
        str(term.termName or "").strip().lower(): term
        for term in catalog_terms
        if str(term.termName or "").strip()
    }
    manual_lookup = dict(manual_mappings or {})
    resolutions: dict[str, dict[str, Any]] = {}
    for alias in aliases:
        normalized = str(alias or "").strip()
        if not normalized:
            continue

        manual_value = str(manual_lookup.get(normalized) or "").strip()
        if manual_value:
            entity = AliasResolutionEntity(
                aliasName=normalized,
                source="manual",
                resolvedTermKey=manual_value,
                resolvedTermName=manual_value,
                resolvedDataType=None,
                domain=None,
                confidence=1.0,
            )
        else:
            catalog_term = catalog_lookup.get(normalized.lower())
            if catalog_term is not None:
                entity = AliasResolutionEntity(
                    aliasName=normalized,
                    source="catalog",
                    resolvedTermKey=catalog_term.termKey,
                    resolvedTermName=catalog_term.termName,
                    resolvedDataType=catalog_term.dataType or None,
                    domain=catalog_term.domain or None,
                    confidence=0.8,
                )
            else:
                entity = AliasResolutionEntity(
                    aliasName=normalized,
                    source="unresolved",
                    resolvedTermKey=None,
                    resolvedTermName=None,
                    resolvedDataType=None,
                    domain=None,
                    confidence=0.0,
                )
        resolutions[normalized] = entity.model_dump(mode="python")
    return resolutions


def detect_rule_drifts(
    *,
    rule_record: object,
    rule_attributes: Iterable[Any],
    catalog_attributes: Iterable[Any],
    data_objects_catalog: Iterable[Any],
    detected_at: str,
) -> dict[str, Any]:
    catalog_rows = list(catalog_attributes)
    term_keys = {
        catalog_term_key_from_name(_read_value(attribute, "name"))
        for attribute in catalog_rows
        if str(_read_value(attribute, "name") or "").strip()
    }

    drifts: list[dict[str, Any]] = []
    affected_aliases: dict[str, str] = {}
    seen_alias_drifts: set[str] = set()
    for alias in extract_rule_aliases_from_record(rule_record):
        normalized_alias = catalog_term_key_from_name(alias)
        if normalized_alias in term_keys or normalized_alias in seen_alias_drifts:
            continue
        seen_alias_drifts.add(normalized_alias)
        affected_aliases.setdefault(normalized_alias, alias)
        drifts.append(
            {
                "driftType": "alias_unresolved",
                "aliasName": alias,
                "resolvedTermName": alias,
                "previousValue": "mapped",
                "currentValue": "unresolved",
                "severity": "warning",
                "detectedAt": detected_at,
            }
        )

    rule_id = str(_read_value(rule_record, "id") or "").strip()
    if not rule_id:
        return {
            "affected_aliases": sorted(affected_aliases.values(), key=lambda value: value.lower()),
            "drifts": drifts,
            "total_drifts": len(drifts),
            "needs_revalidation": len(drifts) > 0,
        }

    attribute_by_id = {
        str(_read_value(attribute, "id") or "").strip(): attribute
        for attribute in catalog_rows
        if str(_read_value(attribute, "id") or "").strip()
    }
    latest_version_by_object = {
        str(_read_value(data_object, "id") or "").strip(): str(_read_value(data_object, "latest_version_id") or "").strip()
        for data_object in data_objects_catalog
        if str(_read_value(data_object, "id") or "").strip()
    }
    latest_attributes_by_object_and_name: dict[tuple[str, str], Any] = {}
    for attribute in catalog_rows:
        data_object_id = str(_read_value(attribute, "data_object_id") or "").strip()
        latest_version_id = latest_version_by_object.get(data_object_id)
        attribute_version_id = str(_read_value(attribute, "version_id") or "").strip()
        if not data_object_id or not latest_version_id or attribute_version_id != latest_version_id:
            continue
        attribute_name = _normalize_name(_read_value(attribute, "name"))
        if not attribute_name:
            continue
        latest_attributes_by_object_and_name[(data_object_id, attribute_name)] = attribute

    seen_type_drifts: set[tuple[str, str, str]] = set()
    for rule_attribute in rule_attributes:
        if str(_read_value(rule_attribute, "ruleId") or "").strip() != rule_id:
            continue
        source_attribute = attribute_by_id.get(str(_read_value(rule_attribute, "attributeId") or "").strip())
        if source_attribute is None:
            continue

        data_object_id = str(_read_value(source_attribute, "data_object_id") or "").strip()
        latest_version_id = latest_version_by_object.get(data_object_id)
        source_version_id = str(_read_value(source_attribute, "version_id") or "").strip()
        if not data_object_id or not latest_version_id or not source_version_id or source_version_id == latest_version_id:
            continue

        source_name = str(_read_value(source_attribute, "name") or "").strip()
        normalized_source_name = _normalize_name(source_name)
        if not normalized_source_name:
            continue
        latest_attribute = latest_attributes_by_object_and_name.get((data_object_id, normalized_source_name))
        if latest_attribute is None:
            continue

        previous_type = str(_read_value(source_attribute, "type") or "").strip()
        current_type = str(_read_value(latest_attribute, "type") or "").strip()
        if not previous_type or not current_type or previous_type.lower() == current_type.lower():
            continue

        drift_key = (normalized_source_name, previous_type.lower(), current_type.lower())
        if drift_key in seen_type_drifts:
            continue
        seen_type_drifts.add(drift_key)
        affected_aliases[normalized_source_name] = source_name
        drifts.append(
            {
                "driftType": "data_type_changed",
                "aliasName": source_name,
                "resolvedTermName": str(_read_value(latest_attribute, "name") or source_name).strip() or source_name,
                "previousValue": previous_type.upper(),
                "currentValue": current_type.upper(),
                "severity": "critical",
                "detectedAt": detected_at,
            }
        )

    return {
        "affected_aliases": sorted(affected_aliases.values(), key=lambda value: value.lower()),
        "drifts": drifts,
        "total_drifts": len(drifts),
        "needs_revalidation": len(drifts) > 0,
    }


def _read_value(row: object, key: str) -> Any:
    if isinstance(row, Mapping):
        if key in row:
            return row.get(key)
        camel_key = _snake_to_camel(key)
        if camel_key in row:
            return row.get(camel_key)

    snake_key = "".join([f"_{char.lower()}" if char.isupper() else char for char in key]).lstrip("_")
    camel_key = _snake_to_camel(key)

    if hasattr(row, key):
        return getattr(row, key)
    if hasattr(row, snake_key):
        return getattr(row, snake_key)
    if hasattr(row, camel_key):
        return getattr(row, camel_key)

    to_payload = getattr(row, "to_payload", None)
    if callable(to_payload):
        payload = to_payload()
        if isinstance(payload, Mapping):
            return _read_value(payload, key)
    return None


def _normalize_name(value: Any) -> str:
    return str(value or "").strip().lower()


def _snake_to_camel(value: str) -> str:
    parts = str(value or "").split("_")
    if not parts:
        return ""
    return parts[0] + "".join(part[:1].upper() + part[1:] for part in parts[1:])
