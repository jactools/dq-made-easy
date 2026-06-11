from __future__ import annotations

from datetime import datetime, timezone

import pytest

import app.infrastructure.repositories.postgres_validation_artifact_repository as repo_module
from app.domain.entities import ValidationArtifactEngineArtifactEntity
from app.domain.entities import ValidationArtifactEnvelopeEntity
from app.infrastructure.orm.models import ValidationArtifactRegistryRow
from app.infrastructure.orm.models import ValidationArtifactStatusHistoryRow
from app.infrastructure.repositories.postgres_validation_artifact_repository import PostgresValidationArtifactRepository


class _Result:
    def __init__(self, value):
        self._value = value

    def scalar_one_or_none(self):
        return self._value

    def scalars(self):
        return self

    def all(self):
        if isinstance(self._value, list):
            return self._value
        return []


class _Session:
    def __init__(self, execute_results: list[object]) -> None:
        self._execute_results = iter(execute_results)
        self.added: list[object] = []
        self.flushed = False
        self.committed = False

    def execute(self, _statement):
        return _Result(next(self._execute_results))

    def add(self, obj: object) -> None:
        self.added.append(obj)

    def flush(self) -> None:
        self.flushed = True

    def commit(self) -> None:
        self.committed = True


class _Ctx:
    def __init__(self, session: _Session) -> None:
        self._session = session

    def __enter__(self) -> _Session:
        return self._session

    def __exit__(self, exc_type, exc, tb) -> bool:
        return False


def _artifact(*, artifact_id: str = "va-1", artifact_version: int = 1, engine_type: str = "gx") -> ValidationArtifactEnvelopeEntity:
    return ValidationArtifactEnvelopeEntity(
        validationArtifactId=artifact_id,
        validationArtifactVersion=artifact_version,
        engineType=engine_type,
        assignmentScope={"dataObjectId": "do-1", "datasetId": "ds-1", "dataProductId": "prod-1"},
        resolvedExecutionScope={"dataObjectVersionIds": ["dov-1"]},
        compiledFrom={"ruleIds": ["r-1"], "compilerVersion": "v1", "generatedAt": "2026-04-26T10:30:00Z"},
        executionHints={"recommendedEngineTarget": "pyspark", "primaryKeyFields": []},
        runPlanning={
            "engineTarget": "pyspark",
            "executionShape": "single_object",
            "groupingKey": "data_object_version_id",
            "traceability": {
                "ruleId": "r-1",
                "ruleVersionId": "rv-1",
                "validationArtifactId": artifact_id,
                "validationArtifactVersion": artifact_version,
            },
        },
        engineArtifact=ValidationArtifactEngineArtifactEntity(
            engineType=engine_type,
            artifactKind="gx_expectation_suite" if engine_type == "gx" else "soda_scan",
            artifactSchemaVersion="gx-artifact-envelope/v1" if engine_type == "gx" else "soda-scan/v1",
            payload={
                "suiteId": artifact_id,
                "suiteVersion": artifact_version,
            }
            if engine_type == "gx"
            else {"scanName": artifact_id, "checks": []},
        ),
    )


@pytest.mark.anyio
async def test_postgres_validation_artifact_repository_saves_non_gx_artifact_directly(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = _Session([None])
    monkeypatch.setattr(repo_module, "session_scope", lambda _dsn: _Ctx(session))
    repository = PostgresValidationArtifactRepository("postgresql://unused")

    saved = await repository.save_artifact(
        envelope=_artifact(artifact_id="soda-art-1", engine_type="soda"),
        status="active",
        saved_by="user-a",
        source_pipeline="rule-compiler",
    )

    registry_row = next(obj for obj in session.added if isinstance(obj, ValidationArtifactRegistryRow))
    history_row = next(obj for obj in session.added if isinstance(obj, ValidationArtifactStatusHistoryRow))

    assert saved.validationArtifactId == "soda-art-1"
    assert saved.engineType == "soda"
    assert registry_row.engine_type == "soda"
    assert registry_row.validation_artifact_id == "soda-art-1"
    assert registry_row.compiled_rule_ids == ["r-1"]
    assert history_row.to_status == "active"
    assert session.flushed is True
    assert session.committed is True


@pytest.mark.anyio
async def test_postgres_validation_artifact_repository_normalizes_seeded_gx_payloads(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seeded_row = ValidationArtifactRegistryRow(
        id="val-art-gx-1",
        validation_artifact_id="gx_suite_1",
        validation_artifact_version=2,
        artifact_contract_version="v1",
        engine_type="gx",
        status="active",
        data_object_id="do-1",
        dataset_id="ds-1",
        data_product_id="prod-1",
        resolved_data_object_version_ids=["dov-1"],
        compiled_rule_ids=["r-1"],
        compiler_version="v1",
        generated_at=datetime(2026, 4, 26, 10, 30, tzinfo=timezone.utc),
        envelope_json={
            "assignmentScope": {"dataObjectId": "do-1", "datasetId": "ds-1", "dataProductId": "prod-1"},
            "resolvedExecutionScope": {"dataObjectVersionIds": ["dov-1"]},
            "gxSuite": {"expectation_suite_name": "dq_suite", "expectations": [], "meta": {}},
            "compiledFrom": {"ruleIds": ["r-1"], "compilerVersion": "v1", "generatedAt": "2026-04-26T10:30:00Z"},
            "executionHints": {"recommendedEngine": "pyspark", "primaryKeyFields": []},
            "executionContract": {
                "engineTarget": "pyspark",
                "executionShape": "single_object",
                "traceability": {
                    "ruleId": "r-1",
                    "ruleVersionId": "rv-1",
                    "gxSuiteId": "gx_suite_1",
                    "gxSuiteVersion": 2,
                    "dataObjectVersionId": "dov-1",
                },
            },
        },
        created_at=datetime(2026, 4, 26, 10, 30, tzinfo=timezone.utc),
        updated_at=datetime(2026, 4, 26, 10, 30, tzinfo=timezone.utc),
        saved_by="user-a",
        source_pipeline="seed_csv",
    )
    session = _Session([seeded_row])
    monkeypatch.setattr(repo_module, "session_scope", lambda _dsn: _Ctx(session))
    repository = PostgresValidationArtifactRepository("postgresql://unused")

    loaded = await repository.get_artifact_by_id(artifact_id="gx_suite_1", artifact_version=2)

    assert loaded is not None
    assert loaded.validationArtifactId == "gx_suite_1"
    assert loaded.engineType == "gx"
    assert loaded.engineArtifact.engineType == "gx"
    assert loaded.runPlanning.traceability.validationArtifactVersion == 2


@pytest.mark.anyio
async def test_postgres_validation_artifact_repository_patch_status_tracks_history(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    existing_row = ValidationArtifactRegistryRow(
        id="val-art-1",
        validation_artifact_id="va-1",
        validation_artifact_version=1,
        artifact_contract_version="v1",
        engine_type="soda",
        status="active",
        data_object_id="do-1",
        dataset_id="ds-1",
        data_product_id="prod-1",
        resolved_data_object_version_ids=["dov-1"],
        compiled_rule_ids=["r-1"],
        compiler_version="v1",
        generated_at=datetime(2026, 4, 26, 10, 30, tzinfo=timezone.utc),
        envelope_json=_artifact(engine_type="soda").model_dump(mode="python", by_alias=False, exclude_none=True),
        created_at=datetime(2026, 4, 26, 10, 30, tzinfo=timezone.utc),
        updated_at=datetime(2026, 4, 26, 10, 30, tzinfo=timezone.utc),
        saved_by="user-a",
        source_pipeline="rule-compiler",
    )
    session = _Session([existing_row])
    monkeypatch.setattr(repo_module, "session_scope", lambda _dsn: _Ctx(session))
    repository = PostgresValidationArtifactRepository("postgresql://unused")

    updated = await repository.patch_artifact_status(
        artifact_id="va-1",
        new_status="disabled",
        changed_by="user-b",
        reason="manual",
    )

    history_row = next(obj for obj in session.added if isinstance(obj, ValidationArtifactStatusHistoryRow))
    assert updated is not None
    assert updated.status == "disabled"
    assert existing_row.envelope_json["status"] == "disabled"
    assert history_row.from_status == "active"
    assert history_row.to_status == "disabled"
    assert history_row.reason == "manual"
    assert session.committed is True