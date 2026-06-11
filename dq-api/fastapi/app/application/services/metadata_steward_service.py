from __future__ import annotations

from typing import Any

from app.application.services.registry_definition_resolver import RegistryDefinitionLookupError
from app.application.services.registry_definition_resolver import RegistryDefinitionResolver
from app.domain.interfaces.v1.data_catalog_repository import DataCatalogRepository


class MetadataStewardLookupError(RuntimeError):
	def __init__(self, message: str, *, status_code: int = 400) -> None:
		super().__init__(message)
		self.status_code = status_code


def _normalize_text(value: Any) -> str:
	return str(value or "").strip()


def _build_fix_list(*, facts: dict[str, Any]) -> list[str]:
	fixes: list[str] = []
	target_type = _normalize_text(facts.get("target_type")).lower()

	if target_type == "data_object_version":
		storage_uri = _normalize_text(facts.get("storage_uri"))
		if not storage_uri:
			fixes.append("Persist the data object version in object storage and record its storage_uri.")

		storage_format = _normalize_text(facts.get("storage_format"))
		if not storage_format:
			fixes.append("Set a storage format so the steward can describe the persisted artifact clearly.")
		elif storage_format.lower() not in {"parquet", "csv", "json", "avro", "delta", "iceberg"}:
			fixes.append(f"Review the storage format '{storage_format}' and align it with the supported delivery formats.")

		if int(facts.get("primary_key_attribute_count") or 0) == 0:
			fixes.append("Mark at least one attribute as a primary key to strengthen stewardship and lookup.")

		if int(facts.get("business_key_attribute_count") or 0) == 0:
			fixes.append("Define business key attributes so the steward can explain the record identity.")

		if int(facts.get("unmapped_attribute_count") or 0) > 0:
			fixes.append("Map the unmapped attributes to glossary definitions to improve metadata explainability.")

	if target_type == "glossary_term":
		if int(facts.get("child_definition_count") or 0) > 0 and not _normalize_text(facts.get("parent_definition_name")):
			fixes.append("Place the glossary term under a parent definition to make the hierarchy explicit.")

		if not _normalize_text(facts.get("business_definition")):
			fixes.append("Add a business definition so the steward can explain the term to downstream users.")

		if not _normalize_text(facts.get("owner")):
			fixes.append("Assign an owner or steward to the glossary term.")

		if not _normalize_text(facts.get("synonyms")):
			fixes.append("Add synonyms to improve searchability and steward recommendations.")

	return fixes


async def build_metadata_steward_payload(
	*,
	prompt: str,
	current_workspace_id: str,
	target_type: str,
	target_id: str,
	catalog_repository: DataCatalogRepository,
	registry_definition_resolver: RegistryDefinitionResolver,
) -> dict[str, Any]:
	normalized_target_type = _normalize_text(target_type).lower()
	normalized_target_id = _normalize_text(target_id)
	normalized_prompt = _normalize_text(prompt)
	normalized_workspace_id = _normalize_text(current_workspace_id)
	if not normalized_workspace_id:
		raise MetadataStewardLookupError("metadata steward requests require 'current_workspace_id'", status_code=400)
	if not normalized_target_type:
		raise MetadataStewardLookupError("metadata steward requests require 'target_type'", status_code=400)
	if not normalized_target_id:
		raise MetadataStewardLookupError("metadata steward requests require 'target_id'", status_code=400)

	if normalized_target_type == "data_object_version":
		version = catalog_repository.get_data_object_version(normalized_target_id)
		if version is None:
			raise MetadataStewardLookupError(
				f"Data object version '{normalized_target_id}' was not found in the catalog",
				status_code=404,
			)

		data_objects = catalog_repository.list_data_objects_catalog()
		data_object = next((row for row in data_objects if _normalize_text(getattr(row, "id", "")) == _normalize_text(version.data_object_id)), None)
		if data_object is None:
			raise MetadataStewardLookupError(
				f"Data object '{version.data_object_id}' for version '{normalized_target_id}' was not found in the catalog",
				status_code=404,
			)

		datasets = catalog_repository.list_data_sets()
		dataset = next((row for row in datasets if _normalize_text(getattr(row, "id", "")) == _normalize_text(data_object.dataset_id)), None)
		if dataset is None:
			raise MetadataStewardLookupError(
				f"Data set '{data_object.dataset_id}' for version '{normalized_target_id}' was not found in the catalog",
				status_code=404,
			)

		products = catalog_repository.list_data_products(workspace=normalized_workspace_id)
		product = next((row for row in products if _normalize_text(getattr(row, "id", "")) == _normalize_text(dataset.product_id)), None)
		if product is None:
			raise MetadataStewardLookupError(
				f"Data product '{dataset.product_id}' for version '{normalized_target_id}' was not found in the workspace catalog",
				status_code=404,
			)

		attributes = catalog_repository.list_attributes_catalog(version_id=normalized_target_id)
		attribute_definition_mappings = catalog_repository.list_attribute_definition_mappings(version_id=normalized_target_id)
		mapped_attribute_ids = {
			_normalize_text(getattr(mapping, "attribute_id", ""))
			for mapping in attribute_definition_mappings
			if _normalize_text(getattr(mapping, "attribute_id", ""))
		}
		primary_key_attribute_names = [
			_normalize_text(getattr(attribute, "name", ""))
			for attribute in attributes
			if bool(getattr(attribute, "is_primary_key", False))
		]
		business_key_attribute_names = [
			_normalize_text(getattr(attribute, "name", ""))
			for attribute in attributes
			if bool(getattr(attribute, "is_business_key", False))
		]
		unmapped_attribute_count = sum(
			1
			for attribute in attributes
			if _normalize_text(getattr(attribute, "definition_id", "")) == ""
			and _normalize_text(getattr(attribute, "definition_mapping_status", "")).lower() not in {"explicit", "mapped"}
			and _normalize_text(getattr(attribute, "id", "")) not in mapped_attribute_ids
		)
		facts = {
			"target_type": normalized_target_type,
			"target_id": normalized_target_id,
			"target_label": _normalize_text(getattr(data_object, "name", "")) or normalized_target_id,
			"workspace_id": normalized_workspace_id,
			"data_product_id": _normalize_text(getattr(product, "id", "")),
			"data_product_name": _normalize_text(getattr(product, "name", "")),
			"data_set_id": _normalize_text(getattr(dataset, "id", "")),
			"data_set_name": _normalize_text(getattr(dataset, "name", "")),
			"data_object_id": _normalize_text(getattr(data_object, "id", "")),
			"data_object_name": _normalize_text(getattr(data_object, "name", "")),
			"data_object_description": _normalize_text(getattr(data_object, "description", "")),
			"storage_uri": _normalize_text(getattr(version, "storage_uri", "")),
			"storage_format": _normalize_text(getattr(version, "storage_format", "")),
			"attribute_count": int(getattr(version, "attribute_count", 0) or 0),
			"primary_key_attribute_count": len(primary_key_attribute_names),
			"primary_key_attributes": primary_key_attribute_names,
			"business_key_attribute_count": len(business_key_attribute_names),
			"business_key_attributes": business_key_attribute_names,
			"mapped_attribute_count": len(attributes) - unmapped_attribute_count,
			"unmapped_attribute_count": unmapped_attribute_count,
			"attribute_names": [_normalize_text(getattr(attribute, "name", "")) for attribute in attributes],
		}
		suggested_fixes = _build_fix_list(facts=facts)
		summary = (
			f"Data object version '{facts['target_label']}' is stored as {facts['storage_format'] or 'an unspecified format'} "
			f"in {facts['data_set_name']} / {facts['data_product_name']}."
		)
		explanation = (
			f"The steward reviewed {facts['attribute_count']} attributes for data object version '{facts['target_label']}'. "
			f"The version is linked to dataset '{facts['data_set_name']}' and product '{facts['data_product_name']}'."
		)
		if normalized_prompt:
			explanation = f"{explanation} Requested focus: {normalized_prompt}."

		return {
			"assistant_mode": "steward",
			"target_type": normalized_target_type,
			"target_id": normalized_target_id,
			"target_label": facts["target_label"],
			"metadata_summary": summary,
			"explanation": explanation,
			"suggested_fixes": suggested_fixes,
			"metadata_facts": facts,
		}

	if normalized_target_type == "glossary_term":
		definition = await registry_definition_resolver.resolve_definition(normalized_target_id)
		facts = {
			"target_type": normalized_target_type,
			"target_id": normalized_target_id,
			"target_label": _normalize_text(definition.get("definition_name") or definition.get("name") or normalized_target_id),
			"definition_type": _normalize_text(definition.get("definition_type")),
			"business_definition": _normalize_text(definition.get("business_definition")),
			"glossary_name": _normalize_text(definition.get("glossary_name")),
			"owner": _normalize_text(definition.get("owner")),
			"parent_definition_name": _normalize_text(definition.get("parent_definition_name")),
			"child_definition_count": int(definition.get("child_definition_count") or 0),
			"synonyms": ", ".join(str(item).strip() for item in definition.get("synonyms") or [] if str(item).strip()),
			"status": _normalize_text(definition.get("status")),
		}
		suggested_fixes = _build_fix_list(facts=facts)
		summary = f"Glossary term '{facts['target_label']}' is available in glossary '{facts['glossary_name'] or 'unknown'}'."
		explanation = (
			f"The steward reviewed glossary term '{facts['target_label']}' with definition type '{facts['definition_type'] or 'unknown'}'. "
			f"The current business definition is {facts['business_definition'] or 'missing'}."
		)
		if normalized_prompt:
			explanation = f"{explanation} Requested focus: {normalized_prompt}."

		return {
			"assistant_mode": "steward",
			"target_type": normalized_target_type,
			"target_id": normalized_target_id,
			"target_label": facts["target_label"],
			"metadata_summary": summary,
			"explanation": explanation,
			"suggested_fixes": suggested_fixes,
			"metadata_facts": facts,
		}

	raise MetadataStewardLookupError(
		f"Unsupported metadata steward target type '{normalized_target_type}'",
		status_code=400,
	)


def normalize_metadata_steward_error(exc: Exception) -> MetadataStewardLookupError:
	if isinstance(exc, MetadataStewardLookupError):
		return exc
	if isinstance(exc, RegistryDefinitionLookupError):
		return MetadataStewardLookupError(str(exc), status_code=getattr(exc, "status_code", 503))
	return MetadataStewardLookupError(str(exc), status_code=500)