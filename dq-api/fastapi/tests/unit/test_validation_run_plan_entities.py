from app.domain.entities import GxRunPlanEntity
from app.domain.entities import GxRunPlanScopeSelectorEntity
from app.domain.entities import ValidationRunPlanArtifactSelectionEntity
from app.domain.entities import ValidationRunPlanArtifactRefEntity
from app.domain.entities import ValidationRunPlanEntity
from app.domain.entities import build_gx_run_plan_entity_from_validation_run_plan
from app.domain.entities import build_validation_run_plan_entity_from_gx_run_plan


def test_build_validation_run_plan_from_gx_run_plan_projects_suite_fields() -> None:
    gx_plan = GxRunPlanEntity(
        runPlanId="rp-1",
        businessKey="rp-1",
        workspaceId="ws-1",
        scopeSelector=GxRunPlanScopeSelectorEntity(dataObjectId="do-1"),
        planningMode="manual",
        status="draft",
        createdAt="2026-04-26T10:30:00Z",
        updatedAt="2026-04-26T10:30:00Z",
        versions=[
            {
                "runPlanVersionId": "v-1",
                "runPlanId": "rp-1",
                "governanceState": "draft",
                "gxSuiteSelection": {
                    "selectionMode": "explicit_refs",
                    "suiteRefs": [{"suiteId": "gx_suite_1", "suiteVersion": 2}],
                },
                "suiteId": "gx_suite_1",
                "suiteVersion": 2,
                "suiteSnapshot": {
                    "suiteId": "gx_suite_1",
                    "suiteVersion": 2,
                    "artifactVersion": "v1",
                    "assignmentScope": {"dataObjectId": "do-1"},
                    "resolvedExecutionScope": {"dataObjectVersionIds": ["dov-1"]},
                    "gxSuite": {"expectation_suite_name": "dq_suite", "expectations": [], "meta": {}},
                    "compiledFrom": {"ruleIds": ["r-1"], "compilerVersion": "v1", "generatedAt": "2026-04-26T10:30:00Z"},
                    "executionHints": {"recommendedEngine": "pyspark", "primaryKeyFields": []},
                },
                "scheduleDefinition": {},
                "createdAt": "2026-04-26T10:30:00Z",
            }
        ],
    )

    validation_plan = build_validation_run_plan_entity_from_gx_run_plan(gx_plan)

    assert validation_plan.versions[0].artifactId == "gx_suite_1"
    assert validation_plan.versions[0].artifactVersion == 2
    assert validation_plan.versions[0].validationArtifactSelection["artifactRefs"][0]["artifactId"] == "gx_suite_1"
    assert validation_plan.versions[0].artifactSnapshot is not None
    assert validation_plan.versions[0].artifactSnapshot["validationArtifactId"] == "gx_suite_1"


def test_build_gx_run_plan_from_validation_run_plan_projects_artifact_fields() -> None:
    validation_plan = ValidationRunPlanEntity(
        runPlanId="rp-2",
        businessKey="rp-2",
        workspaceId="ws-2",
        planningMode="manual",
        status="draft",
        createdAt="2026-04-26T10:30:00Z",
        updatedAt="2026-04-26T10:30:00Z",
        versions=[
            {
                "runPlanVersionId": "v-2",
                "runPlanId": "rp-2",
                "governanceState": "draft",
                "validationArtifactSelection": ValidationRunPlanArtifactSelectionEntity(
                    selectionMode="explicit_refs",
                    artifactRefs=[ValidationRunPlanArtifactRefEntity(artifactId="gx_suite_2", artifactVersion=3)],
                ).model_dump(mode="python", by_alias=False, exclude_none=True),
                "artifactId": "gx_suite_2",
                "artifactVersion": 3,
                "artifactSnapshot": {
                    "validationArtifactId": "gx_suite_2",
                    "validationArtifactVersion": 3,
                    "artifactContractVersion": "v1",
                    "engineType": "gx",
                    "assignmentScope": {"dataObjectId": "do-2"},
                    "resolvedExecutionScope": {"dataObjectVersionIds": ["dov-2"]},
                    "compiledFrom": {"ruleIds": ["r-2"], "compilerVersion": "v1", "generatedAt": "2026-04-26T10:30:00Z"},
                    "executionHints": {"recommendedEngineTarget": "pyspark", "primaryKeyFields": []},
                    "runPlanning": {
                        "engineTarget": "pyspark",
                        "executionShape": "single_object",
                        "groupingKey": "data_object_version_id",
                        "traceability": {
                            "ruleId": "r-2",
                            "ruleVersionId": "rv-2",
                            "validationArtifactId": "gx_suite_2",
                            "validationArtifactVersion": 3,
                        },
                    },
                    "engineArtifact": {
                        "engineType": "gx",
                        "artifactKind": "gx_expectation_suite",
                        "artifactSchemaVersion": "gx-artifact-envelope/v1",
                        "payload": {
                            "suiteId": "gx_suite_2",
                            "suiteVersion": 3,
                            "artifactVersion": "v1",
                            "assignmentScope": {"dataObjectId": "do-2"},
                            "resolvedExecutionScope": {"dataObjectVersionIds": ["dov-2"]},
                            "gxSuite": {"expectation_suite_name": "dq_suite", "expectations": [], "meta": {}},
                            "compiledFrom": {"ruleIds": ["r-2"], "compilerVersion": "v1", "generatedAt": "2026-04-26T10:30:00Z"},
                            "executionHints": {"recommendedEngine": "pyspark", "primaryKeyFields": []},
                        },
                    },
                },
                "scheduleDefinition": {},
                "createdAt": "2026-04-26T10:30:00Z",
            }
        ],
    )

    gx_plan = build_gx_run_plan_entity_from_validation_run_plan(validation_plan)

    assert gx_plan.versions[0].suiteId == "gx_suite_2"
    assert gx_plan.versions[0].suiteVersion == 3
    assert gx_plan.versions[0].gxSuiteSelection["suiteRefs"][0]["suiteId"] == "gx_suite_2"
    assert gx_plan.versions[0].suiteSnapshot is not None
    assert gx_plan.versions[0].suiteSnapshot["suiteId"] == "gx_suite_2"