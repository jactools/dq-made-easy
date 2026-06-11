from __future__ import annotations

import pytest

from app.infrastructure.repositories.in_memory_exception_analysis_session_repository import InMemoryExceptionAnalysisSessionRepository


@pytest.mark.anyio
async def test_analysis_session_repository_round_trips_slices() -> None:
    repo = InMemoryExceptionAnalysisSessionRepository()

    await repo.save_slice(
        {
            "analysisSessionId": "session-1",
            "analysisSliceId": "slice-1",
            "sliceIndex": 1,
            "dataObjectVersionId": "dov-1",
            "executionRunId": "run-1",
            "ruleId": "rule-1",
            "sliceLimit": 2,
            "anchorTotalCount": 3,
            "totalMatchingCount": 2,
            "returnedCount": 2,
            "truncated": False,
            "filters": {"reasonCodes": ["missing_value"]},
            "nextSliceSuggestion": {"reasonCodes": ["type_mismatch"]},
            "analysisPackUri": "s3://analysis-bucket/session-1/slice-1.json.gz",
            "analysisPackSha256": "sha256:abc",
            "createdAt": "2026-04-06T12:00:00+00:00",
            "updatedAt": "2026-04-06T12:00:00+00:00",
        }
    )
    await repo.save_slice(
        {
            "analysisSessionId": "session-1",
            "analysisSliceId": "slice-2",
            "sliceIndex": 2,
            "dataObjectVersionId": "dov-1",
            "executionRunId": "run-1",
            "ruleId": "rule-1",
            "sliceLimit": 2,
            "anchorTotalCount": 3,
            "totalMatchingCount": 1,
            "returnedCount": 1,
            "truncated": False,
            "filters": {"reasonCodes": ["type_mismatch"]},
            "nextSliceSuggestion": None,
            "analysisPackUri": "s3://analysis-bucket/session-1/slice-2.json.gz",
            "analysisPackSha256": "sha256:def",
            "createdAt": "2026-04-06T12:01:00+00:00",
            "updatedAt": "2026-04-06T12:01:00+00:00",
        }
    )

    slices = await repo.list_slices("session-1")
    assert [row["analysisSliceId"] for row in slices] == ["slice-1", "slice-2"]
    assert await repo.get_slice("session-1", "slice-1") is not None
    assert await repo.get_slice("session-1", "missing") is None
