from collections.abc import Mapping
from typing import Any, Protocol

from app.domain.entities import (
    GxExecutionRunCreateEntity,
    GxExecutionRunEntity,
    GxExecutionRunListQueryEntity,
    GxExecutionRunStatusHistoryEntity,
    GxExecutionRunStatusTransitionEntity,
)


class GxExecutionRunRepository(Protocol):
    async def create_run(self, run: GxExecutionRunCreateEntity) -> GxExecutionRunEntity:
        ...

    async def get_run(self, run_id: str) -> GxExecutionRunEntity | None:
        ...

    async def list_runs(
        self,
        query: GxExecutionRunListQueryEntity | Mapping[str, Any],
    ) -> list[GxExecutionRunEntity]:
        ...

    async def list_run_status_history(self, run_id: str) -> list[GxExecutionRunStatusHistoryEntity]:
        ...

    async def record_run_status_transition(
        self,
        transition: GxExecutionRunStatusTransitionEntity,
    ) -> GxExecutionRunEntity:
        ...

    async def update_run_comments(self, run_id: str, comments: str | None) -> GxExecutionRunEntity | None:
        ...
