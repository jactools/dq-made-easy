import pytest

from app.infrastructure.repositories.in_memory_validation_artifact_repository import InMemoryValidationArtifactRepository


pytestmark = pytest.mark.usefixtures("monkeypatch")


def _artifact(*, artifact_id: str = "va-1", artifact_version: int = 1, marker: str = "a") -> dict:
    return {
        "validation_artifact_id": artifact_id,
        "validation_artifact_version": artifact_version,
        "artifact_contract_version": "v1",
        "engine_type": "gx",
        "assignment_scope": {"data_object_id": "obj-1", "dataset_id": "ds-1", "data_product_id": "odcs.demo.dp"},
        "resolved_execution_scope": {"data_object_version_ids": ["dov-1"]},
        "compiled_from": {"rule_ids": ["r-1"], "compiler_version": "v1", "generated_at": "2026-01-01T00:00:00Z"},
        "execution_hints": {"recommended_engine_target": "pyspark", "primary_key_fields": []},
        "run_planning": {
            "engine_target": "pyspark",
            "execution_shape": "single_object",
            "grouping_key": "data_object_version_id",
            "traceability": {
                "rule_id": "r-1",
                "rule_version_id": "rv-1",
                "validation_artifact_id": artifact_id,
                "validation_artifact_version": artifact_version,
            },
        },
        "engine_artifact": {
            "engine_type": "gx",
            "artifact_kind": "gx_expectation_suite",
            "artifact_schema_version": "gx-artifact-envelope/v1",
            "payload": {
                "suiteId": artifact_id,
                "suiteVersion": artifact_version,
                "artifactVersion": "v1",
                "assignmentScope": {"dataObjectId": "obj-1", "datasetId": "ds-1", "dataProductId": "odcs.demo.dp"},
                "resolvedExecutionScope": {"dataObjectVersionIds": ["dov-1"]},
                "gxSuite": {"expectation_suite_name": f"{artifact_id}_v{artifact_version}", "expectations": [], "meta": {"marker": marker}},
                "compiledFrom": {"ruleIds": ["r-1"], "compilerVersion": "v1", "generatedAt": "2026-01-01T00:00:00Z"},
                "executionHints": {"recommendedEngine": "pyspark", "primaryKeyFields": []},
            },
        },
    }


@pytest.mark.anyio
async def test_save_artifact_creates_updates_and_tracks_history() -> None:
    repository = InMemoryValidationArtifactRepository()

    created = await repository.save_artifact(
        envelope=_artifact(marker="initial"),
        status="active",
        saved_by="user-a",
        source_pipeline="rule-compiler",
    )

    assert created.validationArtifactId == "va-1"
    assert created.status == "active"
    assert created.savedBy == "user-a"
    assert created.sourcePipeline == "rule-compiler"
    assert isinstance(created.artifactHash, str)

    updated = await repository.save_artifact(
        envelope=_artifact(marker="updated"),
        status="disabled",
        expected_existing_hash=created.artifactHash,
        saved_by="user-b",
    )

    assert updated.status == "disabled"
    history = await repository.list_artifact_status_history(artifact_id="va-1")
    assert len(history) == 2
    assert history[1].fromStatus == "active"
    assert history[1].toStatus == "disabled"
    assert history[1].changedBy == "user-b"


@pytest.mark.anyio
async def test_list_and_fetch_artifacts_honor_filters_and_latest_only() -> None:
    repository = InMemoryValidationArtifactRepository()

    await repository.save_artifact(envelope=_artifact(artifact_id="va-1", artifact_version=1), status="active")
    await repository.save_artifact(envelope=_artifact(artifact_id="va-1", artifact_version=2), status="active")
    await repository.save_artifact(
        envelope={
            **_artifact(artifact_id="va-2", artifact_version=1),
            "resolved_execution_scope": {"data_object_version_ids": ["dov-2"]},
            "compiled_from": {"rule_ids": ["r-2"], "compiler_version": "v1", "generated_at": "2026-01-01T00:00:00Z"},
        },
        status="active",
    )

    latest = await repository.list_artifacts(data_object_version_id="dov-1")
    all_versions = await repository.list_artifacts(data_object_version_id="dov-1", latest_only=False)
    by_rule = await repository.list_artifacts_for_rule(rule_id="r-2")
    fetched = await repository.get_artifact_by_id(artifact_id="va-1")

    assert len(latest) == 1
    assert latest[0].validationArtifactVersion == 2
    assert len(all_versions) == 2
    assert len(by_rule) == 1
    assert by_rule[0].validationArtifactId == "va-2"
    assert fetched is not None
    assert fetched.validationArtifactVersion == 2