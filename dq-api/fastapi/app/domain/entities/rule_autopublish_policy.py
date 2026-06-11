from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
import os
import re
from typing import Any

from fastapi import HTTPException
from pydantic import ValidationError

from app.core.telemetry import set_span_attributes, traced_span
from app.domain.entities import CompilerArtifactEntity
from app.domain.entities import build_gx_artifact_envelope_entity
from app.domain.entities import build_validation_artifact_envelope_from_gx_artifact
from app.domain.entities import RuleEntity
from app.domain.entities import RuleVersionEntity
from app.domain.entities.rule_dsl_ir import RuleDslIrDocument
from app.domain.entities.rule_dsl_ir import build_rule_dsl_v2_semantic_ir
from app.domain.entities.rule_dsl_v2 import RuleDslV2Document
from app.domain.entities import build_compiler_artifact_entity
from app.domain.entities import build_rule_version_list_entity
from app.application.services.rule_dsl_sodacl_lowerer import build_sodacl_artifact_envelope_from_rule_dsl_v2


GX_JOIN_PAIR_CHECK_TYPES = {
    "REFERENTIAL_INTEGRITY",
    "CORRECT",
    "RECONCILE",
    "TRANSFER_MATCH",
    "JOIN_CONSISTENCY",
}
GX_JOIN_PAIR_OUTPUT_FORMAT = "parquet"
GX_JOIN_PAIR_LANDING_ZONE_BUCKET_PREFIX = "dq-landing-zone-"


@dataclass(frozen=True, slots=True)
class CatalogSourceTarget:
    data_object_id: str
    data_object_version_id: str
    dataset_id: str | None
    workspace_id: str

    def as_execution_source(self) -> dict[str, str | None]:
        return {
            "dataObjectId": self.data_object_id,
            "dataObjectVersionId": self.data_object_version_id,
            "datasetId": self.dataset_id,
        }


@dataclass(frozen=True, slots=True)
class JoinKeyPair:
    left_attribute: str
    right_attribute: str

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "JoinKeyPair":
        return cls(
            left_attribute=str(payload.get("leftAttribute") or "").strip(),
            right_attribute=str(payload.get("rightAttribute") or "").strip(),
        )

    def as_payload(self) -> dict[str, str]:
        return {
            "leftAttribute": self.left_attribute,
            "rightAttribute": self.right_attribute,
        }


def _read_field(value: Any, field_name: str) -> Any:
    if isinstance(value, dict):
        return value.get(field_name)
    return getattr(value, field_name, None)


def resolve_rule_autopublish_target_engine(rule: RuleEntity | None) -> tuple[str, RuleDslIrDocument | None]:
    if rule is None:
        return "gx", None

    raw_dsl = _read_field(rule, "dsl")
    if not isinstance(raw_dsl, dict):
        return "gx", None

    schema_version = str(raw_dsl.get("schema_version") or raw_dsl.get("schemaVersion") or "").strip()
    if schema_version != "2.0.0":
        return "gx", None

    try:
        semantic_model = RuleDslV2Document.model_validate(raw_dsl)
    except ValidationError as exc:
        raise HTTPException(
            status_code=422,
            detail={
                "error": "rule_dsl_lowering_unsupported",
                "message": "DQ DSL 2.0.0 rule DSL is invalid and cannot be auto-published",
                "schema_version": "2.0.0",
                "rule_kind": None,
            },
        ) from exc

    semantic_ir = build_rule_dsl_v2_semantic_ir(semantic_model=semantic_model)
    preferred_engines = [
        str(value).strip().lower()
        for value in semantic_ir.rule.operations.preferred_engines
        if str(value).strip()
    ]
    if not preferred_engines:
        raise HTTPException(
            status_code=422,
            detail={
                "error": "rule_dsl_lowering_unsupported",
                "message": "DQ DSL 2.0.0 auto-publish requires at least one preferred engine",
                "schema_version": "2.0.0",
                "rule_kind": semantic_ir.rule.kind,
            },
        )

    target_engine = preferred_engines[0]
    if target_engine not in {"gx", "sodacl"}:
        raise HTTPException(
            status_code=422,
            detail={
                "error": "rule_dsl_lowering_unsupported",
                "message": (
                    "DQ DSL 2.0.0 auto-publish currently supports only target engines 'gx' and 'sodacl'"
                ),
                "schema_version": "2.0.0",
                "rule_kind": semantic_ir.rule.kind,
            },
        )

    return target_engine, semantic_ir


def _allocate_next_artifact_version(
    *,
    history_entries: list[Any],
    version_field_name: str,
    minimum_version: int,
) -> int:
    max_version = 0
    for entry in history_entries:
        try:
            candidate = int(_read_field(entry, version_field_name) or 0)
        except (TypeError, ValueError):
            continue
        max_version = max(max_version, candidate)

    if max_version <= 0:
        return max(1, int(minimum_version))
    return max_version + 1


def _build_gx_artifact_envelope_from_compiler(
    *,
    rule_id: str,
    rule_version_id: str,
    rule: RuleEntity | None,
    catalog_repository: Any | None,
    intermediate_model: dict,
    publish_request: Any,
    saved_by: str | None,
    suite_id: str,
    suite_version: int,
):
    from app.application.services import build_gx_expectations_for_rule
    from app.application.services import build_gx_expectations_from_intermediate_model
    from app.application.services import build_gx_row_condition_meta_from_intermediate_model

    now_iso = datetime.now(UTC).isoformat().replace("+00:00", "Z")
    execution_contract, resolved_data_object_version_ids = build_execution_contract_for_rule(
        rule=rule,
        catalog_repository=catalog_repository,
        rule_id=rule_id,
        rule_version_id=rule_version_id,
        suite_id=suite_id,
        suite_version=suite_version,
        intermediate_model=intermediate_model,
        publish_request=publish_request,
    )

    gx_suite_meta = {
        "ruleId": rule_id,
        "compilerVersion": intermediate_model.get("compilerVersion"),
        "artifactKey": intermediate_model.get("artifactKey"),
        "intermediateModel": intermediate_model,
        "gxRowCondition": build_gx_row_condition_meta_from_intermediate_model(intermediate_model),
    }

    if rule is None:
        expectations = build_gx_expectations_from_intermediate_model(
            intermediate_model,
            rule_id=rule_id,
            artifact_key=str(intermediate_model.get("artifactKey") or ""),
        )
    else:
        expectations = build_gx_expectations_for_rule(
            rule=rule,
            intermediate_model=intermediate_model,
            rule_id=rule_id,
            artifact_key=str(intermediate_model.get("artifactKey") or ""),
        )

    assignment_scope = {
        "dataObjectId": publish_request.dataObjectId,
        "datasetId": publish_request.datasetId,
        "dataProductId": publish_request.dataProductId,
    }
    if not any(str(value or "").strip() for value in assignment_scope.values()):
        raise ValueError("GX suite envelope is invalid")

    resolved_target_ids = [str(value).strip() for value in resolved_data_object_version_ids if str(value).strip()]
    if not resolved_target_ids:
        raise ValueError("GX suite envelope is invalid")

    return build_gx_artifact_envelope_entity(
        {
            "suiteId": suite_id,
            "suiteVersion": suite_version,
            "artifactVersion": "v1",
            "assignmentScope": assignment_scope,
            "resolvedExecutionScope": {
                "dataObjectVersionIds": resolved_target_ids,
            },
            "gxSuite": {
                "expectation_suite_name": f"dq_{rule_id}_v{suite_version}",
                "expectations": [dict(expectation) for expectation in expectations],
                "meta": dict(gx_suite_meta),
            },
            "compiledFrom": {
                "ruleIds": [rule_id],
                "compilerVersion": str(intermediate_model.get("compilerVersion") or "unknown"),
                "generatedAt": now_iso,
            },
            "executionHints": {
                "recommendedEngine": "pyspark",
                "primaryKeyFields": list(publish_request.primaryKeyFields),
                "businessKeyFields": list(publish_request.businessKeyFields),
            },
            "executionContract": execution_contract,
            "savedBy": saved_by,
            "sourcePipeline": "rule-compiler",
        }
    )


def _resolve_catalog_source_target_entity(
    *,
    catalog_repository: Any,
    version_id: str,
) -> CatalogSourceTarget:
    normalized_version_id = str(version_id or "").strip()
    if not normalized_version_id:
        raise HTTPException(status_code=400, detail="GX join-pair execution requires a data object version id")

    version = next(
        (
            item
            for item in catalog_repository.list_data_object_versions()
            if str(getattr(item, "id", "") or "") == normalized_version_id
        ),
        None,
    )
    if version is None:
        raise HTTPException(
            status_code=400,
            detail=f"GX join-pair execution could not resolve data object version '{normalized_version_id}'",
        )

    data_object_id = str(getattr(version, "data_object_id", "") or "").strip()
    if not data_object_id:
        raise HTTPException(
            status_code=400,
            detail=f"GX join-pair execution could not resolve data object for version '{normalized_version_id}'",
        )

    data_object = next(
        (
            item
            for item in catalog_repository.list_data_objects_catalog()
            if str(getattr(item, "id", "") or "") == data_object_id
        ),
        None,
    )
    dataset_id = str(getattr(data_object, "dataset_id", "") or "").strip() if data_object is not None else ""
    workspace_id = ""
    if dataset_id:
        dataset = next(
            (item for item in catalog_repository.list_data_sets() if str(getattr(item, "id", "") or "") == dataset_id),
            None,
        )
        workspace_id = str(getattr(dataset, "workspace_id", "") or "").strip() if dataset is not None else ""
    if not workspace_id:
        raise HTTPException(
            status_code=400,
            detail=f"GX join-pair execution could not resolve workspace for version '{normalized_version_id}'",
        )

    return CatalogSourceTarget(
        data_object_id=data_object_id,
        data_object_version_id=normalized_version_id,
        dataset_id=dataset_id or None,
        workspace_id=workspace_id,
    )


async def resolve_current_rule_version(repository: Any, rule_id: str) -> RuleVersionEntity | None:
    payload = build_rule_version_list_entity(
        await repository.list_rule_versions(rule_id, limit=1, offset=0)
    )
    if payload is None:
        return None

    versions = payload.versions
    if not versions:
        return None

    current = next((version for version in versions if bool(version.isCurrentVersion)), versions[0])
    if not str(current.id or "").strip():
        return None
    return current


async def persist_compiler_artifact(
    repository: Any,
    *,
    rule_id: str,
    filter_expression: str,
    intermediate_model: dict,
) -> CompilerArtifactEntity | None:
    with traced_span(
        "rules.compiler.persist_artifact",
        endpoint_group="rules",
        operation="persist_compiler_artifact",
        rule_id=rule_id,
    ) as span:
        version = await resolve_current_rule_version(repository, rule_id)
        if version is None:
            set_span_attributes(span, rule_version_found=False)
            return None

        rule_version_id = str(version.id or "").strip()
        if not rule_version_id:
            set_span_attributes(span, rule_version_found=False)
            return None

        normalized_expression = str(intermediate_model.get("filter", {}).get("normalized") or filter_expression or "").strip()
        diagnostics = intermediate_model.get("diagnostics") or []
        compile_status = "success" if bool(intermediate_model.get("compilable", True)) else "failed"
        set_span_attributes(
            span,
            rule_version_id=rule_version_id,
            compiler_diagnostics_count=len(diagnostics),
            compiler_compile_status=compile_status,
        )

        artifact = await repository.upsert_active_compiler_artifact(
            rule_version_id=rule_version_id,
            compiler_version=str(intermediate_model.get("compilerVersion") or "unknown"),
            artifact_key=str(intermediate_model.get("artifactKey") or ""),
            artifact_payload=intermediate_model,
            diagnostics_payload=diagnostics,
            compile_status=compile_status,
            source_fingerprint=sha256(normalized_expression.encode("utf-8")).hexdigest(),
        )
        return build_compiler_artifact_entity(artifact)


def normalize_resolved_data_object_version_ids(*version_ids: str) -> list[str]:
    resolved: list[str] = []
    for value in version_ids:
        normalized = str(value or "").strip()
        if normalized and normalized not in resolved:
            resolved.append(normalized)
    return resolved


def resolve_catalog_source_target(
    *,
    catalog_repository: Any,
    version_id: str,
) -> tuple[dict[str, str | None], str]:
    source = _resolve_catalog_source_target_entity(
        catalog_repository=catalog_repository,
        version_id=version_id,
    )
    return source.as_execution_source(), source.workspace_id


def resolve_join_pair_sources_for_rule(
    *,
    rule: RuleEntity,
    catalog_repository: Any,
    primary_version_id: str,
) -> tuple[dict[str, str | None], dict[str, str | None], str, str]:
    check_type = str(getattr(rule, "check_type", None) or getattr(rule, "checkType", None) or "").strip().upper()
    params = getattr(rule, "check_type_params", None)
    if params is None:
        params = getattr(rule, "checkTypeParams", None)
    raw_params = dict(params or {})

    if check_type == "REFERENTIAL_INTEGRITY":
        left_version_id = primary_version_id
        right_version_id = str(raw_params.get("refDataObjectVersionId") or "").strip()
        join_type = "left"
    elif check_type == "CORRECT":
        left_version_id = str(raw_params.get("sourceDataObjectVersionId") or "").strip()
        right_version_id = str(raw_params.get("referenceDataObjectVersionId") or "").strip()
        join_type = "inner"
    else:
        left_version_id = str(raw_params.get("leftDataObjectVersionId") or "").strip()
        right_version_id = str(raw_params.get("rightDataObjectVersionId") or "").strip()
        join_type = "inner"

    if not left_version_id or not right_version_id:
        raise HTTPException(
            status_code=400,
            detail=f"GX join-pair execution could not resolve source versions for check type '{check_type}'",
        )

    left_source, left_workspace_id = resolve_catalog_source_target(catalog_repository=catalog_repository, version_id=left_version_id)
    right_source, right_workspace_id = resolve_catalog_source_target(catalog_repository=catalog_repository, version_id=right_version_id)
    if left_workspace_id != right_workspace_id:
        raise HTTPException(
            status_code=400,
            detail={
                "error": "cross_workspace_join_pair_not_supported",
                "message": "GX join-pair publication requires both sources to belong to the same workspace",
                "left_workspace_id": left_workspace_id,
                "right_workspace_id": right_workspace_id,
                "check_type": check_type,
            },
        )
    return left_source, right_source, join_type, left_workspace_id


def normalize_bucket_segment(value: str) -> str:
    normalized = re.sub(r"[^a-z0-9-]", "-", str(value or "").strip().lower())
    normalized = re.sub(r"-+", "-", normalized).strip("-")
    if not normalized:
        raise HTTPException(status_code=400, detail="GX join-pair publication requires a non-empty workspace bucket suffix")
    return normalized


def resolve_join_pair_bucket_prefix() -> str:
    raw_prefix = str(os.environ.get("DQ_GX_JOIN_PAIR_LANDING_ZONE_BUCKET_PREFIX") or GX_JOIN_PAIR_LANDING_ZONE_BUCKET_PREFIX).strip().lower()
    normalized = re.sub(r"[^a-z0-9-]", "-", raw_prefix)
    normalized = re.sub(r"-+", "-", normalized).strip("-")
    if not normalized:
        raise HTTPException(status_code=503, detail="DQ_GX_JOIN_PAIR_LANDING_ZONE_BUCKET_PREFIX resolved to an invalid bucket prefix")
    return normalized


def build_join_pair_output_location(*, workspace_id: str, suite_id: str, suite_version: int) -> str:
    bucket_name = f"{resolve_join_pair_bucket_prefix()}-{normalize_bucket_segment(workspace_id)}"
    return (
        f"s3://{bucket_name}/gx/join-pairs/suite_id={suite_id}"
        f"/suite_version={int(suite_version)}"
        f"/format={GX_JOIN_PAIR_OUTPUT_FORMAT}"
    )


def build_execution_contract_for_rule(
    *,
    rule: RuleEntity | None,
    catalog_repository: Any | None,
    rule_id: str,
    rule_version_id: str,
    suite_id: str,
    suite_version: int,
    intermediate_model: dict,
    publish_request: Any,
) -> tuple[dict[str, object], list[str]]:
    primary_version_id = publish_request.dataObjectVersionIds[0] if publish_request.dataObjectVersionIds else None
    check_type = str(getattr(rule, "check_type", None) or getattr(rule, "checkType", None) or "").strip().upper()
    filter_payload = intermediate_model.get("filter") if isinstance(intermediate_model, dict) else None
    source_rule_expression = ""
    compiled_expression = ""
    if isinstance(filter_payload, dict):
        source_rule_expression = str(filter_payload.get("source") or "").strip()
        compiled_expression = str(filter_payload.get("normalized") or "").strip()
    if not source_rule_expression and rule is not None:
        source_rule_expression = str(getattr(rule, "expression", "") or "").strip()

    traceability = {
        "ruleId": rule_id,
        "ruleVersionId": rule_version_id,
        "gxSuiteId": suite_id,
        "gxSuiteVersion": suite_version,
        "dataObjectVersionId": primary_version_id if len(publish_request.dataObjectVersionIds) == 1 else None,
        "sourceRuleExpression": source_rule_expression or None,
        "compiledExpression": compiled_expression or None,
        "artifactKey": str(intermediate_model.get("artifactKey") or "").strip() or None,
    }
    execution_contract: dict[str, object] = {
        "engineType": "gx",
        "engineTarget": "pyspark",
        "executionShape": "single_object",
        "traceability": traceability,
    }
    resolved_ids = normalize_resolved_data_object_version_ids(*publish_request.dataObjectVersionIds)

    if rule is None or check_type not in GX_JOIN_PAIR_CHECK_TYPES:
        return execution_contract, resolved_ids

    if catalog_repository is None:
        raise HTTPException(
            status_code=503,
            detail={
                "error": "downstream_unavailable",
                "service": "data-catalog",
                "message": "data-catalog is unavailable for GX join-pair publication",
            },
        )
    if not primary_version_id:
        raise HTTPException(status_code=400, detail="GX join-pair publication requires a primary data_object_version_id")

    params = getattr(rule, "check_type_params", None)
    if params is None:
        params = getattr(rule, "checkTypeParams", None)
    raw_params = dict(params or {})
    join_key_pairs: list[JoinKeyPair] = []
    if check_type == "REFERENTIAL_INTEGRITY":
        join_key_pairs = [
            JoinKeyPair(
                left_attribute=str(raw_params.get("attribute") or "").strip(),
                right_attribute=str(raw_params.get("refAttribute") or "").strip(),
            )
        ]
    else:
        join_key_pairs = [
            JoinKeyPair.from_payload(item)
            for item in (raw_params.get("joinKeys") or [])
            if isinstance(item, dict)
        ]

    if not join_key_pairs or any(not item.left_attribute or not item.right_attribute for item in join_key_pairs):
        raise HTTPException(
            status_code=400,
            detail=f"GX join-pair publication requires non-empty join keys for check type '{check_type}'",
        )

    left_source, right_source, join_type, workspace_id = resolve_join_pair_sources_for_rule(
        rule=rule,
        catalog_repository=catalog_repository,
        primary_version_id=primary_version_id,
    )
    execution_contract["executionShape"] = "join_pair"
    execution_contract["sourceMaterialization"] = {
        "landingZoneArtifactId": f"lz_{suite_id}",
        "landingZoneVersionId": f"lzv_{suite_version}",
        "outputLocation": build_join_pair_output_location(workspace_id=workspace_id, suite_id=suite_id, suite_version=suite_version),
        "joinType": join_type,
        "joinKeys": [item.left_attribute for item in join_key_pairs],
        "joinKeyPairs": [item.as_payload() for item in join_key_pairs],
        "leftSource": left_source,
        "rightSource": right_source,
    }
    resolved_ids = normalize_resolved_data_object_version_ids(
        *publish_request.dataObjectVersionIds,
        str(left_source.get("dataObjectVersionId") or ""),
        str(right_source.get("dataObjectVersionId") or ""),
    )
    traceability["dataObjectVersionId"] = str(left_source.get("dataObjectVersionId") or "") or primary_version_id
    return execution_contract, resolved_ids


async def persist_gx_suite_from_compiler(
    gx_repository: Any,
    *,
    rule_id: str,
    rule_version_id: str,
    rule: RuleEntity | None = None,
    catalog_repository: Any | None = None,
    intermediate_model: dict,
    publish_request: Any,
    saved_by: str | None,
) -> None:
    with traced_span(
        "rules.gx.auto_publish",
        endpoint_group="rules",
        operation="gx_auto_publish",
        rule_id=rule_id,
        suite_version=publish_request.suiteVersion,
        publish_scope_count=len(publish_request.dataObjectVersionIds),
    ) as span:
        if not any((publish_request.dataObjectId, publish_request.datasetId, publish_request.dataProductId)):
            set_span_attributes(span, publish_skipped=True)
            return
        if not publish_request.dataObjectVersionIds:
            set_span_attributes(span, publish_skipped=True)
            return

        suite_id = f"gx_{rule_id}"
        history = await gx_repository.list_suite_status_history(suite_id=suite_id, suite_version=None)
        suite_version = _allocate_next_artifact_version(
            history_entries=history,
            version_field_name="suiteVersion",
            minimum_version=publish_request.suiteVersion,
        )
        set_span_attributes(span, allocated_suite_version=suite_version)
        set_span_attributes(span, suite_id=suite_id, publish_skipped=False)

        envelope = _build_gx_artifact_envelope_from_compiler(
            rule=rule,
            catalog_repository=catalog_repository,
            rule_id=rule_id,
            rule_version_id=rule_version_id,
            suite_id=suite_id,
            suite_version=suite_version,
            intermediate_model=intermediate_model,
            publish_request=publish_request,
            saved_by=saved_by,
        )

        await gx_repository.save_suite(
            envelope=envelope,
            status="active",
            saved_by=saved_by,
            source_pipeline="rule-compiler",
        )


async def persist_validation_artifact_from_compiler(
    validation_artifact_repository: Any,
    *,
    rule_id: str,
    rule_version_id: str,
    rule: RuleEntity | None = None,
    catalog_repository: Any | None = None,
    intermediate_model: dict,
    publish_request: Any,
    saved_by: str | None,
) -> None:
    with traced_span(
        "rules.gx.auto_publish",
        endpoint_group="rules",
        operation="gx_auto_publish",
        rule_id=rule_id,
        suite_version=publish_request.suiteVersion,
        publish_scope_count=len(publish_request.dataObjectVersionIds),
    ) as span:
        if not any((publish_request.dataObjectId, publish_request.datasetId, publish_request.dataProductId)):
            set_span_attributes(span, publish_skipped=True)
            return
        if not publish_request.dataObjectVersionIds:
            set_span_attributes(span, publish_skipped=True)
            return

        target_engine, semantic_ir = resolve_rule_autopublish_target_engine(rule)
        if target_engine == "sodacl":
            if semantic_ir is None:
                raise HTTPException(status_code=500, detail="DQ DSL 2.0.0 SodaCL auto-publish produced no semantic IR")

            artifact_id = f"sodacl_{rule_id}"
            history = await validation_artifact_repository.list_artifact_status_history(
                artifact_id=artifact_id,
                artifact_version=None,
            )
            artifact_version = _allocate_next_artifact_version(
                history_entries=history,
                version_field_name="validationArtifactVersion",
                minimum_version=publish_request.suiteVersion,
            )
            set_span_attributes(span, allocated_suite_version=artifact_version)
            set_span_attributes(span, suite_id=artifact_id, publish_skipped=False)

            artifact_envelope = build_sodacl_artifact_envelope_from_rule_dsl_v2(
                semantic_ir=semantic_ir,
                validation_artifact_id=artifact_id,
                validation_artifact_version=artifact_version,
                resolved_data_object_version_ids=list(publish_request.dataObjectVersionIds),
                rule_id=rule_id,
                artifact_key=rule_version_id,
                saved_by=saved_by,
                status="active",
                source_pipeline="rule-compiler",
            )

            await validation_artifact_repository.save_artifact(
                envelope=artifact_envelope,
                status="active",
                saved_by=saved_by,
                source_pipeline="rule-compiler",
            )
            return

        suite_id = f"gx_{rule_id}"
        history = await validation_artifact_repository.list_artifact_status_history(
            artifact_id=suite_id,
            artifact_version=None,
        )
        suite_version = _allocate_next_artifact_version(
            history_entries=history,
            version_field_name="validationArtifactVersion",
            minimum_version=publish_request.suiteVersion,
        )
        set_span_attributes(span, allocated_suite_version=suite_version)
        set_span_attributes(span, suite_id=suite_id, publish_skipped=False)

        gx_envelope = _build_gx_artifact_envelope_from_compiler(
            rule=rule,
            catalog_repository=catalog_repository,
            rule_id=rule_id,
            rule_version_id=rule_version_id,
            suite_id=suite_id,
            suite_version=suite_version,
            intermediate_model=intermediate_model,
            publish_request=publish_request,
            saved_by=saved_by,
        )
        artifact_envelope = build_validation_artifact_envelope_from_gx_artifact(gx_envelope)

        await validation_artifact_repository.save_artifact(
            envelope=artifact_envelope,
            status="active",
            saved_by=saved_by,
            source_pipeline="rule-compiler",
        )