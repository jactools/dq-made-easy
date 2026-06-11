from __future__ import annotations

from copy import deepcopy
from typing import Any, Mapping

from app.domain.interfaces import ExceptionAnalysisSessionRepository


class InMemoryExceptionAnalysisSessionRepository(ExceptionAnalysisSessionRepository):
    def __init__(self) -> None:
        self._slices: dict[tuple[str, str], dict[str, Any]] = {}

    async def save_slice(self, slice_row: Mapping[str, Any]) -> Mapping[str, Any]:
        payload = deepcopy(dict(slice_row))
        key = (str(payload.get("analysisSessionId") or ""), str(payload.get("analysisSliceId") or ""))
        self._slices[key] = payload
        return deepcopy(payload)

    async def list_slices(self, analysis_session_id: str) -> list[Mapping[str, Any]]:
        rows = [deepcopy(row) for (session_id, _), row in self._slices.items() if session_id == analysis_session_id]
        rows.sort(key=lambda item: (int(item.get("sliceIndex") or 0), str(item.get("analysisSliceId") or "")))
        return rows

    async def get_slice(self, analysis_session_id: str, analysis_slice_id: str) -> Mapping[str, Any] | None:
        row = self._slices.get((analysis_session_id, analysis_slice_id))
        return deepcopy(row) if row is not None else None
