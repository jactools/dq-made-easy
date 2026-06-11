from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import select, and_

from app.domain.entities import ValidationRunEntity, ValidationRunItemEntity, ValidationRunListEntity
from app.domain.interfaces.v1.validation_run_repository import ValidationRunRepository
from app.infrastructure.orm.models import ValidationRunRow, ValidationRunItemRow
from app.infrastructure.orm.session import session_scope


def _serialize_datetime(value: datetime | None) -> str:
    if value is None:
        return datetime.now(UTC).isoformat()
    return value.isoformat()


def _to_validation_run_item_entity(row: ValidationRunItemRow) -> ValidationRunItemEntity:
    return ValidationRunItemEntity(
        id=str(row.id),
        rule_id=str(row.rule_id),
        rule_name=row.rule_name,
        rule_version_number=row.version_number,
        valid=bool(row.valid),
        errors=int(row.errors or 0),
        warnings=int(row.warnings or 0),
        diagnostics=list(row.diagnostics or []),
        conflicts=list(row.conflicts or []),
    )


def _to_validation_run_entity(
    run_row: ValidationRunRow,
    item_rows: list[ValidationRunItemRow] | None = None,
) -> ValidationRunEntity:
    return ValidationRunEntity(
        id=str(run_row.id),
        workspace=run_row.workspace,
        triggered_by=run_row.triggered_by,
        run_at=_serialize_datetime(run_row.run_at),
        total=int(run_row.total),
        valid_count=int(run_row.valid_count),
        invalid_count=int(run_row.invalid_count),
        status=str(run_row.status),
        validation_items=[_to_validation_run_item_entity(row) for row in (item_rows or [])],
    )


class PostgresValidationRunRepository(ValidationRunRepository):
    def __init__(self, database_url: str) -> None:
        self.database_url = database_url

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
        with session_scope(self.database_url) as session:
            run_row = ValidationRunRow(
                id=run_id,
                workspace=workspace,
                triggered_by=triggered_by,
                run_at=datetime.fromisoformat(run_at) if run_at else datetime.now(UTC),
                total=total,
                valid_count=valid_count,
                invalid_count=invalid_count,
                status=status,
            )
            session.add(run_row)
            # Flush parent row first so FK from validation_run_items can resolve run_id.
            session.flush()

            for item in items:
                item_row = ValidationRunItemRow(
                    id=str(uuid4()),
                    run_id=run_id,
                    rule_id=str(item.get("ruleId") or ""),
                    rule_name=item.get("ruleName"),
                    version_number=(
                        int(item.get("ruleVersionNumber"))
                        if item.get("ruleVersionNumber") is not None
                        else None
                    ),
                    valid=bool(item.get("valid", False)),
                    errors=int(item.get("errors") or 0),
                    warnings=int(item.get("warnings") or 0),
                    diagnostics=item.get("diagnostics"),
                    conflicts=item.get("conflicts"),
                )
                session.add(item_row)

            session.commit()

        persisted = await self.get_run(run_id)
        if persisted is None:
            raise RuntimeError(f"Persisted validation run '{run_id}' could not be reloaded")
        return persisted

    async def list_runs(
        self,
        workspace: str | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> ValidationRunListEntity:
        with session_scope(self.database_url) as session:
            stmt = select(ValidationRunRow)
            if workspace is not None:
                stmt = stmt.where(ValidationRunRow.workspace == workspace)
            stmt = stmt.order_by(ValidationRunRow.run_at.desc())

            total_stmt = stmt
            all_rows = session.execute(total_stmt).scalars().all()
            total = len(all_rows)

            stmt = stmt.limit(limit).offset(offset)
            rows = session.execute(stmt).scalars().all()

            data = [_to_validation_run_entity(r) for r in rows]
            return ValidationRunListEntity(data=data, total=total)

    async def get_run(self, run_id: str) -> ValidationRunEntity | None:
        with session_scope(self.database_url) as session:
            run_row = session.get(ValidationRunRow, run_id)
            if run_row is None:
                return None

            item_stmt = select(ValidationRunItemRow).where(
                ValidationRunItemRow.run_id == run_id
            )
            item_rows = session.execute(item_stmt).scalars().all()
            return _to_validation_run_entity(run_row, list(item_rows))
