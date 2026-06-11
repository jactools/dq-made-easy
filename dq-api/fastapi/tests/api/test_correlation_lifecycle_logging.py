from __future__ import annotations

import pytest
from fastapi import Response

from app.api.v1.endpoints import execution_monitoring as gx_endpoints
from app.core.request_context import set_correlation_id
from app.domain.entities import build_validation_artifact_envelope_from_gx_artifact


class _Repo:
    def __init__(self) -> None:
        self.item = {
            "suiteId": "gx_suite_corr",
            "suiteVersion": 1,
            "artifactVersion": "v1",
            "assignmentScope": {
                "dataObjectId": "do_corr",
                "datasetId": None,
                "dataProductId": None,
            },
            "resolvedExecutionScope": {
                "dataObjectVersionIds": ["dov_corr_1"],
            },
            "gxSuite": {
                "expectation_suite_name": "dq_corr_suite",
                "expectations": [],
                "meta": {},
            },
            "compiledFrom": {
                "ruleIds": ["rule_corr_1"],
                "compilerVersion": "dq-compiler-7.3",
                "generatedAt": "2026-03-22T10:30:00Z",
            },
            "executionHints": {
                "recommendedEngine": "pyspark",
                "primaryKeyFields": ["order_id"],
            },
        }

    async def save_artifact(self, **kwargs):
        envelope = kwargs["envelope"]
        return envelope.model_dump(mode="python", by_alias=False, exclude_none=False) if hasattr(envelope, "model_dump") else dict(envelope)

    async def patch_artifact_status(self, **kwargs):
        updated = dict(self.item)
        updated["status"] = kwargs["new_status"]
        return build_validation_artifact_envelope_from_gx_artifact(updated)


@pytest.mark.anyio
async def test_same_correlation_id_in_multi_step_gx_lifecycle(caplog) -> None:
    repo = _Repo()
    body = gx_endpoints.GxArtifactEnvelopeView.model_validate(repo.item)
    set_correlation_id("cid-lifecycle-001")

    caplog.set_level("INFO")

    await gx_endpoints.save_gx_suite(
        body=body,
        status="active",
        response=Response(),
        repository=repo,
    )
    await gx_endpoints.patch_gx_suite_status(
        suite_id="gx_suite_corr",
        status="deprecated",
        suite_version=1,
        reason="superseded",
        repository=repo,
    )

    lifecycle_events = [
        record
        for record in caplog.records
        if str(record.__dict__.get("event", "")).startswith("gx.suite.")
    ]
    assert lifecycle_events, "Expected gx lifecycle events in logs"
    assert all(record.__dict__.get("correlationId") == "cid-lifecycle-001" for record in lifecycle_events)
