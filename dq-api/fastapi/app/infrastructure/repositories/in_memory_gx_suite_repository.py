from app.domain.entities import build_gx_artifact_envelope_from_validation_artifact
from app.domain.entities import build_validation_artifact_envelope_from_gx_artifact
from app.domain.entities import GxArtifactEnvelopeEntity
from app.domain.entities import GxSuiteStatusHistoryEntity
from app.infrastructure.repositories.in_memory_validation_artifact_repository import InMemoryValidationArtifactRepository


class InMemoryGxSuiteRepository:
    """In-memory GX suite repository backed by the neutral validation-artifact seam."""

    def __init__(self) -> None:
        self._artifacts = InMemoryValidationArtifactRepository()

    async def save_suite(
        self,
        *,
        envelope: GxArtifactEnvelopeEntity,
        status: str = "active",
        expected_existing_hash: str | None = None,
        saved_by: str | None = None,
        source_pipeline: str | None = None,
    ) -> GxArtifactEnvelopeEntity:
        artifact = build_validation_artifact_envelope_from_gx_artifact(envelope)
        saved_artifact = await self._artifacts.save_artifact(
            envelope=artifact,
            status=status,
            expected_existing_hash=expected_existing_hash,
            saved_by=saved_by,
            source_pipeline=source_pipeline,
        )
        return build_gx_artifact_envelope_from_validation_artifact(saved_artifact)

    async def list_suites(
        self,
        *,
        data_object_id: str | None = None,
        data_object_version_id: str | None = None,
        dataset_id: str | None = None,
        data_product_id: str | None = None,
        status: str = "active",
        latest_only: bool = True,
    ) -> list[GxArtifactEnvelopeEntity]:
        artifacts = await self._artifacts.list_artifacts(
            data_object_id=data_object_id,
            data_object_version_id=data_object_version_id,
            dataset_id=dataset_id,
            data_product_id=data_product_id,
            status=status,
            latest_only=latest_only,
        )
        return [build_gx_artifact_envelope_from_validation_artifact(item) for item in artifacts]

    async def list_suites_for_rule(
        self,
        *,
        rule_id: str,
        status: str = "active",
        latest_only: bool = True,
    ) -> list[GxArtifactEnvelopeEntity]:
        artifacts = await self._artifacts.list_artifacts_for_rule(
            rule_id=rule_id,
            status=status,
            latest_only=latest_only,
        )
        return [build_gx_artifact_envelope_from_validation_artifact(item) for item in artifacts]

    async def get_suite_by_id(
        self,
        *,
        suite_id: str,
        suite_version: int | None = None,
        status: str = "active",
    ) -> GxArtifactEnvelopeEntity | None:
        artifact = await self._artifacts.get_artifact_by_id(
            artifact_id=suite_id,
            artifact_version=suite_version,
            status=status,
        )
        if artifact is None:
            return None
        return build_gx_artifact_envelope_from_validation_artifact(artifact)

    async def patch_suite_status(
        self,
        *,
        suite_id: str,
        new_status: str,
        suite_version: int | None = None,
        changed_by: str | None = None,
        reason: str | None = None,
    ) -> GxArtifactEnvelopeEntity | None:
        artifact = await self._artifacts.patch_artifact_status(
            artifact_id=suite_id,
            artifact_version=suite_version,
            new_status=new_status,
            changed_by=changed_by,
            reason=reason,
        )
        if artifact is None:
            return None
        return build_gx_artifact_envelope_from_validation_artifact(artifact)

    async def list_suite_status_history(
        self,
        *,
        suite_id: str,
        suite_version: int | None = None,
    ) -> list[GxSuiteStatusHistoryEntity]:
        rows = await self._artifacts.list_artifact_status_history(
            artifact_id=suite_id,
            artifact_version=suite_version,
        )
        return [
            GxSuiteStatusHistoryEntity(
                suiteId=row.validationArtifactId,
                suiteVersion=row.validationArtifactVersion,
                fromStatus=row.fromStatus,
                toStatus=row.toStatus,
                changedBy=row.changedBy,
                changedAt=row.changedAt,
                reason=row.reason,
            )
            for row in rows
        ]
