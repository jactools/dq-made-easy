from typing import Protocol

from app.domain.entities import ValidationRunEntity, ValidationRunListEntity


class ValidationRunRepository(Protocol):
    async def save_run(
        self,
        *,
        run_id: str,
        workspace: str | None,
        triggered_by: str | None,
        run_at: str,
        total: int,
        valid_count: int,
        invalid_count: int,
        status: str,
        items: list[dict],
    ) -> ValidationRunEntity:
        ...

    async def list_runs(
        self,
        workspace: str | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> ValidationRunListEntity:
        ...

    async def get_run(self, run_id: str) -> ValidationRunEntity | None:
        ...
