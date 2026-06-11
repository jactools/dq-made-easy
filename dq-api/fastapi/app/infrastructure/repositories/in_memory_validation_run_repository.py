from __future__ import annotations

from copy import deepcopy
from uuid import uuid4

from app.domain.entities import ValidationRunEntity, ValidationRunItemEntity, ValidationRunListEntity
from app.domain.interfaces.v1.validation_run_repository import ValidationRunRepository


class InMemoryValidationRunRepository(ValidationRunRepository):
    def __init__(self) -> None:
        self._runs: dict[str, ValidationRunEntity] = {}

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
        record = ValidationRunEntity(
            id=run_id,
            workspace=workspace,
            triggered_by=triggered_by,
            run_at=run_at,
            total=total,
            valid_count=valid_count,
            invalid_count=invalid_count,
            status=status,
            validation_items=[
                ValidationRunItemEntity(
                    id=str(item.get("id") or uuid4()),
                    rule_id=str(item.get("ruleId") or ""),
                    rule_name=item.get("ruleName"),
                    rule_version_number=item.get("ruleVersionNumber"),
                    valid=bool(item.get("valid", False)),
                    errors=int(item.get("errors") or 0),
                    warnings=int(item.get("warnings") or 0),
                    diagnostics=list(deepcopy(item.get("diagnostics") or [])),
                    conflicts=list(deepcopy(item.get("conflicts") or [])),
                )
                for item in deepcopy(items)
            ],
        )
        self._runs[run_id] = record
        return record

    async def list_runs(
        self,
        workspace: str | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> ValidationRunListEntity:
        rows = [
            r for r in self._runs.values()
            if workspace is None or r.workspace == workspace
        ]
        # Most recent first
        rows.sort(key=lambda r: r.run_at or "", reverse=True)
        total = len(rows)
        page = rows[offset : offset + limit]
        return ValidationRunListEntity(data=deepcopy(page), total=total)

    async def get_run(self, run_id: str) -> ValidationRunEntity | None:
        run = self._runs.get(run_id)
        if run is None:
            return None
        return deepcopy(run)
