import pytest

from app.infrastructure.repositories.in_memory_gx_suite_repository import InMemoryGxSuiteRepository


pytestmark = pytest.mark.usefixtures("monkeypatch")


def _suite_envelope(*, suite_id: str = "suite-1", suite_version: int = 1, marker: str = "a") -> dict:
    return {
        "suiteId": suite_id,
        "suiteVersion": suite_version,
        "artifactVersion": "v1",
        "assignmentScope": {"dataObjectId": "obj-1", "datasetId": "ds-1", "dataProductId": "odcs.demo.dp"},
        "resolvedExecutionScope": {"dataObjectVersionIds": ["dov-1"]},
        "gxSuite": {
            "expectation_suite_name": f"{suite_id}_v{suite_version}",
            "expectations": [],
            "meta": {"marker": marker},
        },
        "compiledFrom": {"ruleIds": ["r-1"], "compilerVersion": "v1", "generatedAt": "2026-01-01T00:00:00Z"},
        "executionHints": {"recommendedEngine": "pyspark", "primaryKeyFields": []},
        "executionContract": {
            "engineType": "gx",
            "engineTarget": "pyspark",
            "executionShape": "single_object",
            "traceability": {"ruleId": "r-1", "ruleVersionId": "rv-1", "gxSuiteId": suite_id, "gxSuiteVersion": suite_version},
        },
    }


@pytest.mark.anyio
async def test_save_suite_creates_and_updates_with_status_history() -> None:
    repository = InMemoryGxSuiteRepository()

    created = await repository.save_suite(
        envelope=_suite_envelope(marker="initial"),
        status="active",
        saved_by="user-a",
        source_pipeline="rule-compiler",
    )

    assert created.suiteId == "suite-1"
    assert created.suiteVersion == 1
    assert created.status == "active"
    assert created.savedBy == "user-a"
    assert created.sourcePipeline == "rule-compiler"
    assert isinstance(created.artifactHash, str)

    updated = await repository.save_suite(
        envelope=_suite_envelope(marker="updated"),
        status="disabled",
        expected_existing_hash=created.artifactHash,
        saved_by="user-b",
        source_pipeline="manual",
    )

    assert updated.status == "disabled"
    history = await repository.list_suite_status_history(suite_id="suite-1")
    assert len(history) == 2
    assert history[0].fromStatus is None
    assert history[0].toStatus == "active"
    assert history[1].fromStatus == "active"
    assert history[1].toStatus == "disabled"
    assert history[1].changedBy == "user-b"


@pytest.mark.anyio
async def test_save_suite_rejects_conflicting_overwrite() -> None:
    repository = InMemoryGxSuiteRepository()

    created = await repository.save_suite(envelope=_suite_envelope(marker="left"), status="active")

    with pytest.raises(ValueError) as error:
        await repository.save_suite(
            envelope=_suite_envelope(marker="right"),
            status="active",
            expected_existing_hash="stale-hash",
        )

    assert "overwrite conflict" in str(error.value)
    fetched = await repository.get_suite_by_id(suite_id="suite-1", suite_version=1)
    assert fetched is not None
    assert fetched.gxSuite["meta"]["marker"] == "left"
    assert created.artifactHash != "stale-hash"


@pytest.mark.anyio
async def test_get_suite_by_id_uses_specific_or_latest_version() -> None:
    repository = InMemoryGxSuiteRepository()

    await repository.save_suite(envelope=_suite_envelope(suite_version=1, marker="v1"), status="active")
    await repository.save_suite(envelope=_suite_envelope(suite_version=2, marker="v2"), status="active")

    latest = await repository.get_suite_by_id(suite_id="suite-1")
    specific = await repository.get_suite_by_id(suite_id="suite-1", suite_version=1)
    missing = await repository.get_suite_by_id(suite_id="missing")

    assert latest is not None
    assert latest.suiteVersion == 2
    assert latest.gxSuite["meta"]["marker"] == "v2"
    assert specific is not None
    assert specific.suiteVersion == 1
    assert missing is None


@pytest.mark.anyio
async def test_patch_suite_status_targets_latest_or_specific_version_and_filters_history() -> None:
    repository = InMemoryGxSuiteRepository()

    await repository.save_suite(envelope=_suite_envelope(suite_version=1), status="active")
    await repository.save_suite(envelope=_suite_envelope(suite_version=2), status="active")

    patched_latest = await repository.patch_suite_status(
        suite_id="suite-1",
        new_status="disabled",
        changed_by="operator",
        reason="temporary hold",
    )
    patched_specific = await repository.patch_suite_status(
        suite_id="suite-1",
        suite_version=1,
        new_status="active",
        changed_by="operator",
        reason="reactivate",
    )
    missing = await repository.patch_suite_status(suite_id="missing", new_status="disabled")

    assert patched_latest is not None
    assert patched_latest.suiteVersion == 2
    assert patched_latest.status == "disabled"
    assert patched_specific is not None
    assert patched_specific.suiteVersion == 1
    assert patched_specific.status == "active"
    assert missing is None

    all_history = await repository.list_suite_status_history(suite_id="suite-1")
    v2_history = await repository.list_suite_status_history(suite_id="suite-1", suite_version=2)

    assert len(all_history) >= 4
    assert len(v2_history) >= 2
    assert all(row.suiteVersion == 2 for row in v2_history)


@pytest.mark.anyio
async def test_save_suite_preserves_execution_contract_engine_type() -> None:
    repository = InMemoryGxSuiteRepository()

    created = await repository.save_suite(envelope=_suite_envelope(marker="contract"), status="active")

    assert created.executionContract is not None
    assert created.executionContract.engineType == "gx"
    fetched = await repository.get_suite_by_id(suite_id="suite-1", suite_version=1)
    assert fetched is not None
    assert fetched.executionContract is not None
    assert fetched.executionContract.engineType == "gx"
