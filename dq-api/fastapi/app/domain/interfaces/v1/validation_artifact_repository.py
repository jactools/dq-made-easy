from typing import Protocol

from app.domain.entities import ValidationArtifactEnvelopeEntity
from app.domain.entities import ValidationArtifactStatusHistoryEntity


class ValidationArtifactRepository(Protocol):
    async def save_artifact(
        self,
        *,
        envelope: ValidationArtifactEnvelopeEntity,
        status: str = "active",
        expected_existing_hash: str | None = None,
        saved_by: str | None = None,
        source_pipeline: str | None = None,
    ) -> ValidationArtifactEnvelopeEntity:
        ...

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
        ...

    async def list_artifacts_for_rule(
        self,
        *,
        rule_id: str,
        status: str = "active",
        latest_only: bool = True,
    ) -> list[ValidationArtifactEnvelopeEntity]:
        ...

    async def get_artifact_by_id(
        self,
        *,
        artifact_id: str,
        artifact_version: int | None = None,
        status: str = "active",
    ) -> ValidationArtifactEnvelopeEntity | None:
        ...

    async def patch_artifact_status(
        self,
        *,
        artifact_id: str,
        new_status: str,
        artifact_version: int | None = None,
        changed_by: str | None = None,
        reason: str | None = None,
    ) -> ValidationArtifactEnvelopeEntity | None:
        ...

    async def list_artifact_status_history(
        self,
        *,
        artifact_id: str,
        artifact_version: int | None = None,
    ) -> list[ValidationArtifactStatusHistoryEntity]:
        ...