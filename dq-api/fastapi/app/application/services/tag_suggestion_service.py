from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from app.domain.entities.suggestions import TagSuggestionEntity
from app.domain.interfaces import DataAssetRepository
from app.domain.interfaces import DataCatalogRepository
from app.domain.interfaces import RulesRepository


def _normalize_tag(value: object) -> str:
    return str(value or "").strip()


def _normalize_tag_key(value: object) -> str:
    return _normalize_tag(value).lower()


def _iter_unique_tags(values: Iterable[object]) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()
    for value in values:
        tag = _normalize_tag(value)
        if not tag:
            continue
        key = tag.lower()
        if key in seen:
            continue
        seen.add(key)
        normalized.append(tag)
    return normalized


@dataclass(slots=True)
class TagSuggestionService:
    rules_repository: RulesRepository
    data_catalog_repository: DataCatalogRepository
    data_asset_repository: DataAssetRepository

    async def list_tag_suggestions(self, *, query: str | None = None, limit: int = 20) -> list[TagSuggestionEntity]:
        tag_buckets: dict[str, dict[str, object]] = {}

        async def _bump(tag_value: object, *, source: str, display_name: str | None = None) -> None:
            tag = _normalize_tag(tag_value)
            if not tag:
                return

            key = tag.lower()
            bucket = tag_buckets.get(key)
            if bucket is None:
                bucket = {
                    "id": tag,
                    "name": display_name or tag,
                    "usage_count": 0,
                    "sources": set(),
                }
                tag_buckets[key] = bucket

            bucket["usage_count"] = int(bucket["usage_count"]) + 1
            sources = bucket["sources"]
            if isinstance(sources, set):
                sources.add(source)

        rule_tag_ids: list[str] = []
        for record in await self.rules_repository.list_rule_records():
            record_tag_ids = _iter_unique_tags(getattr(record, "tagIds", None) or getattr(record, "tag_ids", None) or [])
            rule_tag_ids.extend(record_tag_ids)

        if rule_tag_ids:
            resolved_tags = await self.rules_repository.get_tags_by_ids(rule_tag_ids)
            tag_names_by_id = {
                _normalize_tag_key(tag.id): _normalize_tag(tag.name) or _normalize_tag(tag.id)
                for tag in resolved_tags
                if _normalize_tag(tag.id)
            }
            for tag_id in rule_tag_ids:
                display_name = tag_names_by_id.get(_normalize_tag_key(tag_id), tag_id)
                await _bump(display_name, source="rule", display_name=display_name)

        for product in self.data_catalog_repository.list_data_products():
            for tag in _iter_unique_tags(getattr(product, "tags", []) or []):
                await _bump(tag, source="data_product")

        for data_set in self.data_catalog_repository.list_data_sets():
            for tag in _iter_unique_tags(getattr(data_set, "tags", []) or []):
                await _bump(tag, source="data_set")

        for row in self.data_catalog_repository.list_data_objects_catalog():
            for tag in _iter_unique_tags(getattr(row, "tags", []) or []):
                await _bump(tag, source="data_object")

        for version in self.data_catalog_repository.list_data_object_versions():
            for tag in _iter_unique_tags(getattr(version, "tags", []) or []):
                await _bump(tag, source="data_object_version")

        for attribute in self.data_catalog_repository.list_attributes_catalog():
            for tag in _iter_unique_tags(getattr(attribute, "tags", []) or []):
                await _bump(tag, source="attribute")

        for asset in self.data_asset_repository.list_data_assets():
            business_context = getattr(asset, "business_context", None)
            for tag in _iter_unique_tags(getattr(business_context, "tags", []) or []):
                await _bump(tag, source="data_asset")

        suggestions = list(tag_buckets.values())
        if query is not None and str(query).strip():
            normalized_query = str(query).strip().lower()
            suggestions = [
                suggestion
                for suggestion in suggestions
                if normalized_query in str(suggestion["id"]).lower() or normalized_query in str(suggestion["name"]).lower()
            ]

        suggestions.sort(
            key=lambda item: (
                -int(item["usage_count"]),
                str(item["name"]).lower(),
                str(item["id"]).lower(),
            )
        )

        limited_suggestions = suggestions[: max(0, limit)]
        return [
            TagSuggestionEntity(
                id=str(item["id"]),
                name=str(item["name"]),
                usage_count=int(item["usage_count"]),
                source_count=len(item["sources"]) if isinstance(item.get("sources"), set) else 0,
            )
            for item in limited_suggestions
        ]