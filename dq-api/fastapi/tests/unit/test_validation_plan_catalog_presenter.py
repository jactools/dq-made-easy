from __future__ import annotations

from app.api.presenters.validation_plan_catalog import build_validation_plan_catalog_view


def test_build_validation_plan_catalog_view_extracts_engine_types_from_all_supported_sources() -> None:
    class _VersionEngineType:
        runPlanVersionId = "v1"
        governanceState = "active"
        artifactId = "suite-1"
        artifactVersion = 1
        artifactSnapshot = {"engineType": "gx"}
        gxSuiteSelection = {"scopeSelector": {"tagIds": ["gold", "gold", "pii"]}}
        validationArtifactSelection = {"artifactRefs": []}
        scheduleDefinition = {"scheduledAt": "2026-04-12T08:00:00Z"}
        createdAt = "2026-04-10T08:00:00Z"

    class _VersionEngineArtifact:
        runPlanVersionId = "v2"
        governanceState = "active"
        artifactId = "suite-2"
        artifactVersion = 2
        artifactSnapshot = {"engineArtifact": {"engineType": "soda"}}
        validationArtifactSelection = {"artifactRefs": []}
        scheduleDefinition = {"scheduledAt": "2026-04-12T09:00:00Z"}
        createdAt = "2026-04-10T09:00:00Z"

    class _VersionArtifactRefs:
        runPlanVersionId = "v3"
        governanceState = "draft"
        artifactId = None
        artifactVersion = None
        artifactSnapshot = {}
        validationArtifactSelection = {"artifactRefs": [{"engineType": "gx"}]}
        scheduleDefinition = {"scheduledAt": "2026-04-12T10:00:00Z"}
        createdAt = "2026-04-10T10:00:00Z"

    class _VersionNone:
        runPlanVersionId = "v4"
        governanceState = "draft"
        artifactId = None
        artifactVersion = None
        artifactSnapshot = {}
        validationArtifactSelection = {"artifactRefs": []}
        scheduleDefinition = {"scheduledAt": "2026-04-12T11:00:00Z"}
        createdAt = "2026-04-10T11:00:00Z"

    class _Plan:
        runPlanId = "run-plan-1"
        businessKey = "run-plan-1"
        workspaceId = "retail-banking"
        scopeSelector = {"workspaceId": "retail-banking", "tagIds": ["gold", "regulatory"]}
        planningMode = "single_suite"
        status = "active"
        createdAt = "2026-04-10T07:00:00Z"
        updatedAt = "2026-04-10T08:00:00Z"
        versions = [_VersionEngineType(), _VersionEngineArtifact(), _VersionArtifactRefs(), _VersionNone()]

    result = build_validation_plan_catalog_view([_Plan()])

    assert [suite.engineType for suite in result.validationSuites] == ["gx", "soda", "gx", None]
    assert result.validationSuites[0].tagIds == ["gold", "pii"]
    assert result.validationSummary.runPlanCount == 1
    assert result.validationSummary.suiteCount == 4
    assert result.validationSummary.engineTypes == ["gx", "soda"]
