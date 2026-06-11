from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime
from uuid import uuid4

from app.domain.entities import (
    GxExecutionRunCreateEntity,
    GxExecutionRunEntity,
    GxExecutionRunListQueryEntity,
    GxExecutionRunStatusHistoryEntity,
    GxExecutionRunStatusTransitionEntity,
)
from app.domain.entities.gx_execution_run import (
    build_gx_execution_run_entity,
    build_gx_execution_run_list_query_entity,
    build_gx_execution_run_status_history_entity,
)
from app.domain.interfaces import GxExecutionRunRepository


class InMemoryGxExecutionRunRepository(GxExecutionRunRepository):
    def __init__(self) -> None:
        self._runs: dict[str, dict] = {}
        self._history: list[dict] = []

    async def create_run(self, run: GxExecutionRunCreateEntity) -> GxExecutionRunEntity:
        if run.runId in self._runs:
            raise ValueError(f"GX execution run '{run.runId}' already exists")

        now_iso = datetime.now(UTC).isoformat()
        self._runs[run.runId] = {
            "id": run.runId,
            "suiteId": run.suiteId,
            "suiteVersion": run.suiteVersion,
            "ruleId": run.ruleId,
            "ruleVersionId": run.ruleVersionId,
            "correlationId": run.correlationId,
            "requestedBy": run.requestedBy,
            "engineType": run.engineType,
            "engineTarget": run.engineTarget,
            "executionShape": run.executionShape,
            "status": run.status,
            "submittedAt": run.submittedAt,
            "startedAt": run.startedAt,
            "completedAt": run.completedAt,
            "executionProgress": deepcopy(run.executionProgress),
            "createdAt": now_iso,
            "updatedAt": now_iso,
            "executionContract": run.executionContract.model_dump(by_alias=True, exclude_none=True),
            "handoffPayload": (
                run.handoffPayload.model_dump(by_alias=True, exclude_none=True)
                if run.handoffPayload is not None
                else None
            ),
            "resultSummary": (
                run.resultSummary.model_dump(by_alias=True, exclude_none=True)
                if run.resultSummary is not None
                else {}
            ),
            "diagnostics": [item.model_dump(by_alias=True, exclude_none=True) for item in run.diagnostics or []],
            "failureCode": run.failureCode,
            "failureMessage": run.failureMessage,
            "comments": run.comments,
        }
        self._history.append(
            {
                "id": f"gx-run-hist-{uuid4().hex}",
                "runId": run.runId,
                "fromStatus": None,
                "toStatus": run.status,
                "changedBy": run.requestedBy,
                "changedAt": now_iso,
                "reason": run.statusReason,
                "details": deepcopy(run.statusDetails or {}),
            }
        )
        persisted = await self.get_run(run.runId)
        if persisted is None:
            raise RuntimeError(f"GX execution run '{run.runId}' was not persisted")
        return persisted

    async def get_run(self, run_id: str) -> GxExecutionRunEntity | None:
        run = self._runs.get(run_id)
        if run is None:
            return None
        return build_gx_execution_run_entity(
            {**deepcopy(run), "statusHistory": [entry.model_dump() for entry in await self.list_run_status_history(run_id)]}
        )

    async def list_runs(
        self,
        query: GxExecutionRunListQueryEntity | dict[str, object],
    ) -> list[GxExecutionRunEntity]:
        normalized_query = build_gx_execution_run_list_query_entity(query)
        rows: list[GxExecutionRunEntity] = []
        submitted_after = normalized_query.submittedAfter
        submitted_before = normalized_query.submittedBefore
        for run in self._runs.values():
            submitted_at = self._parse_iso_datetime(run.get("submittedAt"))
            if submitted_after is not None and (submitted_at is None or submitted_at < submitted_after):
                continue
            if submitted_before is not None and (submitted_at is None or submitted_at > submitted_before):
                continue
            if normalized_query.suiteId is not None and str(run.get("suiteId") or "") != normalized_query.suiteId:
                continue
            if normalized_query.ruleId is not None and str(run.get("ruleId") or "") != normalized_query.ruleId:
                continue
            if normalized_query.status is not None and str(run.get("status") or "") != normalized_query.status:
                continue
            rows.append(build_gx_execution_run_entity({**deepcopy(run)}))

        rows.sort(
            key=lambda item: (
                self._parse_iso_datetime(item.submittedAt) or datetime.min.replace(tzinfo=UTC),
                self._parse_iso_datetime(item.createdAt) or datetime.min.replace(tzinfo=UTC),
            ),
            reverse=True,
        )
        return rows

    async def list_run_status_history(self, run_id: str) -> list[GxExecutionRunStatusHistoryEntity]:
        rows = [entry for entry in self._history if str(entry.get("runId") or "") == run_id]
        rows.sort(key=lambda item: item.get("changedAt") or "")
        return [build_gx_execution_run_status_history_entity(entry) for entry in deepcopy(rows)]

    async def record_run_status_transition(
        self,
        transition: GxExecutionRunStatusTransitionEntity,
    ) -> GxExecutionRunEntity:
        run = self._runs.get(transition.runId)
        if run is None:
            raise ValueError(f"GX execution run '{transition.runId}' not found")

        now_iso = datetime.now(UTC).isoformat()
        old_status = str(run.get("status") or "") or None
        run["status"] = transition.newStatus
        if transition.startedAt is not None:
            run["startedAt"] = transition.startedAt
        if transition.completedAt is not None:
            run["completedAt"] = transition.completedAt
        if transition.executionProgress is not None:
            run["executionProgress"] = deepcopy(transition.executionProgress)
        if transition.newStatus == "running" and not run.get("startedAt"):
            run["startedAt"] = transition.startedAt or now_iso
        if transition.newStatus in {"succeeded", "failed", "cancelled"} and not run.get("completedAt"):
            run["completedAt"] = transition.completedAt or now_iso
        run["updatedAt"] = now_iso

        if transition.resultSummary is not None:
            run["resultSummary"] = transition.resultSummary.model_dump(by_alias=True, exclude_none=True)
        if transition.diagnostics is not None:
            run["diagnostics"] = [
                item.model_dump(by_alias=True, exclude_none=True) for item in transition.diagnostics
            ]
        if transition.failureCode is not None:
            run["failureCode"] = transition.failureCode
        if transition.failureMessage is not None:
            run["failureMessage"] = transition.failureMessage

        if old_status != transition.newStatus:
            self._history.append(
                {
                    "id": f"gx-run-hist-{uuid4().hex}",
                    "runId": transition.runId,
                    "fromStatus": old_status,
                    "toStatus": transition.newStatus,
                    "changedBy": transition.changedBy,
                    "changedAt": now_iso,
                    "reason": transition.reason,
                    "details": deepcopy(transition.details or {}),
                }
            )
        run_entity = await self.get_run(transition.runId)
        if run_entity is None:
            raise RuntimeError(f"GX execution run '{transition.runId}' was not persisted")
        return run_entity

    async def update_run_comments(self, run_id: str, comments: str | None) -> GxExecutionRunEntity | None:
        run = self._runs.get(run_id)
        if run is None:
            return None

        run["comments"] = str(comments or "").strip() or None
        run["updatedAt"] = datetime.now(UTC).isoformat()
        return await self.get_run(run_id)

    @staticmethod
    def _parse_iso_datetime(value: str | None) -> datetime | None:
        if value is None:
            return None
        payload = str(value).strip()
        if not payload:
            return None
        return datetime.fromisoformat(payload.replace("Z", "+00:00"))
