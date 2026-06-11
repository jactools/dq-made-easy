from typing import Protocol

from app.domain.entities import DqResultEventEntity


class DqResultEventRepository(Protocol):
    async def record_result_event(self, event: DqResultEventEntity) -> DqResultEventEntity:
        ...

    async def list_result_events(
        self,
        *,
        rule_id: str | None = None,
        dataset_id: str | None = None,
        domain_id: str | None = None,
        data_product_id: str | None = None,
        severity: str | None = None,
        status: str | None = None,
        emitted_after: str | None = None,
        emitted_before: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[DqResultEventEntity]:
        ...