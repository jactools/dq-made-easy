from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.domain.entities import rule_testing_context as testing_context


class _RepositoryStub:
    def __init__(self, *, version_payload=None, artifact_payload=None, rows=None) -> None:
        self.version_payload = version_payload
        self.artifact_payload = artifact_payload
        self.rows = rows if rows is not None else []
        self.list_rule_records_kwargs = None

    async def get_rule_version(self, rule_id: str, rule_version_id: str):
        del rule_id, rule_version_id
        return self.version_payload

    async def get_active_compiler_artifact(self, rule_version_id: str):
        del rule_version_id
        return self.artifact_payload

    async def list_rule_records(self, **kwargs):
        self.list_rule_records_kwargs = kwargs
        return self.rows


def _artifact_payload(*, normalized: str, execution_contract: dict | None = None) -> dict:
    return {
        "id": "artifact-1",
        "isActive": True,
        "artifactKey": "artifact/key",
        "compilerVersion": "1.0.0",
        "compilerRevision": 7,
        "compileStatus": "compiled",
        "artifactPayload": {
            "schemaVersion": "v1",
            "filter": {
                "normalized": normalized,
                "source": "source_expr",
            },
            "executionContract": execution_contract,
        },
    }


def test_resolve_current_rule_version_delegates_to_autopublish_policy(monkeypatch) -> None:
    async def _resolve(repository, rule_id):
        assert repository == "repo"
        assert rule_id == "rule-1"
        return SimpleNamespace(id="rv-1", versionNumber=9)

    monkeypatch.setattr(testing_context.rule_autopublish_policy, "resolve_current_rule_version", _resolve)

    version = asyncio.run(testing_context.resolve_current_rule_version("repo", "rule-1"))

    assert version is not None
    assert version.id == "rv-1"


def test_raise_compiler_artifact_required_returns_fail_fast_http_exception() -> None:
    with pytest.raises(HTTPException) as exc:
        testing_context.raise_compiler_artifact_required("rule-1", "rv-1")

    assert exc.value.status_code == 409
    assert exc.value.detail["error"] == "active_compiler_artifact_required"
    assert exc.value.detail["rule_id"] == "rule-1"
    assert exc.value.detail["rule_version_id"] == "rv-1"


def test_build_execution_context_fails_when_current_version_missing(monkeypatch) -> None:
    async def _resolve_none(repository, rule_id):
        del repository, rule_id
        return None

    monkeypatch.setattr(testing_context, "resolve_current_rule_version", _resolve_none)

    with pytest.raises(HTTPException) as exc:
        asyncio.run(testing_context.build_execution_context(_RepositoryStub(), "rule-1"))

    assert exc.value.status_code == 409
    assert exc.value.detail["rule_id"] == "rule-1"


def test_build_execution_context_fails_when_version_id_is_blank(monkeypatch) -> None:
    async def _resolve_blank_id(repository, rule_id):
        del repository, rule_id
        return SimpleNamespace(id=" ", versionNumber=3)

    monkeypatch.setattr(testing_context, "resolve_current_rule_version", _resolve_blank_id)

    with pytest.raises(HTTPException) as exc:
        asyncio.run(testing_context.build_execution_context(_RepositoryStub(), "rule-1"))

    assert exc.value.status_code == 409
    assert exc.value.detail["rule_id"] == "rule-1"


def test_build_execution_context_fails_when_active_artifact_missing(monkeypatch) -> None:
    async def _resolve_version(repository, rule_id):
        del repository, rule_id
        return SimpleNamespace(id="rv-1", versionNumber=2)

    monkeypatch.setattr(testing_context, "resolve_current_rule_version", _resolve_version)

    repo = _RepositoryStub(
        version_payload={"id": "rv-1", "versionNumber": 2, "expression": "source_col > 0"},
        artifact_payload=None,
    )

    with pytest.raises(HTTPException) as exc:
        asyncio.run(testing_context.build_execution_context(repo, "rule-1"))

    assert exc.value.status_code == 409
    assert exc.value.detail["rule_version_id"] == "rv-1"


def test_build_execution_context_fails_when_compiled_expression_blank(monkeypatch) -> None:
    async def _resolve_version(repository, rule_id):
        del repository, rule_id
        return SimpleNamespace(id="rv-1", versionNumber=2)

    monkeypatch.setattr(testing_context, "resolve_current_rule_version", _resolve_version)

    repo = _RepositoryStub(
        version_payload={"id": "rv-1", "versionNumber": 2, "expression": "source_col > 0"},
        artifact_payload=_artifact_payload(normalized="   ", execution_contract={"runtime": "gx"}),
    )

    with pytest.raises(HTTPException) as exc:
        asyncio.run(testing_context.build_execution_context(repo, "rule-1"))

    assert exc.value.status_code == 409
    assert exc.value.detail["rule_version_id"] == "rv-1"


def test_build_execution_context_returns_entity_when_compiler_artifact_ready(monkeypatch) -> None:
    async def _resolve_version(repository, rule_id):
        del repository, rule_id
        return SimpleNamespace(id="rv-1", versionNumber=5)

    monkeypatch.setattr(testing_context, "resolve_current_rule_version", _resolve_version)

    repo = _RepositoryStub(
        version_payload={"id": "rv-1", "versionNumber": 5, "expression": "source_col > 0"},
        artifact_payload=_artifact_payload(normalized="compiled_col > 0", execution_contract={"runtime": "gx"}),
    )

    context = asyncio.run(testing_context.build_execution_context(repo, "rule-1"))

    assert context is not None
    assert context.ruleId == "rule-1"
    assert context.ruleVersionId == "rv-1"
    assert context.ruleVersionNumber == 5
    assert context.sourceRuleExpression == "source_col > 0"
    assert context.compiledExpression == "compiled_col > 0"
    assert context.executedExpression == "compiled_col > 0"
    assert context.handoffReady is True


def test_derive_rule_status_from_row_handles_none_and_delegates(monkeypatch) -> None:
    assert testing_context.derive_rule_status_from_row(None) == "draft"

    monkeypatch.setattr(testing_context.rule_policy, "derive_rule_status_from_row", lambda row: "activated")
    assert testing_context.derive_rule_status_from_row({"id": "rule-1"}) == "activated"


def test_resolve_current_rule_status_returns_none_when_no_matching_row() -> None:
    repo = _RepositoryStub(rows=[{"id": "rule-2"}])

    status = asyncio.run(testing_context.resolve_current_rule_status(repo, "rule-1"))

    assert status is None
    assert repo.list_rule_records_kwargs == {
        "workspace": None,
        "include_deleted": True,
        "is_template": False,
        "limit": 500,
        "offset": 0,
    }


def test_resolve_current_rule_status_returns_derived_status_for_matching_row(monkeypatch) -> None:
    monkeypatch.setattr(testing_context, "derive_rule_status_from_row", lambda row: "pending-approval")

    repo = _RepositoryStub(rows=[{"id": "rule-1", "active": False}])
    status = asyncio.run(testing_context.resolve_current_rule_status(repo, "rule-1"))

    assert status == "pending-approval"
