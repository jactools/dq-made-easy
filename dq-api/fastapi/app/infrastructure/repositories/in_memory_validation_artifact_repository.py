import hashlib
import json
from datetime import datetime, timezone

from app.domain.entities import build_validation_artifact_envelope_entity
from app.domain.entities import build_validation_artifact_status_history_entities
from app.domain.entities import ValidationArtifactEnvelopeEntity
from app.domain.entities import ValidationArtifactStatusHistoryEntity
from app.domain.interfaces.v1.validation_artifact_repository import ValidationArtifactRepository


class InMemoryValidationArtifactRepository(ValidationArtifactRepository):
    def __init__(self) -> None:
        self._artifacts: list[dict] = []
        self._history: list[dict] = []

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
            mode="python", by_alias=False, exclude_none=True
        )
        normalized["status"] = status
        normalized["savedBy"] = saved_by
        normalized["sourcePipeline"] = source_pipeline

        artifact_id = str(normalized.get("validationArtifactId") or "")
        artifact_version = int(normalized.get("validationArtifactVersion") or 0)
        now_iso = datetime.now(timezone.utc).isoformat()

        for index, item in enumerate(self._artifacts):
            if str(item.get("validationArtifactId") or "") != artifact_id:
                continue
            if int(item.get("validationArtifactVersion") or 0) != artifact_version:
                continue

            existing_hash = self._hash_payload(item)
            incoming_hash = self._hash_payload(normalized)
            if existing_hash != incoming_hash and expected_existing_hash != existing_hash:
                raise ValueError("Validation artifact overwrite conflict: expected hash does not match current artifact")

            old_status = str(item.get("status") or "")
            self._artifacts[index] = normalized
            if old_status != status:
                self._history.append({
                    "validationArtifactId": artifact_id,
                    "validationArtifactVersion": artifact_version,
                    "fromStatus": old_status or None,
                    "toStatus": status,
                    "changedBy": saved_by,
                    "changedAt": now_iso,
                    "reason": None,
                })

            result = dict(normalized)
            result["artifactHash"] = incoming_hash
            return build_validation_artifact_envelope_entity(result)

        self._artifacts.append(normalized)
        self._history.append({
            "validationArtifactId": artifact_id,
            "validationArtifactVersion": artifact_version,
            "fromStatus": None,
            "toStatus": status,
            "changedBy": saved_by,
            "changedAt": now_iso,
            "reason": None,
        })
        result = dict(normalized)
        result["artifactHash"] = self._hash_payload(normalized)
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
        matches = []
        for item in self._artifacts:
            if str(item.get("status") or "") != str(status):
                continue

            assignment_scope = item.get("assignmentScope") if isinstance(item.get("assignmentScope"), dict) else {}
            resolved_scope = item.get("resolvedExecutionScope") if isinstance(item.get("resolvedExecutionScope"), dict) else {}
            version_ids = resolved_scope.get("dataObjectVersionIds") if isinstance(resolved_scope.get("dataObjectVersionIds"), list) else []

            if data_object_id and str(assignment_scope.get("dataObjectId") or "") != str(data_object_id):
                continue
            if dataset_id and str(assignment_scope.get("datasetId") or "") != str(dataset_id):
                continue
            if data_product_id and str(assignment_scope.get("dataProductId") or "") != str(data_product_id):
                continue
            if data_object_version_id and str(data_object_version_id) not in [str(value) for value in version_ids]:
                continue
            matches.append(item)

        if not latest_only:
            return [build_validation_artifact_envelope_entity(item) for item in matches]

        latest_by_artifact: dict[str, dict] = {}
        for item in matches:
            artifact_id = str(item.get("validationArtifactId") or "")
            if not artifact_id:
                continue
            existing = latest_by_artifact.get(artifact_id)
            if existing is None or int(item.get("validationArtifactVersion") or 0) > int(existing.get("validationArtifactVersion") or 0):
                latest_by_artifact[artifact_id] = item
        return [build_validation_artifact_envelope_entity(item) for item in latest_by_artifact.values()]

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

        matches = []
        for item in self._artifacts:
            if str(item.get("status") or "") != str(status):
                continue
            compiled_from = item.get("compiledFrom") if isinstance(item.get("compiledFrom"), dict) else {}
            rule_ids = compiled_from.get("ruleIds") if isinstance(compiled_from.get("ruleIds"), list) else []
            if normalized_rule_id not in [str(value) for value in rule_ids]:
                continue
            matches.append(item)

        if not latest_only:
            return [build_validation_artifact_envelope_entity(item) for item in matches]

        latest_by_artifact: dict[str, dict] = {}
        for item in matches:
            artifact_id = str(item.get("validationArtifactId") or "")
            if not artifact_id:
                continue
            existing = latest_by_artifact.get(artifact_id)
            if existing is None or int(item.get("validationArtifactVersion") or 0) > int(existing.get("validationArtifactVersion") or 0):
                latest_by_artifact[artifact_id] = item
        return [build_validation_artifact_envelope_entity(item) for item in latest_by_artifact.values()]

    async def get_artifact_by_id(
        self,
        *,
        artifact_id: str,
        artifact_version: int | None = None,
        status: str = "active",
    ) -> ValidationArtifactEnvelopeEntity | None:
        matches = [
            item
            for item in self._artifacts
            if str(item.get("validationArtifactId") or "") == str(artifact_id)
            and str(item.get("status") or "") == str(status)
        ]
        if not matches:
            return None

        if artifact_version is not None:
            for item in matches:
                if int(item.get("validationArtifactVersion") or 0) == artifact_version:
                    return build_validation_artifact_envelope_entity(item)
            return None

        return build_validation_artifact_envelope_entity(
            max(matches, key=lambda item: int(item.get("validationArtifactVersion") or 0))
        )

    async def patch_artifact_status(
        self,
        *,
        artifact_id: str,
        new_status: str,
        artifact_version: int | None = None,
        changed_by: str | None = None,
        reason: str | None = None,
    ) -> ValidationArtifactEnvelopeEntity | None:
        matches = [item for item in self._artifacts if str(item.get("validationArtifactId") or "") == str(artifact_id)]
        if not matches:
            return None

        if artifact_version is not None:
            target = next(
                (item for item in matches if int(item.get("validationArtifactVersion") or 0) == artifact_version),
                None,
            )
        else:
            target = max(matches, key=lambda item: int(item.get("validationArtifactVersion") or 0))

        if target is None:
            return None

        old_status = str(target.get("status") or "")
        target["status"] = new_status
        self._history.append({
            "validationArtifactId": str(target.get("validationArtifactId") or ""),
            "validationArtifactVersion": int(target.get("validationArtifactVersion") or 0),
            "fromStatus": old_status or None,
            "toStatus": new_status,
            "changedBy": changed_by,
            "changedAt": datetime.now(timezone.utc).isoformat(),
            "reason": reason,
        })
        return build_validation_artifact_envelope_entity(target)

    async def list_artifact_status_history(
        self,
        *,
        artifact_id: str,
        artifact_version: int | None = None,
    ) -> list[ValidationArtifactStatusHistoryEntity]:
        rows = [h for h in self._history if str(h.get("validationArtifactId") or "") == str(artifact_id)]
        if artifact_version is not None:
            rows = [h for h in rows if int(h.get("validationArtifactVersion") or 0) == artifact_version]
        return build_validation_artifact_status_history_entities(rows)

    @staticmethod
    def _hash_payload(payload: dict) -> str:
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()