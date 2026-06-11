from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.domain.entities import rule_autopublish_policy as rules_autopublish_support


def _sodacl_rule_entity() -> SimpleNamespace:
    return SimpleNamespace(
        dsl={
            "schema_version": "2.0.0",
            "rule": {
                "kind": "metric_threshold",
                "scope": {
                    "dataset": {
                        "data_object_id": "do-customer",
                    },
                },
                "measure": {
                    "type": "metric",
                    "metric": "row_count",
                },
                "expectation": {
                    "type": "threshold",
                    "operator": "gte",
                    "value": 1,
                    "unit": "count",
                },
                "evidence": {
                    "failed_rows": {
                        "mode": "none",
                        "include_row_identifier": False,
                        "include_primary_key": False,
                    },
                    "emit_compiled_artifact": True,
                    "emit_generated_sql": False,
                },
                "operations": {
                    "severity": "critical",
                    "preferred_engines": ["sodacl", "gx"],
                    "fail_if_not_native": True,
                },
            },
        },
    )


def test_resolve_current_rule_version_variants() -> None:
    class _VRepo:
        def __init__(self, payload):
            self._payload = payload

        async def list_rule_versions(self, rule_id, limit, offset):
            del rule_id, limit, offset
            return self._payload

    assert asyncio.run(rules_autopublish_support.resolve_current_rule_version(_VRepo(None), "r1")) is None
    assert asyncio.run(rules_autopublish_support.resolve_current_rule_version(_VRepo({"versions": []}), "r1")) is None

    payload = {"versions": [{"id": "v1", "isCurrentVersion": True}, {"id": "v2"}]}
    cur = asyncio.run(rules_autopublish_support.resolve_current_rule_version(_VRepo(payload), "r1"))
    assert cur is not None
    assert cur.id == "v1"

    payload2 = {"versions": [{"id": "", "isCurrentVersion": True}]}
    assert asyncio.run(rules_autopublish_support.resolve_current_rule_version(_VRepo(payload2), "r1")) is None


def test_resolve_rule_autopublish_target_engine_variants() -> None:
    assert rules_autopublish_support.resolve_rule_autopublish_target_engine(None) == ("gx", None)

    assert rules_autopublish_support.resolve_rule_autopublish_target_engine(SimpleNamespace(dsl={"schema_version": "1.0.0"})) == ("gx", None)

    with pytest.raises(HTTPException):
        rules_autopublish_support.resolve_rule_autopublish_target_engine(
            SimpleNamespace(
                dsl={
                    "schema_version": "2.0.0",
                    "rule": {
                        "kind": "metric_threshold",
                        "scope": {"dataset": {"data_object_id": "do-1"}},
                        "measure": {"type": "metric", "metric": "row_count"},
                        "expectation": {"type": "threshold", "operator": "gte", "value": 1, "unit": "count"},
                        "evidence": {"failed_rows": {"mode": "none", "include_row_identifier": False, "include_primary_key": False}, "emit_compiled_artifact": True, "emit_generated_sql": False},
                        "operations": {"severity": "critical", "preferred_engines": [], "fail_if_not_native": True},
                    },
                }
            )
        )

    assert rules_autopublish_support.resolve_rule_autopublish_target_engine(_sodacl_rule_entity())[0] == "sodacl"


def test_resolve_rule_autopublish_target_engine_rejects_invalid_target_engine(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(rules_autopublish_support.RuleDslV2Document, "model_validate", lambda raw_dsl: SimpleNamespace(raw_dsl=raw_dsl))
    monkeypatch.setattr(
        rules_autopublish_support,
        "build_rule_dsl_v2_semantic_ir",
        lambda semantic_model: SimpleNamespace(rule=SimpleNamespace(kind="metric_threshold", operations=SimpleNamespace(preferred_engines=["snowflake"]))),
    )

    with pytest.raises(HTTPException) as exc_info:
        rules_autopublish_support.resolve_rule_autopublish_target_engine(
            SimpleNamespace(dsl={"schema_version": "2.0.0"})
        )

    assert exc_info.value.status_code == 422
    assert "auto-publish currently supports only target engines 'gx' and 'sodacl'" in str(exc_info.value.detail["message"])


def test_persist_compiler_artifact_no_version_and_with_version() -> None:
    class _NoVersionRepo:
        async def list_rule_versions(self, rule_id, limit, offset):
            del rule_id, limit, offset
            return None

        async def upsert_active_compiler_artifact(self, **kwargs):
            del kwargs
            raise AssertionError("upsert should not be called when no version")

    none_res = asyncio.run(
        rules_autopublish_support.persist_compiler_artifact(
            repository=_NoVersionRepo(),
            rule_id="r1",
            filter_expression="f",
            intermediate_model={"filter": {}, "diagnostics": []},
        )
    )
    assert none_res is None

    class _WithVersionRepo:
        async def list_rule_versions(self, rule_id, limit, offset):
            del rule_id, limit, offset
            return {"versions": [{"id": "ver123", "isCurrentVersion": True}]}

        async def upsert_active_compiler_artifact(self, **kwargs):
            return {
                "id": "artifact-1",
                "artifactKey": kwargs["artifact_key"],
                "compilerVersion": kwargs["compiler_version"],
                "compilerRevision": 1,
                "compileStatus": kwargs["compile_status"],
                "isActive": True,
                "artifactPayload": kwargs["artifact_payload"],
                "diagnosticsPayload": kwargs["diagnostics_payload"],
            }

    intermediate = {
        "filter": {"normalized": "expr"},
        "diagnostics": [],
        "compilerVersion": "cv",
        "artifactKey": "k",
        "compilable": True,
    }
    res = asyncio.run(
        rules_autopublish_support.persist_compiler_artifact(
            repository=_WithVersionRepo(),
            rule_id="r1",
            filter_expression="f",
            intermediate_model=intermediate,
        )
    )
    assert res is not None
    assert res.id == "artifact-1"
    assert res.artifactKey == "k"
    assert res.compilerVersion == "cv"


def test_persist_gx_suite_from_compiler_early_and_success() -> None:
    class _FakeGX:
        def __init__(self):
            self.called = False

        async def list_suite_status_history(self, **kwargs):
            del kwargs
            return []

        async def save_suite(self, **kwargs):
            del kwargs
            self.called = True

    fake = _FakeGX()
    req = SimpleNamespace(
        dataObjectId=None,
        datasetId=None,
        dataProductId=None,
        dataObjectVersionIds=[],
        primaryKeyFields=[],
        businessKeyFields=[],
        suiteVersion=1,
    )
    assert asyncio.run(
        rules_autopublish_support.persist_gx_suite_from_compiler(
            fake,
            rule_id="r1",
            rule_version_id="rv-1",
            rule=None,
            intermediate_model={},
            publish_request=req,
            saved_by=None,
        )
    ) is None
    assert fake.called is False

    fake2 = _FakeGX()
    req2 = SimpleNamespace(
        dataObjectId="do",
        datasetId=None,
        dataProductId=None,
        dataObjectVersionIds=["v1"],
        primaryKeyFields=["pk"],
        businessKeyFields=[],
        suiteVersion=2,
    )
    assert asyncio.run(
        rules_autopublish_support.persist_gx_suite_from_compiler(
            fake2,
            rule_id="r2",
            rule_version_id="rv-2",
            rule=None,
            intermediate_model={
                "compilerVersion": "cv",
                "artifactKey": "k",
                "filter": {
                    "logicalOperators": [],
                    "predicates": [
                        {
                            "operator": "IS NOT NULL",
                            "field": "email",
                        }
                    ],
                },
            },
            publish_request=req2,
            saved_by="me",
        )
    ) is None
    assert fake2.called is True


def test_persist_validation_artifact_from_compiler_early_and_success() -> None:
    class _FakeArtifacts:
        def __init__(self):
            self.called = False
            self.saved_envelope = None

        async def list_artifact_status_history(self, **kwargs):
            del kwargs
            return []

        async def save_artifact(self, **kwargs):
            self.called = True
            self.saved_envelope = kwargs["envelope"]

    fake = _FakeArtifacts()
    req = SimpleNamespace(
        dataObjectId=None,
        datasetId=None,
        dataProductId=None,
        dataObjectVersionIds=[],
        primaryKeyFields=[],
        businessKeyFields=[],
        suiteVersion=1,
    )
    assert asyncio.run(
        rules_autopublish_support.persist_validation_artifact_from_compiler(
            fake,
            rule_id="r1",
            rule_version_id="rv-1",
            rule=None,
            intermediate_model={},
            publish_request=req,
            saved_by=None,
        )
    ) is None
    assert fake.called is False

    fake2 = _FakeArtifacts()
    req2 = SimpleNamespace(
        dataObjectId="do",
        datasetId=None,
        dataProductId=None,
        dataObjectVersionIds=["v1"],
        primaryKeyFields=["pk"],
        businessKeyFields=[],
        suiteVersion=2,
    )
    assert asyncio.run(
        rules_autopublish_support.persist_validation_artifact_from_compiler(
            fake2,
            rule_id="r2",
            rule_version_id="rv-2",
            rule=None,
            intermediate_model={
                "compilerVersion": "cv",
                "artifactKey": "k",
                "filter": {
                    "logicalOperators": [],
                    "predicates": [
                        {
                            "operator": "IS NOT NULL",
                            "field": "email",
                        }
                    ],
                },
            },
            publish_request=req2,
            saved_by="me",
        )
    ) is None
    assert fake2.called is True
    assert fake2.saved_envelope is not None
    assert fake2.saved_envelope.validationArtifactId == "gx_r2"
    assert fake2.saved_envelope.engineType == "gx"


def test_persist_validation_artifact_from_compiler_uses_sodacl_when_selected() -> None:
    class _FakeArtifacts:
        def __init__(self):
            self.called = False
            self.saved_envelope = None

        async def list_artifact_status_history(self, **kwargs):
            del kwargs
            return []

        async def save_artifact(self, **kwargs):
            self.called = True
            self.saved_envelope = kwargs["envelope"]

    fake = _FakeArtifacts()
    req = SimpleNamespace(
        dataObjectId="do-customer",
        datasetId=None,
        dataProductId=None,
        dataObjectVersionIds=["dov-1"],
        primaryKeyFields=["customer_id"],
        businessKeyFields=[],
        suiteVersion=2,
    )

    assert asyncio.run(
        rules_autopublish_support.persist_validation_artifact_from_compiler(
            fake,
            rule_id="r3",
            rule_version_id="rv-3",
            rule=_sodacl_rule_entity(),
            catalog_repository=None,
            intermediate_model={"compilerVersion": "cv", "artifactKey": "k", "filter": {}},
            publish_request=req,
            saved_by="me",
        )
    ) is None

    assert fake.called is True
    assert fake.saved_envelope is not None
    assert fake.saved_envelope.validationArtifactId == "sodacl_r3"
    assert fake.saved_envelope.engineType == "soda"
