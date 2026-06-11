import pytest

from app.api.v1.schemas.gx_artifact_view import (
    GxArtifactEnvelopeView,
    GxArtifactAssignmentScopeView,
    GxArtifactExecutionContractView,
    GxArtifactExecutionTraceabilityView,
    GxArtifactLandingZoneMaterializationView,
    GxArtifactResolvedExecutionScopeView,
    GxArtifactSourceTargetView,
    GxArtifactCompiledFromView,
    GxArtifactExecutionHintsView,
    GxSuiteRetrievalQueryView,
)


def test_gx_artifact_envelope_aliasing():
    envelope = GxArtifactEnvelopeView(
        suiteId="gx_1",
        suiteVersion=1,
        artifactVersion="v1",
        assignmentScope=GxArtifactAssignmentScopeView(datasetId="ds_1"),
        resolvedExecutionScope=GxArtifactResolvedExecutionScopeView(dataObjectVersionIds=["dov_1"]),
        gxSuite={},
        compiledFrom=GxArtifactCompiledFromView(ruleIds=["r1"], compilerVersion="c1", generatedAt="2026-04-05T00:00:00Z"),
        executionHints=GxArtifactExecutionHintsView(recommendedEngine="pyspark", primaryKeyFields=["id"]),
        executionContract=GxArtifactExecutionContractView(
            engineTarget="pyspark",
            executionShape="join_pair",
            traceability=GxArtifactExecutionTraceabilityView(
                ruleId="r1",
                ruleVersionId="rv1",
                gxSuiteId="gx_1",
                gxSuiteVersion=1,
                dataObjectVersionId="dov_1",
            ),
            sourceMaterialization=GxArtifactLandingZoneMaterializationView(
                landingZoneArtifactId="lz_1",
                landingZoneVersionId="lzv_1",
                outputLocation="s3://dq-landing-zone/joined/lz_1",
                joinType="inner",
                joinKeys=["customer_id"],
                leftSource=GxArtifactSourceTargetView(
                    dataObjectId="do_left",
                    dataObjectVersionId="dov_left",
                    datasetId="ds_left",
                    dataProductId="odcs.dp.left-001",
                ),
                rightSource=GxArtifactSourceTargetView(
                    dataObjectId="do_right",
                    dataObjectVersionId="dov_right",
                    datasetId="ds_right",
                    dataProductId="odcs.dp.right-001",
                ),
            ),
        ),
    )
    out = envelope.model_dump(by_alias=True)
    assert "suite_id" in out
    assert "assignment_scope" in out
    assert "dataset_id" in out["assignment_scope"]
    assert "execution_contract" in out
    assert out["execution_contract"]["traceability"]["gx_suite_id"] == "gx_1"


def test_gx_retrieval_query_validation():
    with pytest.raises(ValueError):
        GxSuiteRetrievalQueryView(dataObjectId="a", datasetId="b")
