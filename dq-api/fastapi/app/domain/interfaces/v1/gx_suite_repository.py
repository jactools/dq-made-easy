from typing import Protocol

from app.domain.entities import GxArtifactEnvelopeEntity
from app.domain.entities import GxSuiteStatusHistoryEntity


class GxSuiteRepository(Protocol):
    async def save_suite(
        self,
        *,
        envelope: GxArtifactEnvelopeEntity,
        status: str = "active",
        expected_existing_hash: str | None = None,
        saved_by: str | None = None,
        source_pipeline: str | None = None,
    ) -> GxArtifactEnvelopeEntity:
        ...

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
        ...

    async def list_suites_for_rule(
        self,
        *,
        rule_id: str,
        status: str = "active",
        latest_only: bool = True,
    ) -> list[GxArtifactEnvelopeEntity]:
        ...

    async def get_suite_by_id(
        self,
        *,
        suite_id: str,
        suite_version: int | None = None,
        status: str = "active",
    ) -> GxArtifactEnvelopeEntity | None:
        ...

    async def patch_suite_status(
        self,
        *,
        suite_id: str,
        new_status: str,
        suite_version: int | None = None,
        changed_by: str | None = None,
        reason: str | None = None,
    ) -> GxArtifactEnvelopeEntity | None:
        ...

    async def list_suite_status_history(
        self,
        *,
        suite_id: str,
        suite_version: int | None = None,
    ) -> list[GxSuiteStatusHistoryEntity]:
        ...
