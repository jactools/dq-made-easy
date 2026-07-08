from __future__ import annotations


import copy
import json
import os
from typing import Any

from app.application.services.business_term_guideline_validator import BusinessTermGuidelineViolation
from app.application.services.business_term_guideline_validator import validate_business_term_definition
from app.application.services.natural_language_rule_drafting import create_llm_service_client

import httpx

from app.domain.interfaces import DataCatalogRepository


ANALYSIS_TYPE_DEFINITION_TASK = "definition_task"
DEFAULT_DATA_DEFINITION_LLM_TIMEOUT_SECONDS = 300.0


class DataDefinitionTaskError(RuntimeError):
    def __init__(self, message: str, *, status_code: int = 400) -> None:
        super().__init__(message)
        self.status_code = status_code


def _clean(value: Any) -> str:
    return str(value or "").strip()


def _clean_list(values: Any) -> list[str]:
    if not isinstance(values, list):
        return []
    return [str(item).strip() for item in values if str(item).strip()]


def data_definition_llm_timeout_seconds() -> float:
    raw_value = os.getenv("DQ_DATA_DEFINITION_LLM_TIMEOUT_SECONDS", "").strip()
    if not raw_value:
        return DEFAULT_DATA_DEFINITION_LLM_TIMEOUT_SECONDS
    try:
        timeout_seconds = float(raw_value)
    except ValueError as exc:
        raise DataDefinitionTaskError(
            "DQ_DATA_DEFINITION_LLM_TIMEOUT_SECONDS must be a positive number",
            status_code=503,
        ) from exc
    if timeout_seconds <= 0:
        raise DataDefinitionTaskError(
            "DQ_DATA_DEFINITION_LLM_TIMEOUT_SECONDS must be a positive number",
            status_code=503,
        )
    return timeout_seconds


def _workspace_context(
    *,
    current_workspace_id: str,
    version_id: str,
    catalog_repository: DataCatalogRepository,
) -> tuple[Any, Any, Any, Any]:
    version = catalog_repository.get_data_object_version(version_id)
    if version is None:
        raise DataDefinitionTaskError(f"Data object version '{version_id}' was not found", status_code=404)

    data_objects = catalog_repository.list_data_objects_catalog()
    data_object = next((item for item in data_objects if _clean(getattr(item, "id", "")) == _clean(version.data_object_id)), None)
    if data_object is None:
        raise DataDefinitionTaskError(
            f"Data object '{version.data_object_id}' for version '{version_id}' was not found",
            status_code=404,
        )

    data_sets = catalog_repository.list_data_sets()
    data_set = next((item for item in data_sets if _clean(getattr(item, "id", "")) == _clean(data_object.dataset_id)), None)
    if data_set is None:
        raise DataDefinitionTaskError(
            f"Data set '{data_object.dataset_id}' for version '{version_id}' was not found",
            status_code=404,
        )

    data_products = catalog_repository.list_data_products(workspace=current_workspace_id)
    data_product = next((item for item in data_products if _clean(getattr(item, "id", "")) == _clean(data_set.product_id)), None)
    if data_product is None:
        raise DataDefinitionTaskError(
            f"Data product '{data_set.product_id}' for version '{version_id}' was not found in workspace '{current_workspace_id}'",
            status_code=404,
        )

    return version, data_object, data_set, data_product


def build_data_definition_generation_request(
    *,
    task_payload: dict[str, Any],
    catalog_repository: DataCatalogRepository,
) -> dict[str, Any]:
    current_workspace_id = _clean(task_payload.get("current_workspace_id"))
    version_id = _clean(task_payload.get("version_id"))
    selected_attribute_ids = _clean_list(task_payload.get("selected_attribute_ids"))
    if not current_workspace_id:
        raise DataDefinitionTaskError("Data-definition tasks require 'current_workspace_id'", status_code=422)
    if not version_id:
        raise DataDefinitionTaskError("Data-definition tasks require 'version_id'", status_code=422)
    if not selected_attribute_ids:
        raise DataDefinitionTaskError("Select at least one attribute for the data-definition task", status_code=422)

    version, data_object, data_set, data_product = _workspace_context(
        current_workspace_id=current_workspace_id,
        version_id=version_id,
        catalog_repository=catalog_repository,
    )
    attributes = catalog_repository.list_attributes_catalog(version_id=version_id)
    attributes_by_id = {_clean(getattr(attribute, "id", "")): attribute for attribute in attributes}
    missing_attribute_ids = [attribute_id for attribute_id in selected_attribute_ids if attribute_id not in attributes_by_id]
    if missing_attribute_ids:
        raise DataDefinitionTaskError(
            f"Selected attributes were not found for version '{version_id}': {', '.join(sorted(missing_attribute_ids))}",
            status_code=404,
        )

    targets: list[dict[str, Any]] = []
    for attribute_id in selected_attribute_ids:
        attribute = attributes_by_id[attribute_id]
        metadata = {
            "workspace_id": current_workspace_id,
            "version_id": version_id,
            "definition_id": _clean(getattr(attribute, "definition_id", "")),
            "definition_mapping_status": _clean(getattr(attribute, "definition_mapping_status", "")),
            "is_cde": bool(getattr(attribute, "is_cde", False)),
            "is_primary_key": bool(getattr(attribute, "is_primary_key", False)),
            "is_business_key": bool(getattr(attribute, "is_business_key", False)),
            "storage_uri": _clean(getattr(version, "storage_uri", "")),
            "storage_format": _clean(getattr(version, "storage_format", "")),
            "masking_method": _clean(getattr(attribute, "masking_method", "none")),
            "encryption_required": bool(getattr(attribute, "encryption_required", False)),
            "regulatory_tags": ["critical_data_element"] if bool(getattr(attribute, "is_cde", False)) else [],
            "retention_class": "encrypted" if bool(getattr(attribute, "encryption_required", False)) else "standard",
            "sensitivity": _clean(getattr(attribute, "masking_method", "none")),
        }
        targets.append(
            {
                "target_id": attribute_id,
                "data_set_name": _clean(getattr(data_set, "name", "")) or version_id,
                "data_object_name": _clean(getattr(data_object, "name", "")) or version_id,
                "attribute_name": _clean(getattr(attribute, "name", "")) or attribute_id,
                "display_name": _clean(getattr(attribute, "name", "")) or attribute_id,
                "data_type": _clean(getattr(attribute, "type", "")),
                "nullable": bool(getattr(attribute, "nullable", True)),
                "description": _clean(getattr(attribute, "source_name", "")),
                "logical_path": "/".join(
                    [
                        _clean(getattr(data_product, "name", "")) or current_workspace_id,
                        _clean(getattr(data_set, "name", "")) or data_set.id,
                        _clean(getattr(data_object, "name", "")) or data_object.id,
                        f"v{int(getattr(version, 'version', 0) or 0)}",
                        _clean(getattr(attribute, "name", "")) or attribute_id,
                    ]
                ),
                "source_system": _clean(task_payload.get("source_system")) or _clean(getattr(data_product, "name", "")),
                "steward_notes": _clean(task_payload.get("user_input")),
                "sample_values": [],
                "metadata": metadata,
            }
        )

    normalized_feedback_items: list[dict[str, Any]] = []
    for item in list(task_payload.get("feedback_items") or []):
        if not isinstance(item, dict):
            continue
        normalized_feedback_items.append(
            {
                "feedback_id": _clean(item.get("feedback_id")) or None,
                "source_role": _clean(item.get("source_role")),
                "comment": _clean(item.get("comment")),
                "author_name": _clean(item.get("author_name")) or None,
                "disposition": _clean(item.get("disposition")) or None,
                "target_ids": _clean_list(item.get("target_ids")) or list(selected_attribute_ids),
            }
        )

    board_approval = task_payload.get("board_approval") if isinstance(task_payload.get("board_approval"), dict) else None
    if board_approval is not None:
        board_approval = {
            "board_name": _clean(board_approval.get("board_name")) or None,
            "status": _clean(board_approval.get("status")) or "pending",
            "approver_name": _clean(board_approval.get("approver_name")) or None,
            "approval_notes": _clean(board_approval.get("approval_notes")) or None,
            "approved_at": _clean(board_approval.get("approved_at")) or None,
        }

    return {
        "task_id": _clean(task_payload.get("task_id")) or _clean(task_payload.get("request_id")) or version_id,
        "steward_name": _clean(task_payload.get("steward_name")) or None,
        "board_name": _clean(task_payload.get("board_name")) or "Data Definition Board",
        "glossary_name": _clean(task_payload.get("glossary_name")) or None,
        "glossary_display_name": _clean(task_payload.get("glossary_display_name")) or None,
        "domain_name": _clean(task_payload.get("domain_name")) or _clean(getattr(data_product, "name", "")) or None,
        "source_system": _clean(task_payload.get("source_system")) or _clean(getattr(data_product, "name", "")) or None,
        "user_input": _clean(task_payload.get("user_input")) or None,
        "policies": _clean_list(task_payload.get("policies")),
        "targets": targets,
        "context_documents": [item for item in list(task_payload.get("context_documents") or []) if isinstance(item, dict)],
        "feedback_items": [item for item in normalized_feedback_items if item["source_role"] and item["comment"]],
        "board_approval": board_approval,
    }


async def fetch_data_definition_bundle(*, request_payload: dict[str, Any], llm_service_url: str) -> dict[str, Any]:
    normalized_service_url = _clean(llm_service_url).rstrip("/")
    if not normalized_service_url:
        raise DataDefinitionTaskError("LLM service URL is not configured", status_code=503)

    try:
        async with create_llm_service_client(
            base_url=normalized_service_url,
            timeout_seconds=data_definition_llm_timeout_seconds(),
        ) as client:
            response = await client.post(f"{normalized_service_url}/generate_data_definitions", json=request_payload)
    except httpx.TimeoutException as exc:
        raise DataDefinitionTaskError("The data-definition generation service timed out", status_code=503) from exc
    except httpx.RequestError as exc:
        raise DataDefinitionTaskError("The data-definition generation service is unavailable", status_code=503) from exc

    if response.status_code >= 400:
        detail = None
        try:
            payload = response.json()
        except ValueError:
            payload = None
        if isinstance(payload, dict):
            detail = _clean(payload.get("detail") or payload.get("message"))
        raise DataDefinitionTaskError(
            detail or f"Data-definition generation returned HTTP {response.status_code}",
            status_code=502 if response.status_code >= 500 else response.status_code,
        )

    try:
        payload = response.json()
    except ValueError as exc:
        raise DataDefinitionTaskError("The data-definition generation service returned a non-JSON response", status_code=502) from exc

    if not isinstance(payload, dict):
        raise DataDefinitionTaskError("The data-definition generation service returned an invalid payload", status_code=502)
    validate_data_definition_task_result(result=payload)
    return payload


def _definition_term_name(definition: dict[str, Any]) -> str:
    for field_name in ("definition_name", "display_name", "displayName", "name", "term", "definition_id"):
        value = _clean(definition.get(field_name))
        if value:
            return value
    return ""


def _definition_text(definition: dict[str, Any]) -> str:
    for field_name in ("business_definition", "definition", "description"):
        value = _clean(definition.get(field_name))
        if value:
            return value
    return ""


def _definition_identifier(definition: dict[str, Any]) -> str:
    for field_name in ("definition_id", "concept_key"):
        value = _clean(definition.get(field_name))
        if value:
            return value
    extension = definition.get("extension") if isinstance(definition.get("extension"), dict) else {}
    for field_name in ("definition_id", "concept_key"):
        value = _clean(extension.get(field_name))
        if value:
            return value
    for field_name in ("name", "term"):
        value = _clean(definition.get(field_name))
        if value:
            return value
    return ""


def _json_object(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)
    if isinstance(value, str) and value.strip():
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return {}
        return dict(parsed) if isinstance(parsed, dict) else {}
    return {}


def _json_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return [item for item in value if item]
    if isinstance(value, str) and value.strip():
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return [value.strip()]
        if isinstance(parsed, list):
            return [item for item in parsed if item]
        if parsed:
            return [parsed]
    return []


def _definition_extension(definition: dict[str, Any]) -> dict[str, Any]:
    return definition.get("extension") if isinstance(definition.get("extension"), dict) else {}


def _definition_provenance(definition: dict[str, Any]) -> dict[str, Any]:
    provenance = _json_object(definition.get("provenance"))
    if provenance:
        return provenance
    return _json_object(_definition_extension(definition).get("provenance"))


def _governance_value(definition: dict[str, Any], field_name: str) -> str:
    value = _clean(definition.get(field_name))
    if value:
        return value
    extension = _definition_extension(definition)
    value = _clean(extension.get(field_name))
    if value:
        return value
    return _clean(_definition_provenance(definition).get(field_name))


def _governance_list(definition: dict[str, Any], field_name: str) -> list[Any]:
    values = _json_list(definition.get(field_name))
    if values:
        return values
    extension_values = _json_list(_definition_extension(definition).get(field_name))
    if extension_values:
        return extension_values
    return _json_list(_definition_provenance(definition).get(field_name))


def _governance_object(definition: dict[str, Any], field_name: str) -> dict[str, Any]:
    value = _json_object(definition.get(field_name))
    if value:
        return value
    extension_value = _json_object(_definition_extension(definition).get(field_name))
    if extension_value:
        return extension_value
    return _json_object(_definition_provenance(definition).get(field_name))


def _dict_items(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _validate_governance_payload(*, definition: dict[str, Any], label: str, term_name: str) -> None:
    violations: list[str] = []

    if not _definition_identifier(definition):
        violations.append("concept_key or definition_id is required for one-entry-per-concept governance")
    if not _governance_value(definition, "primary_domain"):
        violations.append("primary_domain is required")
    if not _governance_value(definition, "definition_owner"):
        violations.append("definition_owner is required")
    if not _governance_list(definition, "source_references"):
        violations.append("source_references must include at least one source reference")
    if not _governance_list(definition, "policy_documents"):
        violations.append("policy_documents must include at least one governing policy document")

    homonym_context = _governance_object(definition, "homonym_context")
    if not homonym_context:
        violations.append("homonym_context is required for clear homonym disambiguation")
    else:
        missing_homonym_fields = [
            field_name
            for field_name in ("primary_domain", "object_class", "property")
            if not _clean(homonym_context.get(field_name))
        ]
        if missing_homonym_fields:
            violations.append(f"homonym_context is missing {', '.join(missing_homonym_fields)}")

    if violations:
        raise DataDefinitionTaskError(
            f"{label} for term '{term_name}' violates business term governance requirements: {'; '.join(violations)}",
            status_code=422,
        )


def _validate_definition_payload(*, definition: dict[str, Any], label: str) -> None:
    term_name = _definition_term_name(definition)
    definition_text = _definition_text(definition)
    synonyms = _clean_list(definition.get("synonyms"))
    if not term_name:
        raise DataDefinitionTaskError(f"{label} is missing a business term name", status_code=422)
    if not definition_text:
        raise DataDefinitionTaskError(f"{label} for term '{term_name}' is missing a business definition", status_code=422)
    try:
        validate_business_term_definition(term_name, definition_text, synonyms)
    except BusinessTermGuidelineViolation as exc:
        raise DataDefinitionTaskError(
            f"{label} for term '{term_name}' violates business term guidelines: {exc}",
            status_code=422,
        ) from exc
    _validate_governance_payload(definition=definition, label=label, term_name=term_name)


def _validate_unique_concepts(*, label: str, definitions: list[dict[str, Any]]) -> None:
    seen_identifiers: set[str] = set()
    seen_target_ids: set[str] = set()
    for definition in definitions:
        identifier = _definition_identifier(definition)
        if identifier:
            if identifier in seen_identifiers:
                raise DataDefinitionTaskError(f"{label} contains duplicate concept '{identifier}'", status_code=422)
            seen_identifiers.add(identifier)
        target_id = _clean(definition.get("target_id")) or _clean(_definition_extension(definition).get("target_id"))
        if target_id:
            if target_id in seen_target_ids:
                raise DataDefinitionTaskError(f"{label} contains duplicate target_id '{target_id}'", status_code=422)
            seen_target_ids.add(target_id)


def _iter_result_definitions(result: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
    definitions: list[tuple[str, dict[str, Any]]] = []

    registry_contract = result.get("registry_contract")
    if isinstance(registry_contract, dict):
        for definition in _dict_items(registry_contract.get("definitions")):
            definitions.append(("Registry definition", definition))

    import_contract = result.get("openmetadata_import_contract")
    if isinstance(import_contract, dict):
        manifest = import_contract.get("definitions_manifest") if isinstance(import_contract.get("definitions_manifest"), dict) else None
        if manifest is not None:
            for definition in _dict_items(manifest.get("definitions")):
                definitions.append(("OpenMetadata manifest definition", definition))
        for glossary_term in _dict_items(import_contract.get("glossary_terms")):
            definitions.append(("OpenMetadata glossary term", glossary_term))

    return definitions


def validate_data_definition_task_result(*, result: dict[str, Any]) -> None:
    if not isinstance(result, dict):
        raise DataDefinitionTaskError("Data-definition task result must be a JSON object", status_code=502)
    registry_contract = result.get("registry_contract") if isinstance(result.get("registry_contract"), dict) else None
    if registry_contract is not None:
        registry_definitions = _dict_items(registry_contract.get("definitions"))
        _validate_unique_concepts(label="Registry definitions", definitions=registry_definitions)

    import_contract = result.get("openmetadata_import_contract") if isinstance(result.get("openmetadata_import_contract"), dict) else None
    if import_contract is not None:
        manifest = import_contract.get("definitions_manifest") if isinstance(import_contract.get("definitions_manifest"), dict) else None
        if manifest is not None:
            manifest_definitions = _dict_items(manifest.get("definitions"))
            _validate_unique_concepts(label="OpenMetadata manifest definitions", definitions=manifest_definitions)

        glossary_terms = _dict_items(import_contract.get("glossary_terms"))
        _validate_unique_concepts(label="OpenMetadata glossary terms", definitions=glossary_terms)

    definitions = _iter_result_definitions(result)
    if not definitions:
        raise DataDefinitionTaskError("Data-definition task result does not include generated definitions", status_code=502)
    for label, definition in definitions:
        _validate_definition_payload(definition=definition, label=label)


def require_approved_openmetadata_import_contract(*, result: dict[str, Any]) -> dict[str, Any]:
    if str(result.get("review_status") or "").strip().lower() != "approved":
        raise DataDefinitionTaskError("Only approved tasks can be imported to OpenMetadata", status_code=422)

    import_contract = result.get("openmetadata_import_contract")
    if not isinstance(import_contract, dict):
        raise DataDefinitionTaskError("Task result does not include an OpenMetadata import contract", status_code=502)

    validate_data_definition_task_result(result=result)
    return import_contract


def apply_board_approval_to_result(*, result: dict[str, Any], approval_payload: dict[str, Any]) -> dict[str, Any]:
    updated = copy.deepcopy(result)
    normalized_status = _clean(approval_payload.get("status")).lower() or "pending"

    if normalized_status == "approved":
        validate_data_definition_task_result(result=updated)

    board_review_packet = updated.get("board_review_packet")
    if not isinstance(board_review_packet, dict):
        board_review_packet = {}
        updated["board_review_packet"] = board_review_packet
    board_review_packet["approval"] = dict(approval_payload)
    board_review_packet["review_status"] = normalized_status
    board_review_packet["decision_required"] = normalized_status != "approved"

    if normalized_status in {"approved", "rejected"}:
        updated["review_status"] = normalized_status

    for contract_key in ("registry_contract",):
        contract = updated.get(contract_key)
        if not isinstance(contract, dict):
            continue
        definitions = contract.get("definitions")
        if not isinstance(definitions, list):
            continue
        for definition in definitions:
            if not isinstance(definition, dict):
                continue
            provenance = definition.get("provenance") if isinstance(definition.get("provenance"), dict) else {}
            provenance["approval_status"] = normalized_status
            provenance["approver_name"] = _clean(approval_payload.get("approver_name"))
            provenance["approval_notes"] = _clean(approval_payload.get("approval_notes"))
            definition["provenance"] = provenance
            definition["board_review_status"] = normalized_status
            if normalized_status == "approved":
                definition["status"] = "approved"

    import_contract = updated.get("openmetadata_import_contract")
    if isinstance(import_contract, dict):
        manifest = import_contract.get("definitions_manifest") if isinstance(import_contract.get("definitions_manifest"), dict) else None
        if manifest is not None:
            definitions = manifest.get("definitions") if isinstance(manifest.get("definitions"), list) else []
            for definition in definitions:
                if not isinstance(definition, dict):
                    continue
                provenance = definition.get("provenance") if isinstance(definition.get("provenance"), dict) else {}
                provenance["approval_status"] = normalized_status
                provenance["approver_name"] = _clean(approval_payload.get("approver_name"))
                provenance["approval_notes"] = _clean(approval_payload.get("approval_notes"))
                definition["provenance"] = provenance
                definition["board_review_status"] = normalized_status
                if normalized_status == "approved":
                    definition["status"] = "approved"

        glossary_terms = import_contract.get("glossary_terms") if isinstance(import_contract.get("glossary_terms"), list) else []
        for term in glossary_terms:
            if not isinstance(term, dict):
                continue
            extension = term.get("extension") if isinstance(term.get("extension"), dict) else {}
            extension["board_review_status"] = normalized_status
            if normalized_status == "approved":
                extension["status"] = "approved"
            raw_provenance = extension.get("provenance")
            if isinstance(raw_provenance, str) and raw_provenance.strip():
                try:
                    parsed_provenance = json.loads(raw_provenance)
                except json.JSONDecodeError:
                    parsed_provenance = {}
            else:
                parsed_provenance = {}
            if isinstance(parsed_provenance, dict):
                parsed_provenance["approval_status"] = normalized_status
                parsed_provenance["approver_name"] = _clean(approval_payload.get("approver_name"))
                parsed_provenance["approval_notes"] = _clean(approval_payload.get("approval_notes"))
                extension["provenance"] = json.dumps(parsed_provenance, separators=(",", ":"), sort_keys=True)
            term["extension"] = extension

    return updated


def merge_import_result(*, result: dict[str, Any], import_report: dict[str, Any]) -> dict[str, Any]:
    updated = copy.deepcopy(result)
    updated["openmetadata_import_result"] = import_report
    orchestration_trace = updated.get("orchestration_trace")
    if not isinstance(orchestration_trace, list):
        orchestration_trace = []
        updated["orchestration_trace"] = orchestration_trace
    orchestration_trace.append(
        {
            "step_id": "DD-STEP-005",
            "name": "import_openmetadata_contract",
            "status": "completed",
            "detail": f"Imported {int(import_report.get('definition_count') or 0)} definitions into OpenMetadata.",
        }
    )
    return updated