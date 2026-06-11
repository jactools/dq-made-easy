from __future__ import annotations

import gzip
import json

import pytest

from app.domain.entities import GxExecutionViolationCreateEntity
from app.application.services.exception_analysis_session_service import ExceptionAnalysisSessionService
from app.application.services.exception_analysis_session_service import S3ExceptionAnalysisSliceStorageBackend
from app.infrastructure.repositories.in_memory_exception_analysis_session_repository import InMemoryExceptionAnalysisSessionRepository
from app.infrastructure.repositories.in_memory_gx_execution_violation_repository import InMemoryGxExecutionViolationRepository


class _FakeAnalysisPackStorageBackend:
    def __init__(self) -> None:
        self._payloads: dict[str, dict[str, object]] = {}
        self._counter = 0

    async def persist_analysis_pack(
        self,
        payload,
        *,
        analysis_session_id: str,
        analysis_slice_id: str,
        data_object_version_id: str,
        execution_run_id: str,
        rule_id: str,
    ) -> dict[str, str]:
        self._counter += 1
        pack_uri = f"s3://analysis-bucket/{analysis_session_id}/{analysis_slice_id}/{self._counter}.pack.json.gz"
        manifest_uri = f"s3://analysis-bucket/{analysis_session_id}/{analysis_slice_id}/{self._counter}.manifest.json.gz"
        pack_payload = dict(payload)
        self._payloads[pack_uri] = pack_payload
        manifest_payload = {key: value for key, value in pack_payload.items() if key != "records"}
        manifest_payload["analysisPackUri"] = pack_uri
        manifest_payload["analysisPackSha256"] = f"sha256:{self._counter:02d}"
        self._payloads[manifest_uri] = manifest_payload
        return {
            "analysisPackUri": pack_uri,
            "analysisPackSha256": f"sha256:{self._counter:02d}",
            "analysisManifestUri": manifest_uri,
            "analysisManifestSha256": f"sha256:manifest:{self._counter:02d}",
        }

    async def load_analysis_pack(self, analysis_pack_uri: str) -> dict[str, object]:
        return dict(self._payloads[analysis_pack_uri])


@pytest.mark.anyio
async def test_analysis_session_service_persists_pack_and_suggests_next_slice() -> None:
    violation_repository = InMemoryGxExecutionViolationRepository()
    session_repository = InMemoryExceptionAnalysisSessionRepository()
    storage_backend = _FakeAnalysisPackStorageBackend()
    service = ExceptionAnalysisSessionService(
        violation_repository=violation_repository,
        session_repository=session_repository,
        storage_backend=storage_backend,
    )

    await violation_repository.save_violations(
        [
            GxExecutionViolationCreateEntity(
                id="vio-1",
                dataObjectVersionId="dov-1",
                executionRunId="run-1",
                ruleId="rule-1",
                dataPrimaryKey="row-1",
                violationReason="missing value",
                opsMetadata={
                    "reason_code": "missing_value",
                    "reason_text": "missing value",
                    "record_identifier_type": "primary_key",
                    "record_identifier_value": "row-1",
                },
                detectedAt="2026-04-06T12:00:00+00:00",
            ),
            GxExecutionViolationCreateEntity(
                id="vio-2",
                dataObjectVersionId="dov-1",
                executionRunId="run-1",
                ruleId="rule-1",
                dataPrimaryKey="row-2",
                violationReason="missing value",
                opsMetadata={
                    "reason_code": "missing_value",
                    "reason_text": "missing value",
                    "record_identifier_type": "primary_key",
                    "record_identifier_value": "row-2",
                },
                detectedAt="2026-04-06T12:01:00+00:00",
            ),
            GxExecutionViolationCreateEntity(
                id="vio-3",
                dataObjectVersionId="dov-1",
                executionRunId="run-1",
                ruleId="rule-1",
                dataPrimaryKey="row-3",
                violationReason="type mismatch",
                opsMetadata={
                    "reason_code": "type_mismatch",
                    "reason_text": "type mismatch",
                    "record_identifier_type": "primary_key",
                    "record_identifier_value": "row-3",
                },
                detectedAt="2026-04-06T12:02:00+00:00",
            ),
        ]
    )

    session = await service.create_session(
        {
            "dataObjectVersionId": "dov-1",
            "executionRunId": "run-1",
            "ruleId": "rule-1",
            "reasonCodes": ["missing_value"],
            "sliceLimit": 2,
        }
    )

    assert session["sliceCount"] == 1
    assert session["currentSlice"]["returnedCount"] == 2
    assert session["currentSlice"]["totalMatchingCount"] == 2
    assert session["currentSlice"]["truncated"] is False
    assert session["currentSlice"]["nextSliceSuggestion"]["reasonCodes"] == ["type_mismatch"]
    assert session["currentSlice"]["nextSliceSuggestion"]["partitionStrategy"] == ["reason_code"]
    assert session["currentSlice"]["analysisManifestUri"].endswith(".manifest.json.gz")
    assert session["analysisStatus"]["progressPercent"] == 66.7
    assert session["analysisStatus"]["estimatedRemainingRecordCount"] == 1
    assert session["analysisStatus"]["estimatedRemainingSliceCount"] == 1
    assert session["analysisStatus"]["estimatedCostImpact"] == "Approximately 1 additional slice(s) covering 1 uncovered record(s)."
    assert session["currentSlice"]["records"][0]["id"] == "vio-1"
    assert session["currentSlice"]["analysisPackUri"].startswith("s3://analysis-bucket/")

    follow_up = await service.create_session(
        {
            "dataObjectVersionId": "dov-1",
            "executionRunId": "run-1",
            "ruleId": "rule-1",
            "reasonCodes": ["type_mismatch"],
            "sliceLimit": 2,
        },
        analysis_session_id=session["analysisSessionId"],
    )

    assert follow_up["sliceCount"] == 2
    assert [row["analysisSliceId"] for row in follow_up["slices"]] == [
        session["currentSlice"]["analysisSliceId"],
        follow_up["currentSlice"]["analysisSliceId"],
    ]
    assert follow_up["currentSlice"]["nextSliceSuggestion"]["partitionStrategy"] == ["reason_code"]
    assert follow_up["currentSlice"]["analysisManifestUri"].endswith(".manifest.json.gz")
    assert follow_up["analysisStatus"]["progressPercent"] == 100.0
    assert follow_up["analysisStatus"]["estimatedRemainingRecordCount"] == 2
    assert follow_up["analysisStatus"]["estimatedRemainingSliceCount"] == 1
    assert follow_up["analysisStatus"]["estimatedCostImpact"] == "Approximately 1 additional slice(s) covering 2 uncovered record(s)."


@pytest.mark.anyio
async def test_analysis_session_service_can_run_until_budget_is_hit() -> None:
    violation_repository = InMemoryGxExecutionViolationRepository()
    session_repository = InMemoryExceptionAnalysisSessionRepository()
    storage_backend = _FakeAnalysisPackStorageBackend()
    service = ExceptionAnalysisSessionService(
        violation_repository=violation_repository,
        session_repository=session_repository,
        storage_backend=storage_backend,
    )

    await violation_repository.save_violations(
        [
            GxExecutionViolationCreateEntity(
                id="vio-1",
                dataObjectVersionId="dov-1",
                executionRunId="run-1",
                ruleId="rule-1",
                dataPrimaryKey="row-1",
                violationReason="missing value",
                opsMetadata={
                    "reason_code": "missing_value",
                    "reason_text": "missing value",
                    "record_identifier_type": "primary_key",
                    "record_identifier_value": "row-1",
                },
                detectedAt="2026-04-06T12:00:00+00:00",
            ),
            GxExecutionViolationCreateEntity(
                id="vio-2",
                dataObjectVersionId="dov-1",
                executionRunId="run-1",
                ruleId="rule-1",
                dataPrimaryKey="row-2",
                violationReason="missing value",
                opsMetadata={
                    "reason_code": "missing_value",
                    "reason_text": "missing value",
                    "record_identifier_type": "primary_key",
                    "record_identifier_value": "row-2",
                },
                detectedAt="2026-04-06T12:01:00+00:00",
            ),
            GxExecutionViolationCreateEntity(
                id="vio-3",
                dataObjectVersionId="dov-1",
                executionRunId="run-1",
                ruleId="rule-1",
                dataPrimaryKey="row-3",
                violationReason="type mismatch",
                opsMetadata={
                    "reason_code": "type_mismatch",
                    "reason_text": "type mismatch",
                    "record_identifier_type": "primary_key",
                    "record_identifier_value": "row-3",
                },
                detectedAt="2026-04-06T12:02:00+00:00",
            ),
        ]
    )

    session = await service.create_session(
        {
            "dataObjectVersionId": "dov-1",
            "executionRunId": "run-1",
            "ruleId": "rule-1",
            "reasonCodes": ["missing_value"],
            "sliceLimit": 1,
            "runUntilExhausted": True,
            "maxSlices": 2,
        }
    )

    assert session["sliceCount"] == 2
    assert session["analysisStatus"]["state"] == "budget_hit"
    assert session["analysisStatus"]["budgetHit"] is True
    assert session["analysisStatus"]["maxSlices"] == 2
    assert session["currentSlice"]["nextSliceSuggestion"]["partitionStrategy"] == ["reason_code"]
    assert session["currentSlice"]["analysisManifestUri"].endswith(".manifest.json.gz")
    assert session["analysisStatus"]["progressPercent"] == 66.7
    assert session["analysisStatus"]["estimatedRemainingRecordCount"] == 2
    assert session["analysisStatus"]["estimatedRemainingSliceCount"] == 2
    assert session["analysisStatus"]["estimatedCostImpact"] == "Approximately 2 additional slice(s) covering 2 uncovered record(s)."
    assert [row["analysisSliceId"] for row in session["slices"]] == [
        session["slices"][0]["analysisSliceId"],
        session["slices"][1]["analysisSliceId"],
    ]


@pytest.mark.anyio
async def test_analysis_session_service_supports_summary_first_adaptive_resume_flow() -> None:
    violation_repository = InMemoryGxExecutionViolationRepository()
    session_repository = InMemoryExceptionAnalysisSessionRepository()
    storage_backend = _FakeAnalysisPackStorageBackend()
    service = ExceptionAnalysisSessionService(
        violation_repository=violation_repository,
        session_repository=session_repository,
        storage_backend=storage_backend,
    )

    violations: list[GxExecutionViolationCreateEntity] = []
    for index in range(1, 14):
        reason_code = "missing_value" if index == 1 else "type_mismatch"
        violations.append(
            GxExecutionViolationCreateEntity(
                id=f"vio-{index}",
                dataObjectVersionId="dov-1",
                executionRunId="run-1",
                ruleId="rule-1",
                dataPrimaryKey=f"row-{index}",
                violationReason=reason_code.replace("_", " "),
                opsMetadata={
                    "reason_code": reason_code,
                    "reason_text": reason_code.replace("_", " "),
                    "record_identifier_type": "primary_key",
                    "record_identifier_value": f"row-{index}",
                },
                detectedAt=f"2026-04-06T12:{index:02d}:00+00:00",
            )
        )

    await violation_repository.save_violations(violations)

    session = await service.create_session(
        {
            "dataObjectVersionId": "dov-1",
            "executionRunId": "run-1",
            "ruleId": "rule-1",
            "reasonCodes": ["missing_value"],
            "sliceLimit": 1,
            "summaryOnly": True,
            "runUntilExhausted": True,
            "maxSlices": 2,
        }
    )

    assert session["sliceCount"] == 2
    assert session["currentSlice"]["records"] == []
    assert session["slices"][0]["sliceLimit"] == 1
    assert session["slices"][1]["sliceLimit"] == 2
    assert session["analysisStatus"]["state"] == "budget_hit"
    assert session["analysisStatus"]["budgetHit"] is True
    assert session["analysisStatus"]["estimatedRemainingSliceCount"] >= 1
    assert session["analysisStatus"]["estimatedCostImpact"].startswith("Approximately ")

    summary_view = await service.get_session_summary(session["analysisSessionId"])
    assert summary_view is not None
    assert summary_view["currentSlice"]["records"] == []
    assert summary_view["analysisStatus"]["sliceCount"] == 2

    detail_view = await service.get_session(session["analysisSessionId"])
    assert detail_view is not None
    assert detail_view["currentSlice"]["records"]
    assert detail_view["currentSlice"]["analysisSliceId"] == session["currentSlice"]["analysisSliceId"]
    assert detail_view["analysisStatus"]["progressPercent"] == session["analysisStatus"]["progressPercent"]


@pytest.mark.anyio
async def test_analysis_session_service_plans_detected_at_buckets_for_remaining_records() -> None:
    violation_repository = InMemoryGxExecutionViolationRepository()
    session_repository = InMemoryExceptionAnalysisSessionRepository()
    storage_backend = _FakeAnalysisPackStorageBackend()
    service = ExceptionAnalysisSessionService(
        violation_repository=violation_repository,
        session_repository=session_repository,
        storage_backend=storage_backend,
    )

    await violation_repository.save_violations(
        [
            GxExecutionViolationCreateEntity(
                id="vio-1",
                dataObjectVersionId="dov-1",
                executionRunId="run-1",
                ruleId="rule-1",
                dataPrimaryKey="row-1",
                violationReason="missing value",
                opsMetadata={
                    "reason_code": "missing_value",
                    "reason_text": "missing value",
                    "record_identifier_type": "primary_key",
                    "record_identifier_value": "row-1",
                    "failure_class": "expectation_failed",
                },
                detectedAt="2026-04-06T01:00:00+00:00",
            ),
            GxExecutionViolationCreateEntity(
                id="vio-2",
                dataObjectVersionId="dov-1",
                executionRunId="run-1",
                ruleId="rule-1",
                dataPrimaryKey="row-2",
                violationReason="type mismatch",
                opsMetadata={
                    "reason_code": "type_mismatch",
                    "reason_text": "type mismatch",
                    "record_identifier_type": "primary_key",
                    "record_identifier_value": "row-2",
                    "failure_class": "expectation_failed",
                },
                detectedAt="2026-04-06T02:00:00+00:00",
            ),
            GxExecutionViolationCreateEntity(
                id="vio-3",
                dataObjectVersionId="dov-1",
                executionRunId="run-1",
                ruleId="rule-1",
                dataPrimaryKey="row-3",
                violationReason="type mismatch",
                opsMetadata={
                    "reason_code": "type_mismatch",
                    "reason_text": "type mismatch",
                    "record_identifier_type": "primary_key",
                    "record_identifier_value": "row-3",
                    "failure_class": "expectation_failed",
                },
                detectedAt="2026-04-07T03:00:00+00:00",
            ),
        ]
    )

    session = await service.create_session(
        {
            "dataObjectVersionId": "dov-1",
            "executionRunId": "run-1",
            "ruleId": "rule-1",
            "reasonCodes": ["missing_value", "type_mismatch"],
            "failureClass": "expectation_failed",
            "recordIdentifierType": "primary_key",
            "sliceLimit": 1,
            "runUntilExhausted": True,
            "maxSlices": 1,
        }
    )

    assert session["sliceCount"] == 1
    assert session["analysisStatus"]["budgetHit"] is True
    assert session["currentSlice"]["nextSliceSuggestion"]["partitionStrategy"] == ["detected_at_bucket"]
    assert session["currentSlice"]["nextSliceSuggestion"]["detectedAfter"] == "2026-04-06T00:00:00+00:00"
    assert session["currentSlice"]["nextSliceSuggestion"]["detectedBefore"] == "2026-04-07T00:00:00+00:00"

    resumed = await service.create_session(
        {
            "dataObjectVersionId": "dov-1",
            "executionRunId": "run-1",
            "ruleId": "rule-1",
            "sliceLimit": 1,
            "runUntilExhausted": True,
            "maxSlices": 2,
        },
        analysis_session_id=session["analysisSessionId"],
    )

    assert resumed["sliceCount"] == 2
    assert resumed["currentSlice"]["filters"]["detectedAfter"] == "2026-04-06T00:00:00+00:00"
    assert resumed["currentSlice"]["filters"]["detectedBefore"] == "2026-04-07T00:00:00+00:00"
    assert resumed["currentSlice"]["nextSliceSuggestion"] is not None


@pytest.mark.anyio
async def test_analysis_session_service_plans_hash_stripes_when_date_buckets_do_not_split_remaining_records() -> None:
    violation_repository = InMemoryGxExecutionViolationRepository()
    session_repository = InMemoryExceptionAnalysisSessionRepository()
    storage_backend = _FakeAnalysisPackStorageBackend()
    service = ExceptionAnalysisSessionService(
        violation_repository=violation_repository,
        session_repository=session_repository,
        storage_backend=storage_backend,
    )

    await violation_repository.save_violations(
        [
            GxExecutionViolationCreateEntity(
                id=f"vio-{index}",
                dataObjectVersionId="dov-1",
                executionRunId="run-1",
                ruleId="rule-1",
                dataPrimaryKey=f"row-{index}",
                violationReason="type mismatch",
                opsMetadata={
                    "reason_code": "type_mismatch",
                    "reason_text": "type mismatch",
                    "record_identifier_type": "primary_key",
                    "record_identifier_value": f"row-{index}",
                    "failure_class": "expectation_failed",
                },
                detectedAt="2026-04-06T12:00:00+00:00",
            )
            for index in range(1, 5)
        ]
    )

    session = await service.create_session(
        {
            "dataObjectVersionId": "dov-1",
            "executionRunId": "run-1",
            "ruleId": "rule-1",
            "reasonCodes": ["type_mismatch"],
            "failureClass": "expectation_failed",
            "recordIdentifierType": "primary_key",
            "sliceLimit": 1,
        }
    )

    suggestion = session["currentSlice"]["nextSliceSuggestion"]
    assert suggestion["partitionStrategy"] == ["hash_stripe"]
    assert suggestion["hashStripeCount"] == 8
    assert isinstance(suggestion["hashStripe"], int)
    assert 0 <= suggestion["hashStripe"] < suggestion["hashStripeCount"]


class _FakeS3Client:
    def __init__(self) -> None:
        self.head_calls: list[dict[str, object]] = []
        self.create_calls: list[dict[str, object]] = []
        self.put_calls: list[dict[str, object]] = []

    def head_bucket(self, **kwargs):
        self.head_calls.append(kwargs)
        error = RuntimeError("NoSuchBucket")
        error.response = {"Error": {"Code": "NoSuchBucket"}}
        raise error

    def create_bucket(self, **kwargs):
        self.create_calls.append(kwargs)

    def put_object(self, **kwargs):
        self.put_calls.append(kwargs)


@pytest.mark.anyio
async def test_analysis_slice_storage_backend_persists_pack_and_manifest() -> None:
    fake_client = _FakeS3Client()
    backend = S3ExceptionAnalysisSliceStorageBackend(
        bucket="dq-gx-exceptions",
        prefix="gx-analysis-slices",
        endpoint="http://aistor:9000",
        access_key="access-key",
        secret_key="secret-key",
        ssl_enabled=False,
        client_factory=lambda: fake_client,
    )

    artifact_locations = await backend.persist_analysis_pack(
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
            "nextSliceSuggestion": {"reasonCodes": ["type_mismatch"], "partitionStrategy": ["reason_code"]},
            "records": [{"id": "vio-1"}],
            "createdAt": "2026-04-06T12:00:00+00:00",
            "updatedAt": "2026-04-06T12:00:00+00:00",
        },
        analysis_session_id="session-1",
        analysis_slice_id="slice-1",
        data_object_version_id="dov-1",
        execution_run_id="run-1",
        rule_id="rule-1",
    )

    assert "analysis-pack-" in artifact_locations["analysisPackUri"]
    assert "analysis-manifest-" in artifact_locations["analysisManifestUri"]
    assert len(fake_client.put_calls) == 2

    pack_payload = json.loads(gzip.decompress(fake_client.put_calls[0]["Body"]).decode("utf-8"))
    manifest_payload = json.loads(gzip.decompress(fake_client.put_calls[1]["Body"]).decode("utf-8"))
    assert pack_payload["records"] == [{"id": "vio-1"}]
    assert "records" not in manifest_payload
    assert manifest_payload["analysisPackUri"] == artifact_locations["analysisPackUri"]
    assert manifest_payload["analysisPackSha256"] == artifact_locations["analysisPackSha256"]

