from __future__ import annotations

from types import SimpleNamespace

import pytest

import app.api.v1.endpoints.exceptions as exceptions_module
from app.main import app


class _FakeAdminRepository:
    def get_current_user(self, *_args, **_kwargs):
        return SimpleNamespace(
            granted_scopes=["dq:rules:read"],
            workspace_roles=[],
        )


class _FakeAnalysisService:
    async def create_session(self, request, *, analysis_session_id=None):
        return {
            "analysisSessionId": analysis_session_id or "analysis-session-1",
            "dataObjectVersionId": request["dataObjectVersionId"],
            "executionRunId": request["executionRunId"],
            "ruleId": request["ruleId"],
            "anchorTotalCount": 2,
            "sliceCount": 1,
            "analysisStatus": {
                "state": "in_progress",
                "reason": "The analysis session has remaining uncovered exception space.",
                "progressPercent": 50.0,
                "remainingCount": 1,
                "estimatedRemainingRecordCount": 1,
                "estimatedRemainingSliceCount": 1,
                "estimatedCostImpact": "Approximately 1 additional slice(s) covering 1 uncovered record(s).",
                "sliceCount": 1,
                "materializedRecordCount": 1,
                "maxSlices": None,
                "maxRecords": None,
                "maxSeconds": None,
                "budgetHit": False,
                "exhausted": False,
                "stalled": False,
            },
            "createdAt": "2026-04-06T12:00:00+00:00",
            "updatedAt": "2026-04-06T12:00:00+00:00",
            "currentSlice": {
                "analysisSessionId": analysis_session_id or "analysis-session-1",
                "analysisSliceId": "slice-1",
                "sliceIndex": 1,
                "dataObjectVersionId": request["dataObjectVersionId"],
                "executionRunId": request["executionRunId"],
                "ruleId": request["ruleId"],
                "sliceLimit": 2,
                "anchorTotalCount": 2,
                "totalMatchingCount": 1,
                "returnedCount": 1,
                "truncated": False,
                "analysisPackUri": "s3://analysis-bucket/analysis-session-1/slice-1.json.gz",
                "analysisPackSha256": "sha256:abc",
                "analysisManifestUri": "s3://analysis-bucket/analysis-session-1/slice-1.manifest.json.gz",
                "analysisManifestSha256": "sha256:manifest-abc",
                "filters": request,
                "nextSliceSuggestion": {
                    "reasonCodes": ["type_mismatch"],
                    "failureClass": None,
                    "recordIdentifierType": None,
                    "recordIdentifierValueContains": None,
                    "search": None,
                    "remainingCount": 1,
                    "partitionStrategy": ["reason_code"],
                    "rationale": "1 uncovered exception fact shares reason_code 'type_mismatch'.",
                },
                "analysisStatus": {
                    "state": "in_progress",
                    "reason": "The analysis session has remaining uncovered exception space.",
                    "progressPercent": 50.0,
                    "remainingCount": 1,
                    "estimatedRemainingRecordCount": 1,
                    "estimatedRemainingSliceCount": 1,
                    "estimatedCostImpact": "Approximately 1 additional slice(s) covering 1 uncovered record(s).",
                    "sliceCount": 1,
                    "materializedRecordCount": 1,
                    "maxSlices": None,
                    "maxRecords": None,
                    "maxSeconds": None,
                    "budgetHit": False,
                    "exhausted": False,
                    "stalled": False,
                },
                "createdAt": "2026-04-06T12:00:00+00:00",
                "updatedAt": "2026-04-06T12:00:00+00:00",
                "records": [],
            },
            "slices": [
                {
                    "analysisSessionId": analysis_session_id or "analysis-session-1",
                    "analysisSliceId": "slice-1",
                    "sliceIndex": 1,
                    "dataObjectVersionId": request["dataObjectVersionId"],
                    "executionRunId": request["executionRunId"],
                    "ruleId": request["ruleId"],
                    "sliceLimit": 2,
                    "anchorTotalCount": 2,
                    "totalMatchingCount": 1,
                    "returnedCount": 1,
                    "truncated": False,
                    "analysisPackUri": "s3://analysis-bucket/analysis-session-1/slice-1.json.gz",
                    "analysisPackSha256": "sha256:abc",
                    "analysisManifestUri": "s3://analysis-bucket/analysis-session-1/slice-1.manifest.json.gz",
                    "analysisManifestSha256": "sha256:manifest-abc",
                    "filters": request,
                    "nextSliceSuggestion": {
                        "reasonCodes": ["type_mismatch"],
                        "failureClass": None,
                        "recordIdentifierType": None,
                        "recordIdentifierValueContains": None,
                        "search": None,
                        "remainingCount": 1,
                        "partitionStrategy": ["reason_code"],
                        "rationale": "1 uncovered exception fact shares reason_code 'type_mismatch'.",
                    },
                    "analysisStatus": {
                        "state": "in_progress",
                        "reason": "The analysis session has remaining uncovered exception space.",
                        "progressPercent": 50.0,
                        "remainingCount": 1,
                        "estimatedRemainingRecordCount": 1,
                        "estimatedRemainingSliceCount": 1,
                        "estimatedCostImpact": "Approximately 1 additional slice(s) covering 1 uncovered record(s).",
                        "sliceCount": 1,
                        "materializedRecordCount": 1,
                        "maxSlices": None,
                        "maxRecords": None,
                        "maxSeconds": None,
                        "budgetHit": False,
                        "exhausted": False,
                        "stalled": False,
                    },
                    "createdAt": "2026-04-06T12:00:00+00:00",
                    "updatedAt": "2026-04-06T12:00:00+00:00",
                }
            ],
        }


@pytest.fixture(autouse=True)
def _analysis_session_test_overrides(monkeypatch: pytest.MonkeyPatch):
    app.dependency_overrides[exceptions_module.get_admin_repository] = lambda: _FakeAdminRepository()
    monkeypatch.setattr(exceptions_module, "_resolve_workspace_for_data_object_version", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(exceptions_module, "_build_exception_analysis_session_service", lambda *_args, **_kwargs: _FakeAnalysisService())
    yield
    app.dependency_overrides.pop(exceptions_module.get_admin_repository, None)


def test_create_exception_analysis_session_returns_projected_fact_payload(client, auth_headers) -> None:
    response = client.post(
        "/rulebuilder/v1/exceptions/analysis-sessions",
        headers=auth_headers("dq:rules:write"),
        json={
            "data_object_version_id": "dov-1",
            "execution_run_id": "run-1",
            "rule_id": "rule-1",
            "reason_codes": ["missing_value"],
            "slice_limit": 2,
            "summary_only": True,
        },
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["analysis_session_id"] == "analysis-session-1"
    assert payload["current_slice"]["records"] == []
    assert payload["current_slice"]["next_slice_suggestion"]["reason_codes"] == ["type_mismatch"]
    assert payload["current_slice"]["next_slice_suggestion"]["partition_strategy"] == ["reason_code"]
    assert payload["current_slice"]["analysis_manifest_uri"].endswith(".manifest.json.gz")
    assert payload["analysis_status"]["progress_percent"] == 50.0
    assert payload["analysis_status"]["estimated_remaining_record_count"] == 1
    assert payload["analysis_status"]["estimated_remaining_slice_count"] == 1
    assert payload["analysis_status"]["estimated_cost_impact"].startswith("Approximately 1 additional slice")
