from __future__ import annotations

import pytest

from app.application.services.rule_dsl_sodacl_lowerer import SodaclExpectationBuildError
from app.application.services.rule_dsl_sodacl_lowerer import build_sodacl_artifact_envelope_from_rule_dsl_v2
from app.application.services.rule_dsl_sodacl_lowerer import build_sodacl_scan_payload_from_rule_dsl_v2
from app.domain.entities import build_validation_run_plan_entity
from app.domain.entities.rule_dsl_ir import RuleDslIrDatasetScope
from app.domain.entities.rule_dsl_ir import RuleDslIrDocument
from app.domain.entities.rule_dsl_ir import RuleDslIrEvidence
from app.domain.entities.rule_dsl_ir import RuleDslIrFailedRowsPolicy
from app.domain.entities.rule_dsl_ir import RuleDslIrMetricMeasure
from app.domain.entities.rule_dsl_ir import RuleDslIrOperations
from app.domain.entities.rule_dsl_ir import RuleDslIrRule
from app.domain.entities.rule_dsl_ir import RuleDslIrScope
from app.domain.entities.rule_dsl_ir import RuleDslIrThresholdExpectation


@pytest.fixture
def simple_row_count_rule_ir() -> RuleDslIrDocument:
    return RuleDslIrDocument(
        rule=RuleDslIrRule(
            kind="metric_threshold",
            scope=RuleDslIrScope(
                dataset=RuleDslIrDatasetScope(
                    data_object_id="do_orders",
                    data_object_version_id="dov_orders_v1",
                    dataset_id="ds_orders",
                )
            ),
            measure=RuleDslIrMetricMeasure(metric="row_count"),
            expectation=RuleDslIrThresholdExpectation(operator="gt", value=0, unit="count"),
            evidence=RuleDslIrEvidence(
                failed_rows=RuleDslIrFailedRowsPolicy(
                    mode="none",
                    include_row_identifier=False,
                    include_primary_key=False,
                ),
                emit_compiled_artifact=True,
                emit_generated_sql=False,
            ),
            operations=RuleDslIrOperations(
                severity="critical",
                preferred_engines=["sodacl"],
                fail_if_not_native=True,
            ),
        )
    )


@pytest.fixture
def simple_sodacl_artifact(simple_row_count_rule_ir: RuleDslIrDocument):
    return build_sodacl_artifact_envelope_from_rule_dsl_v2(
        semantic_ir=simple_row_count_rule_ir,
        validation_artifact_id="soda-plan-1",
        validation_artifact_version=1,
        assignment_scope={
            "dataObjectId": "do_orders",
            "datasetId": "ds_orders",
        },
        resolved_data_object_version_ids=["dov_orders_v1"],
        rule_id="rule-1",
    )


def test_build_sodacl_scan_payload_from_simple_metric_rule(simple_row_count_rule_ir: RuleDslIrDocument) -> None:
    payload = build_sodacl_scan_payload_from_rule_dsl_v2(
        semantic_ir=simple_row_count_rule_ir,
        rule_id="rule-1",
    )

    assert payload["scanName"] == "rule-1"
    assert payload["ruleKind"] == "metric_threshold"
    assert payload["checks"][0]["metric"] == "row_count"
    assert payload["checks"][0]["text"] == "row_count > 0"


def test_build_sodacl_artifact_envelope_from_simple_rule(simple_sodacl_artifact) -> None:
    assert simple_sodacl_artifact.validationArtifactId == "soda-plan-1"
    assert simple_sodacl_artifact.engineType == "soda"
    assert simple_sodacl_artifact.engineArtifact.engineType == "soda"
    assert simple_sodacl_artifact.engineArtifact.artifactKind == "soda_scan"
    assert simple_sodacl_artifact.engineArtifact.payload["checks"][0]["text"] == "row_count > 0"
    assert simple_sodacl_artifact.runPlanning.engineTarget == "soda"
    assert simple_sodacl_artifact.runPlanning.traceability is not None
    assert simple_sodacl_artifact.runPlanning.traceability.validationArtifactId == "soda-plan-1"


def test_validation_run_plan_can_reference_sodacl_artifact(simple_sodacl_artifact) -> None:
    plan = build_validation_run_plan_entity(
        {
            "runPlanId": "run-plan-soda-1",
            "businessKey": "run-plan-soda-1",
            "workspaceId": "retail-banking",
            "scopeSelector": {
                "workspaceId": "retail-banking",
                "assignmentScope": {
                    "dataObjectId": "do_orders",
                    "datasetId": "ds_orders",
                },
            },
            "planningMode": "single_suite",
            "status": "draft",
            "createdBy": "user-admin",
            "createdAt": "2026-04-10T08:00:00Z",
            "updatedAt": "2026-04-10T08:00:00Z",
            "versions": [
                {
                    "runPlanVersionId": "run-plan-soda-1-v1",
                    "runPlanId": "run-plan-soda-1",
                    "governanceState": "draft",
                    "validationArtifactSelection": {
                        "selectionMode": "explicit_refs",
                        "artifactRefs": [
                            {
                                "artifactId": simple_sodacl_artifact.validationArtifactId,
                                "artifactVersion": simple_sodacl_artifact.validationArtifactVersion,
                                "engineType": "soda",
                            }
                        ],
                    },
                    "artifactId": simple_sodacl_artifact.validationArtifactId,
                    "artifactVersion": simple_sodacl_artifact.validationArtifactVersion,
                    "artifactSnapshot": simple_sodacl_artifact.model_dump(mode="python", by_alias=False, exclude_none=True),
                    "scheduleDefinition": {"scheduledAt": "2026-04-10T09:00:00Z"},
                    "createdAt": "2026-04-10T08:05:00Z",
                }
            ],
            "transitionEvents": [],
        }
    )

    assert plan.versions[0].artifactSnapshot["engineType"] == "soda"
    assert plan.versions[0].artifactSnapshot["engineArtifact"]["artifactKind"] == "soda_scan"
    assert plan.versions[0].artifactSnapshot["engineArtifact"]["payload"]["checks"][0]["text"] == "row_count > 0"
    assert plan.versions[0].validationArtifactSelection["artifactRefs"][0]["engineType"] == "soda"


def test_build_sodacl_scan_payload_rejects_row_filter(simple_row_count_rule_ir: RuleDslIrDocument) -> None:
    simple_row_count_rule_ir.rule.scope.row_filter = {
        "kind": "row_predicate",
        "language": "dq_predicate",
        "expression": "status = 'ACTIVE'",
    }

    with pytest.raises(SodaclExpectationBuildError, match="row_filter"):
        build_sodacl_scan_payload_from_rule_dsl_v2(
            semantic_ir=simple_row_count_rule_ir,
            rule_id="rule-1",
        )
