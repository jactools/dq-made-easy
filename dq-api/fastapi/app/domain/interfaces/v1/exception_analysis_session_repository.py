from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Protocol


class ExceptionAnalysisSessionRepository(Protocol):
    async def save_slice(self, slice_row: Mapping[str, Any]) -> Mapping[str, Any]:
        ...

    async def list_slices(self, analysis_session_id: str) -> list[Mapping[str, Any]]:
        ...

    async def get_slice(self, analysis_session_id: str, analysis_slice_id: str) -> Mapping[str, Any] | None:
        ...
