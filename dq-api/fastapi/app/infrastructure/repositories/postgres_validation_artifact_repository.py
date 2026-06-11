from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from uuid import uuid4

from sqlalchemy import select

from app.domain.entities import build_validation_artifact_envelope_from_gx_artifact
from app.domain.entities import build_validation_artifact_status_history_entities
from app.domain.entities import build_validation_artifact_envelope_entity
from app.domain.entities import ValidationArtifactEnvelopeEntity
from app.domain.entities import ValidationArtifactStatusHistoryEntity
from app.domain.interfaces.v1.validation_artifact_repository import ValidationArtifactRepository
from app.infrastructure.orm.models import ValidationArtifactRegistryRow
from app.infrastructure.orm.models import ValidationArtifactStatusHistoryRow
from app.infrastructure.orm.session import session_scope


class PostgresValidationArtifactRepository(ValidationArtifactRepository):
    def __init__(self, database_url: str) -> None:
        self.database_url = database_url

    async def save_artifact(
        self,
        *,
        envelope: ValidationArtifactEnvelopeEntity,
        status: str = "active",
        expected_existing_hash: str | None = None,
        saved_by: str | None = None,
        source_pipeline: str | None = None,
    ) -> ValidationArtifactEnvelopeEntity:
        normalized = build_validation_artifact_envelope_entity(envelope).model_dump(
            mode="python",
            by_alias=False,
            exclude_none=True,
        )
        normalized["status"] = status
        normalized["savedBy"] = saved_by
        normalized["sourcePipeline"] = source_pipeline

        artifact_id = str(normalized.get("validationArtifactId") or "").strip()
        artifact_version = int(normalized.get("validationArtifactVersion") or 0)
        assignment_scope = self._coerce_mapping(normalized.get("assignmentScope"))
        compiled_from = self._coerce_mapping(normalized.get("compiledFrom"))
        resolved_scope = self._coerce_mapping(normalized.get("resolvedExecutionScope"))
        generated_at = self._parse_generated_at(compiled_from.get("generatedAt"))
        target_ids = self._coerce_string_list(resolved_scope.get("dataObjectVersionIds"))
        rule_ids = self._coerce_string_list(compiled_from.get("ruleIds"))

        with session_scope(self.database_url) as session:
            row = session.execute(
                select(ValidationArtifactRegistryRow)
                .where(ValidationArtifactRegistryRow.validation_artifact_id == artifact_id)
                .where(ValidationArtifactRegistryRow.validation_artifact_version == artifact_version)
                .limit(1)
            ).scalar_one_or_none()

            if row is None:
                row = ValidationArtifactRegistryRow(
                    id=f"val-art-{uuid4().hex}",
                    validation_artifact_id=artifact_id,
                    validation_artifact_version=artifact_version,
                    artifact_contract_version=str(normalized.get("artifactContractVersion") or "v1"),
                    engine_type=str(normalized.get("engineType") or ""),
                    status=status,
                    data_object_id=assignment_scope.get("dataObjectId"),
                    dataset_id=assignment_scope.get("datasetId"),
                    data_product_id=assignment_scope.get("dataProductId"),
                    resolved_data_object_version_ids=target_ids,
                    compiled_rule_ids=rule_ids,
                    compiler_version=str(compiled_from.get("compilerVersion") or "unknown"),
                    generated_at=generated_at,
                    envelope_json=normalized,
                    saved_by=saved_by,
                    source_pipeline=source_pipeline,
                )
                session.add(row)
                session.flush()
                session.add(
                    ValidationArtifactStatusHistoryRow(
                        id=f"val-art-hist-{uuid4().hex}",
                        validation_artifact_id=artifact_id,
                        validation_artifact_version=artifact_version,
                        from_status=None,
                        to_status=status,
                        changed_by=saved_by,
                        reason=None,
                    )
                )
            else:
                existing_hash = self._hash_payload(self._build_envelope(row))
                incoming_hash = self._hash_payload(normalized)
                if existing_hash != incoming_hash and expected_existing_hash != existing_hash:
                    raise ValueError(
                        "Validation artifact overwrite conflict: expected hash does not match current artifact"
                    )

                old_status = str(row.status or "")
                row.artifact_contract_version = str(normalized.get("artifactContractVersion") or row.artifact_contract_version or "v1")
                row.engine_type = str(normalized.get("engineType") or row.engine_type or "")
                row.status = status
                row.data_object_id = assignment_scope.get("dataObjectId")
                row.dataset_id = assignment_scope.get("datasetId")
                row.data_product_id = assignment_scope.get("dataProductId")
                row.resolved_data_object_version_ids = target_ids
                row.compiled_rule_ids = rule_ids
                row.compiler_version = str(compiled_from.get("compilerVersion") or row.compiler_version or "unknown")
                row.generated_at = generated_at
                row.envelope_json = normalized
                row.saved_by = saved_by
                row.source_pipeline = source_pipeline
                if old_status != status:
                    session.add(
                        ValidationArtifactStatusHistoryRow(
                            id=f"val-art-hist-{uuid4().hex}",
                            validation_artifact_id=artifact_id,
                            validation_artifact_version=artifact_version,
                            from_status=old_status or None,
                            to_status=status,
                            changed_by=saved_by,
                            reason=None,
                        )
                    )

            session.commit()

        result = self._build_envelope(row)
        result["artifactHash"] = self._hash_payload(result)
        return build_validation_artifact_envelope_entity(result)

    async def list_artifacts(
        self,
        *,
        data_object_id: str | None = None,
        data_object_version_id: str | None = None,
        dataset_id: str | None = None,
        data_product_id: str | None = None,
        status: str = "active",
        latest_only: bool = True,
    ) -> list[ValidationArtifactEnvelopeEntity]:
        with session_scope(self.database_url) as session:
            stmt = select(ValidationArtifactRegistryRow).where(ValidationArtifactRegistryRow.status == status)

            if data_object_id:
                stmt = stmt.where(ValidationArtifactRegistryRow.data_object_id == data_object_id)
            if dataset_id:
                stmt = stmt.where(ValidationArtifactRegistryRow.dataset_id == dataset_id)
            if data_product_id:
                stmt = stmt.where(ValidationArtifactRegistryRow.data_product_id == data_product_id)
            if data_object_version_id:
                stmt = stmt.where(
                    ValidationArtifactRegistryRow.resolved_data_object_version_ids.contains([str(data_object_version_id)])
                )

            rows = session.execute(
                stmt.order_by(
                    ValidationArtifactRegistryRow.validation_artifact_id.asc(),
                    ValidationArtifactRegistryRow.validation_artifact_version.desc(),
                )
            ).scalars().all()

        selected_rows = rows
        if latest_only:
            latest_by_artifact: dict[str, ValidationArtifactRegistryRow] = {}
            for row in rows:
                if row.validation_artifact_id not in latest_by_artifact:
                    latest_by_artifact[row.validation_artifact_id] = row
            selected_rows = list(latest_by_artifact.values())

        return [build_validation_artifact_envelope_entity(self._build_envelope(row)) for row in selected_rows]

    async def list_artifacts_for_rule(
        self,
        *,
        rule_id: str,
        status: str = "active",
        latest_only: bool = True,
    ) -> list[ValidationArtifactEnvelopeEntity]:
        normalized_rule_id = str(rule_id or "").strip()
        if not normalized_rule_id:
            return []

        with session_scope(self.database_url) as session:
            rows = session.execute(
                select(ValidationArtifactRegistryRow)
                .where(ValidationArtifactRegistryRow.status == status)
                .where(ValidationArtifactRegistryRow.compiled_rule_ids.contains([normalized_rule_id]))
                .order_by(
                    ValidationArtifactRegistryRow.validation_artifact_id.asc(),
                    ValidationArtifactRegistryRow.validation_artifact_version.desc(),
                )
            ).scalars().all()

        selected_rows = rows
        if latest_only:
            latest_by_artifact: dict[str, ValidationArtifactRegistryRow] = {}
            for row in rows:
                if row.validation_artifact_id not in latest_by_artifact:
                    latest_by_artifact[row.validation_artifact_id] = row
            selected_rows = list(latest_by_artifact.values())

        return [build_validation_artifact_envelope_entity(self._build_envelope(row)) for row in selected_rows]

    async def get_artifact_by_id(
        self,
        *,
        artifact_id: str,
        artifact_version: int | None = None,
        status: str = "active",
    ) -> ValidationArtifactEnvelopeEntity | None:
        with session_scope(self.database_url) as session:
            stmt = select(ValidationArtifactRegistryRow).where(
                ValidationArtifactRegistryRow.validation_artifact_id == artifact_id,
                ValidationArtifactRegistryRow.status == status,
            )

            if artifact_version is not None:
                stmt = stmt.where(ValidationArtifactRegistryRow.validation_artifact_version == artifact_version)
            else:
                stmt = stmt.order_by(ValidationArtifactRegistryRow.validation_artifact_version.desc())

            row = session.execute(stmt.limit(1)).scalar_one_or_none()

        if row is None:
            return None
        return build_validation_artifact_envelope_entity(self._build_envelope(row))

    async def patch_artifact_status(
        self,
        *,
        artifact_id: str,
        new_status: str,
        artifact_version: int | None = None,
        changed_by: str | None = None,
        reason: str | None = None,
    ) -> ValidationArtifactEnvelopeEntity | None:
        with session_scope(self.database_url) as session:
            stmt = select(ValidationArtifactRegistryRow).where(
                ValidationArtifactRegistryRow.validation_artifact_id == artifact_id
            )

            if artifact_version is not None:
                stmt = stmt.where(ValidationArtifactRegistryRow.validation_artifact_version == artifact_version)
            else:
                stmt = stmt.order_by(ValidationArtifactRegistryRow.validation_artifact_version.desc())

            row = session.execute(stmt.limit(1)).scalar_one_or_none()
            if row is None:
                return None

            old_status = str(row.status or "")
            row.status = new_status
            envelope_json = row.envelope_json if isinstance(row.envelope_json, dict) else {}
            row.envelope_json = {
                **envelope_json,
                "status": new_status,
            }
            session.add(
                ValidationArtifactStatusHistoryRow(
                    id=f"val-art-hist-{uuid4().hex}",
                    validation_artifact_id=row.validation_artifact_id,
                    validation_artifact_version=int(row.validation_artifact_version),
                    from_status=old_status or None,
                    to_status=new_status,
                    changed_by=changed_by,
                    reason=reason,
                )
            )
            session.commit()

        if row is None:
            return None
        return build_validation_artifact_envelope_entity(self._build_envelope(row))

    async def list_artifact_status_history(
        self,
        *,
        artifact_id: str,
        artifact_version: int | None = None,
    ) -> list[ValidationArtifactStatusHistoryEntity]:
        with session_scope(self.database_url) as session:
            stmt = select(ValidationArtifactStatusHistoryRow).where(
                ValidationArtifactStatusHistoryRow.validation_artifact_id == artifact_id
            )
            if artifact_version is not None:
                stmt = stmt.where(
                    ValidationArtifactStatusHistoryRow.validation_artifact_version == artifact_version
                )
            stmt = stmt.order_by(ValidationArtifactStatusHistoryRow.changed_at.asc())
            rows = session.execute(stmt).scalars().all()

        return build_validation_artifact_status_history_entities(
            [
                {
                    "validationArtifactId": row.validation_artifact_id,
                    "validationArtifactVersion": int(row.validation_artifact_version),
                    "fromStatus": row.from_status,
                    "toStatus": row.to_status,
                    "changedBy": row.changed_by,
                    "changedAt": self._format_datetime(row.changed_at),
                    "reason": row.reason,
                }
                for row in rows
            ]
        )

    @staticmethod
    def _coerce_mapping(value: object) -> dict:
        return value if isinstance(value, dict) else {}

    @staticmethod
    def _coerce_string_list(value: object) -> list[str]:
        if not isinstance(value, list):
            return []
        return [str(item).strip() for item in value if str(item).strip()]

    @staticmethod
    def _parse_generated_at(value: object) -> datetime:
        raw_value = str(value or "").strip()
        try:
            return datetime.fromisoformat(raw_value.replace("Z", "+00:00"))
        except ValueError:
            return datetime.now(timezone.utc)

    @staticmethod
    def _format_datetime(value: object) -> str:
        if isinstance(value, datetime):
            return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
        return str(value or "")

    @classmethod
    def _build_envelope(cls, row: ValidationArtifactRegistryRow) -> dict:
        payload = row.envelope_json if isinstance(row.envelope_json, dict) else {}

        if "engineArtifact" not in payload and str(row.engine_type or "").strip().lower() == "gx":
            gx_assignment_scope = cls._coerce_mapping(payload.get("assignmentScope"))
            gx_resolved_scope = cls._coerce_mapping(payload.get("resolvedExecutionScope"))
            gx_compiled_from = cls._coerce_mapping(payload.get("compiledFrom"))
            gx_execution_hints = cls._coerce_mapping(payload.get("executionHints"))
            gx_execution_contract = cls._coerce_mapping(payload.get("executionContract"))
            gx_suite = payload.get("gxSuite") if isinstance(payload.get("gxSuite"), dict) else payload
            gx_payload = {
                "suiteId": row.validation_artifact_id,
                "suiteVersion": int(row.validation_artifact_version),
                "artifactVersion": str(row.artifact_contract_version or "v1"),
                "assignmentScope": {
                    "dataObjectId": row.data_object_id or gx_assignment_scope.get("dataObjectId"),
                    "datasetId": row.dataset_id or gx_assignment_scope.get("datasetId"),
                    "dataProductId": row.data_product_id or gx_assignment_scope.get("dataProductId"),
                },
                "resolvedExecutionScope": {
                    "dataObjectVersionIds": cls._coerce_string_list(
                        row.resolved_data_object_version_ids
                        if isinstance(row.resolved_data_object_version_ids, list)
                        else gx_resolved_scope.get("dataObjectVersionIds")
                    )
                },
                "gxSuite": gx_suite,
                "compiledFrom": {
                    **gx_compiled_from,
                    "ruleIds": cls._coerce_string_list(
                        row.compiled_rule_ids
                        if isinstance(row.compiled_rule_ids, list)
                        else gx_compiled_from.get("ruleIds")
                    ),
                    "compilerVersion": str(row.compiler_version or gx_compiled_from.get("compilerVersion") or "unknown"),
                    "generatedAt": cls._format_datetime(row.generated_at),
                },
                "executionHints": gx_execution_hints,
                "executionContract": gx_execution_contract,
                "savedBy": row.saved_by,
                "sourcePipeline": row.source_pipeline,
                "status": str(row.status or "") or None,
            }
            return build_validation_artifact_envelope_from_gx_artifact(gx_payload).model_dump(
                mode="python",
                by_alias=False,
                exclude_none=True,
            )

        assignment_scope = cls._coerce_mapping(payload.get("assignmentScope"))
        resolved_scope = cls._coerce_mapping(payload.get("resolvedExecutionScope"))
        compiled_from = cls._coerce_mapping(payload.get("compiledFrom"))

        result = dict(payload)
        result["validationArtifactId"] = row.validation_artifact_id
        result["validationArtifactVersion"] = int(row.validation_artifact_version)
        result["artifactContractVersion"] = str(row.artifact_contract_version or "v1")
        result["engineType"] = str(row.engine_type or "")
        result["assignmentScope"] = {
            "dataObjectId": row.data_object_id or assignment_scope.get("dataObjectId"),
            "datasetId": row.dataset_id or assignment_scope.get("datasetId"),
            "dataProductId": row.data_product_id or assignment_scope.get("dataProductId"),
        }
        result["resolvedExecutionScope"] = {
            "dataObjectVersionIds": cls._coerce_string_list(
                row.resolved_data_object_version_ids
                if isinstance(row.resolved_data_object_version_ids, list)
                else resolved_scope.get("dataObjectVersionIds")
            )
        }
        result["compiledFrom"] = {
            **compiled_from,
            "ruleIds": cls._coerce_string_list(
                row.compiled_rule_ids if isinstance(row.compiled_rule_ids, list) else compiled_from.get("ruleIds")
            ),
            "compilerVersion": str(row.compiler_version or compiled_from.get("compilerVersion") or "unknown"),
            "generatedAt": cls._format_datetime(row.generated_at),
        }
        result["status"] = str(row.status or "") or None
        result["savedBy"] = row.saved_by
        result["sourcePipeline"] = row.source_pipeline
        return result

    @staticmethod
    def _hash_payload(payload: dict) -> str:
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()