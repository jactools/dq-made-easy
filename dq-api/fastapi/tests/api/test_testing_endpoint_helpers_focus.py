from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.api.presenters import testing as testing_presenters
from app.api.v1 import testing_data_requests_api as testing_data_requests
from app.api.v1 import testing_route_support as testing_helpers
from app.api.v1.endpoints import testing as testing_ep
from app.domain.entities import rule_testing_context as testing_context


pytestmark = pytest.mark.usefixtures("monkeypatch")


class _Trace:
    def __init__(self, **kwargs):
        self.ruleVersionNumber = kwargs.get("ruleVersionNumber")
        self.ruleVersionId = kwargs.get("ruleVersionId")
        self.artifactKey = kwargs.get("artifactKey")
        self.compilerVersion = kwargs.get("compilerVersion")

    def model_dump(self):
        return {
            "ruleVersionNumber": self.ruleVersionNumber,
            "ruleVersionId": self.ruleVersionId,
            "artifactKey": self.artifactKey,
            "compilerVersion": self.compilerVersion,
        }


def test_extract_selected_attributes_and_failure_analysis() -> None:
    attrs = testing_presenters.extract_test_selected_attributes(
        {
            "selectedAttributes": [
                {"name": "email"},
                {"id": "status"},
                "country",
                "",
            ]
        }
    )
    assert attrs == ["email", "status", "country"]

    reasons = testing_presenters.build_test_failure_analysis(
        {
            "failureReasons": ["invalid email"],
            "diagnostics": [{"message": "invalid email"}, {"message": "status mismatch"}],
        },
        failures_found=3,
    )
    assert reasons == ["invalid email", "status mismatch"]

    fallback = testing_presenters.build_test_failure_analysis(
        {
            "results": [
                {"passed": False, "data": {"email": None, "status": ""}},
                {"passed": False, "data": {"email": None, "status": "ok"}},
            ]
        },
        failures_found=2,
    )
    assert any("Likely cause" in item for item in fallback)


def test_paginate_scheduler_payload_and_markdown_pdf_helpers() -> None:
    page = testing_helpers._paginate([{"id": i} for i in range(5)], page=2, limit=2)
    assert [row["id"] for row in page["data"]] == [2, 3]
    assert page["pagination"]["total_pages"] == 3

    payload = testing_helpers._build_scheduler_handoff_payload(
        request_id="req-1",
        execution_context={"executionContract": {"engineTarget": "dq-engine"}, "handoffReady": True},
        correlation_id="corr-1",
    )
    assert payload["batchRequestId"] == "req-1"
    assert payload["executorTarget"] == "dq-engine"
    assert payload["handoffReady"] is True

    md = "# Report\n\n- Line"
    pdf = testing_helpers._markdown_to_pdf_bytes(md)
    assert isinstance(pdf, bytes)
    assert len(pdf) > 10


def test_resolve_version_generation_payload_and_mock_preview_attributes() -> None:
    class _CatalogRepo:
        def list_data_object_versions(self):
            return [SimpleNamespace(id="dov-23", version=3, data_object_id="do-9")]

        def list_attributes_catalog(self, version_id: str | None = None):
            assert version_id == "dov-23"
            return [
                SimpleNamespace(name="email", type="text", nullable=True, format="", is_primary_key=False),
                SimpleNamespace(name="status", type="text", nullable=True, format="", is_primary_key=False),
            ]

        def list_data_objects_catalog(self):
            return [SimpleNamespace(id="do-9", name="Data Object 9")]

    payload = testing_helpers._resolve_version_generation_payload("dov-23", 4, _CatalogRepo())
    assert payload["target_type"] == "data_object_version"
    assert payload["version_name"] == 3
    assert payload["data_object_id"] == "do-9"
    assert [attribute["name"] for attribute in payload["attributes"]] == ["email", "status"]

    mock_attributes = testing_helpers._build_mock_preview_attributes()
    assert [attribute["name"] for attribute in mock_attributes] == ["column_id", "column_x", "column_y"]


def test_render_version_diff_and_markdown_report() -> None:
    latest = SimpleNamespace(
        id="proof-2",
        status="failed",
        testDate="2026-03-27T10:00:00Z",
        recordsTestedCount=10,
        failuresFound=2,
        coverage=0.8,
        proofData={
            "selectedAttributes": [{"name": "email"}],
            "passed_count": 8,
            "results": [{"passed": False, "data": {"email": None}}],
        },
        executionTrace=_Trace(ruleVersionNumber=2, ruleVersionId="rv-2", artifactKey="k2", compilerVersion="dq-7.3.0"),
    )
    previous = SimpleNamespace(
        id="proof-1",
        status="passed",
        testDate="2026-03-26T10:00:00Z",
        recordsTestedCount=10,
        failuresFound=0,
        coverage=0.9,
        proofData={},
        executionTrace=_Trace(ruleVersionNumber=1, ruleVersionId="rv-1", artifactKey="k1", compilerVersion="dq-7.2.0"),
    )

    diff_text = testing_presenters.render_test_proof_version_diff_section(
        {
            "changes": {
                "details": [
                    {"field": "expression", "oldValue": "a", "newValue": "b"},
                ]
            }
        },
        latest,
        previous,
    )
    assert "Version changed from V1 to V2" in diff_text
    assert "expression" in diff_text

    report = testing_presenters.build_test_markdown_report(
        rule_id="rule-1",
        proof=latest,
        rule_name="Email Rule",
        dimension="validity",
        compiled_expression="email contains '@'",
        version_diff_section=diff_text,
    )
    assert "# Rule Test Report" in report
    assert "What Went Good" in report
    assert "Executed Rule Expression" in report


def test_resolve_current_rule_version_and_build_execution_context() -> None:
    class _Repo:
        async def list_rule_versions(self, _rule_id: str, limit: int = 1, offset: int = 0):
            return {
                "versions": [
                    {"id": "rv-2", "isCurrentVersion": True, "versionNumber": 2},
                    {"id": "rv-1", "isCurrentVersion": False, "versionNumber": 1},
                ]
            }

        async def get_rule_version(self, _rule_id: str, rule_version_id: str):
            return {
                "id": rule_version_id,
                "expression": "email contains '@'",
            }

        async def get_active_compiler_artifact(self, _rule_version_id: str):
            return {
                "artifactKey": "artifact-2",
                "compilerVersion": "dq-7.3.0",
                "compilerRevision": 3,
                "compileStatus": "compiled",
                "artifactPayload": {
                    "schemaVersion": "1",
                    "filter": {"normalized": "email contains '@'"},
                    "executionContract": {"engineTarget": "dq-engine"},
                },
            }

    repo = _Repo()
    version = asyncio.run(testing_context.resolve_current_rule_version(repo, "rule-1"))
    assert version is not None
    assert version.id == "rv-2"
    assert version.versionNumber == 2
    assert version.isCurrentVersion is True

    context = asyncio.run(testing_context.build_execution_context(repo, "rule-1"))
    assert context is not None
    assert context.ruleId == "rule-1"
    assert context.ruleVersionId == "rv-2"
    assert context.compilerVersion == "dq-7.3.0"
    assert context.sourceRuleExpression == "email contains '@'"
    assert context.executedExpression == "email contains '@'"
    assert context.handoffReady is True
    assert context.compiledExpression == "email contains '@'"


def test_build_execution_context_raises_when_active_compiler_artifact_missing() -> None:
    class _Repo:
        async def list_rule_versions(self, _rule_id: str, limit: int = 1, offset: int = 0):
            return {
                "versions": [
                    {"id": "rv-2", "isCurrentVersion": True, "versionNumber": 2},
                ]
            }

        async def get_rule_version(self, _rule_id: str, rule_version_id: str):
            return {
                "id": rule_version_id,
                "expression": "email contains '@'",
            }

        async def get_active_compiler_artifact(self, _rule_version_id: str):
            return None

    with pytest.raises(HTTPException) as error:
        asyncio.run(testing_context.build_execution_context(_Repo(), "rule-1"))

    assert error.value.status_code == 409
    assert error.value.detail["error"] == "active_compiler_artifact_required"


def _proof_payload(*, proof_id: str, version_id: str | None, version_number: int | None, status: str = "passed") -> dict:
    return {
        "id": proof_id,
        "ruleId": "rule-1",
        "testDate": "2026-03-28T10:00:00Z",
        "coverage": 0.9,
        "status": status,
        "recordsTestedCount": 10,
        "failuresFound": 0 if status == "passed" else 2,
        "proofData": {"selectedAttributes": [{"name": "email"}], "passedCount": 8},
        "executionTrace": {
            "executionId": f"exec-{proof_id}",
            "correlationId": f"corr-{proof_id}",
            "resultStatus": status,
            "artifactKey": f"artifact-{proof_id}",
            "ruleVersionId": version_id,
            "ruleVersionNumber": version_number,
            "compilerVersion": "dq-7.3.0",
        },
    }


async def _read_stream(response) -> bytes:
    chunks: list[bytes] = []
    async for chunk in response.body_iterator:
        chunks.append(chunk if isinstance(chunk, bytes) else chunk.encode("utf-8"))
    return b"".join(chunks)


@pytest.mark.anyio
async def test_export_test_proof_report_raises_when_no_proofs() -> None:
    class _TestingRepo:
        def list_test_proofs(self, _rule_id: str):
            return []

    class _RulesRepo:
        async def get_rule_by_id(self, _rule_id: str):
            return None

    with pytest.raises(testing_ep.HTTPException) as error:
        await testing_ep.export_test_proof_report(
            rule_id="rule-1",
            proof_id=None,
            repository=_TestingRepo(),
            rules_repository=_RulesRepo(),
        )
    assert error.value.status_code == 404


@pytest.mark.anyio
async def test_generate_test_data_for_version_uses_completed_queue_result(monkeypatch) -> None:
    async def _enqueue(**_kwargs):
        return {"request_id": "tdr-queue-1"}

    async def _wait(_request_id: str):
        return {
            "request_id": "tdr-queue-1",
            "job_id": "tdj-queue-1",
            "status": "completed",
            "target_type": "data_object_version",
            "target_id": "dov-23",
            "sample_count": 2,
            "requested_at": "2026-04-05T12:00:00Z",
            "result": {
                "version_id": "dov-23",
                "version_name": 3,
                "data_object_id": "do-9",
                "attribute_count": 1,
                "sample_count": 2,
                "samples": [{"email": "user1@example.com"}, {"email": "user2@example.com"}],
                "attributes": [{"name": "email", "type": "text", "nullable": True, "format": "", "is_primary_key": False}],
                "generated_at": "2026-04-05T12:00:02Z",
            },
        }

    monkeypatch.setattr(testing_data_requests, "bind_queued_test_data_request_enqueuer", lambda _request: _enqueue)
    monkeypatch.setattr(testing_data_requests, "wait_for_test_data_request_result", _wait)

    class _CatalogRepo:
        def list_data_object_versions(self):
            return [SimpleNamespace(id="dov-23", version=3, data_object_id="do-9")]

        def list_attributes_catalog(self, version_id: str | None = None):
            return [SimpleNamespace(name="email", type="text", nullable=True, format="", is_primary_key=False)]

        def list_data_objects_catalog(self):
            return [SimpleNamespace(id="do-9", name="Data Object 9")]

    response = await testing_ep.generate_test_data_for_version(
        request=SimpleNamespace(headers={}),
        version_id="dov-23",
        payload=testing_ep.GenerateTestDataRequest(sampleCount=2),
        catalog_repository=_CatalogRepo(),
    )

    assert response.versionId == "dov-23"
    assert response.sampleCount == 2
    assert len(response.samples) == 2


@pytest.mark.anyio
async def test_test_rule_with_generated_data_uses_queued_samples(monkeypatch) -> None:
    async def _enqueue(**_kwargs):
        return {"request_id": "tdr-queue-2"}

    async def _wait(_request_id: str):
        return {
            "request_id": "tdr-queue-2",
            "job_id": "tdj-queue-2",
            "status": "completed",
            "target_type": "data_object_version",
            "target_id": "dov-23",
            "sample_count": 2,
            "requested_at": "2026-04-05T12:00:00Z",
            "result": {
                "version_id": "dov-23",
                "version_name": 3,
                "data_object_id": "do-9",
                "attribute_count": 1,
                "sample_count": 2,
                "samples": [{"email": "user1@example.com"}, {"email": "user2@example.com"}],
                "attributes": [{"name": "email", "type": "text", "nullable": True, "format": "", "is_primary_key": False}],
                "generated_at": "2026-04-05T12:00:02Z",
            },
        }

    monkeypatch.setattr(testing_data_requests, "bind_queued_test_data_request_enqueuer", lambda _request: _enqueue)
    monkeypatch.setattr(testing_data_requests, "wait_for_test_data_request_result", _wait)

    class _TestingRepo:
        def create_test_proof(self, rule_id, payload, status="pending"):
            return {
                "id": "tp-generated-1",
                "ruleId": rule_id,
                "testDate": "2026-04-05T12:00:01Z",
                "coverage": payload.get("coverage", 0.0),
                "status": status,
                "recordsTestedCount": payload.get("recordsTestedCount", 0),
                "failuresFound": payload.get("failuresFound", 0),
                "proofData": payload.get("proofData", {}),
            }

        def update_test_proof(self, proof_id, payload, status="pending"):
            return {
                "id": proof_id,
                "ruleId": "rule-1",
                "testDate": "2026-04-05T12:00:03Z",
                "coverage": payload.get("coverage", 0.0),
                "status": status,
                "recordsTestedCount": payload.get("recordsTestedCount", 0),
                "failuresFound": payload.get("failuresFound", 0),
                "proofData": payload.get("proofData", {}),
                "executionTrace": payload.get("executionTrace"),
            }

        def run_rule_against_test_data(self, rule_id, test_data, version_id_source=None, compiled_expression=None, semantic_config=None):
            assert rule_id == "rule-1"
            assert version_id_source == "dov-23"
            assert len(test_data) == 2
            payload = {
                "ruleId": "rule-1",
                "expression": "email contains '@'",
                "testDataSource": "dov-23",
                "totalTests": 2,
                "passedCount": 2,
                "failedCount": 0,
                "successRate": 100.0,
                "rulePassed": True,
                "timestamp": "2026-04-05T12:00:03Z",
                "results": [],
                "ruleDetails": {},
                "executionContext": {},
            }
            return SimpleNamespace(totalTests=2, model_dump=lambda: payload)

    class _RulesRepo:
        async def list_rule_versions(self, _rule_id: str, limit: int = 1, offset: int = 0):
            return {"versions": [{"id": "rv-2", "isCurrentVersion": True, "versionNumber": 2}]}

        async def list_rule_records(self, **kwargs):
            del kwargs
            return [{"id": "rule-1", "active": False, "last_approval_status": "draft"}]

        async def get_rule_version(self, _rule_id: str, rule_version_id: str):
            return {
                "id": rule_version_id,
                "expression": "email contains '@'",
            }

        async def get_active_compiler_artifact(self, _rule_version_id: str):
            return {
                "artifactKey": "artifact-2",
                "compilerVersion": "dq-7.3.0",
                "compilerRevision": 3,
                "compileStatus": "compiled",
                "artifactPayload": {
                    "schemaVersion": "1",
                    "filter": {"normalized": "email contains '@'"},
                    "executionContract": {"engineTarget": "dq-engine"},
                },
            }

        async def list_rules(self, **kwargs):
            del kwargs
            return [{"id": "rule-1", "active": False, "last_approval_status": "draft"}]

        async def record_rule_status_transition(self, *args, **kwargs):
            del args, kwargs
            return None

        async def list_rule_status_history(self, *args, **kwargs):
            del args, kwargs
            return []

    class _CatalogRepo:
        def list_data_object_versions(self):
            return [SimpleNamespace(id="dov-23", version=3, data_object_id="do-9")]

        def list_attributes_catalog(self, version_id: str | None = None):
            return [SimpleNamespace(name="email", type="text", nullable=True, format="", is_primary_key=False)]

        def list_data_objects_catalog(self):
            return [SimpleNamespace(id="do-9", name="Data Object 9")]

    response = await testing_ep.test_rule_with_generated_data(
        request=SimpleNamespace(headers={}),
        rule_id="rule-1",
        payload=testing_ep.TestRuleWithGeneratedDataRequest(versionId="dov-23", sampleCount=2),
        repository=_TestingRepo(),
        rules_repository=_RulesRepo(),
        catalog_repository=_CatalogRepo(),
    )

    assert response.ruleId == "rule-1"
    assert response.totalTests == 2
    assert response.executionContext is not None
    assert response.executionContext.ruleVersionId == "rv-2"


@pytest.mark.anyio
async def test_export_test_proof_report_raises_when_proof_id_missing() -> None:
    class _TestingRepo:
        def list_test_proofs(self, _rule_id: str):
            return [_proof_payload(proof_id="p-1", version_id="rv-1", version_number=1)]

    class _RulesRepo:
        async def get_rule_by_id(self, _rule_id: str):
            return None

    with pytest.raises(testing_ep.HTTPException) as error:
        await testing_ep.export_test_proof_report(
            rule_id="rule-1",
            proof_id="missing",
            repository=_TestingRepo(),
            rules_repository=_RulesRepo(),
        )
    assert error.value.status_code == 404


@pytest.mark.anyio
async def test_export_test_proof_report_returns_markdown_and_pdf() -> None:
    class _TestingRepo:
        def list_test_proofs(self, _rule_id: str):
            return [
                _proof_payload(proof_id="p-2", version_id="rv-2", version_number=2, status="failed"),
                _proof_payload(proof_id="p-1", version_id="rv-1", version_number=1, status="passed"),
            ]

    class _RulesRepo:
        async def compare_rule_versions(self, _rule_id: str, _prev: str, _latest: str):
            return {
                "changes": {
                    "details": [
                        {"field": "expression", "oldValue": "a", "newValue": "b"},
                    ]
                }
            }

        async def get_rule_by_id(self, _rule_id: str):
            return SimpleNamespace(name="Rule One", dimension="validity")

        async def get_rule_version(self, _rule_id: str, _version_id: str):
            return {"expression": "email contains '@'"}

    markdown_response = await testing_ep.export_test_proof_report(
        rule_id="rule-1",
        format="markdown",
        proof_id=None,
        repository=_TestingRepo(),
        rules_repository=_RulesRepo(),
    )
    markdown_body = (await _read_stream(markdown_response)).decode("utf-8")
    assert markdown_response.media_type == "text/markdown"
    assert "Version changed from V1 to V2" in markdown_body
    assert "Executed Rule Expression" in markdown_body

    pdf_response = await testing_ep.export_test_proof_report(
        rule_id="rule-1",
        format="pdf",
        proof_id=None,
        repository=_TestingRepo(),
        rules_repository=_RulesRepo(),
    )
    pdf_bytes = await _read_stream(pdf_response)
    assert pdf_response.media_type == "application/pdf"
    assert pdf_bytes.startswith(b"%PDF")


@pytest.mark.anyio
async def test_export_test_proof_report_handles_compare_and_expression_errors() -> None:
    class _TestingRepo:
        def list_test_proofs(self, _rule_id: str):
            return [
                _proof_payload(proof_id="p-2", version_id="rv-2", version_number=2, status="failed"),
                _proof_payload(proof_id="p-1", version_id="rv-1", version_number=1, status="passed"),
            ]

    class _RulesRepo:
        async def compare_rule_versions(self, _rule_id: str, _prev: str, _latest: str):
            raise RuntimeError("diff unavailable")

        async def get_rule_by_id(self, _rule_id: str):
            return None

        async def get_rule_version(self, _rule_id: str, _version_id: str):
            raise RuntimeError("version unavailable")

    response = await testing_ep.export_test_proof_report(
        rule_id="rule-1",
        format="markdown",
        proof_id=None,
        repository=_TestingRepo(),
        rules_repository=_RulesRepo(),
    )
    body = (await _read_stream(response)).decode("utf-8")
    assert "Version changed from V1 to V2" in body
    assert "field-level comparison is not available" in body
