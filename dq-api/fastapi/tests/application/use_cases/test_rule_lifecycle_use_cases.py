import asyncio
import importlib
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.application.use_cases.activate_rule import activate_rule
from app.application.use_cases.activate_rule import ActivateRuleCommand
from app.application.use_cases.remove_rule import remove_rule
from app.application.use_cases.remove_rule import RemoveRuleCommand
from app.domain.entities import build_rule_record_entity


activate_rule_module = importlib.import_module("app.application.use_cases.activate_rule")


pytestmark = pytest.mark.usefixtures("clone_payload")


def _run(coro):
    return asyncio.run(coro)


def _sodacl_rule_entity() -> SimpleNamespace:
    return SimpleNamespace(
        expression="email IS NOT NULL",
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


@pytest.fixture
def lifecycle_repository():
    class _Repository:
        def __init__(self) -> None:
            self.rows = [{"id": "rule-1", "active": False, "last_approval_status": "approved"}]
            self.activated: list[str] = []
            self.soft_deleted: list[tuple[str, str]] = []
            self.rule_entity = SimpleNamespace(expression="email IS NOT NULL")
            self.activate_payload = {"id": "rule-1", "active": True}

        async def list_rule_records(self, **kwargs):
            del kwargs
            return [build_rule_record_entity(row) for row in self.rows]

        async def activate_rule_record(self, rule_id: str):
            self.activated.append(rule_id)
            return build_rule_record_entity(self.activate_payload)

        async def get_rule_by_id(self, rule_id: str):
            if rule_id != "rule-1":
                return None
            return self.rule_entity

        async def soft_delete_rule_record(self, rule_id: str, *, removed_by: str):
            self.soft_deleted.append((rule_id, removed_by))
            return build_rule_record_entity({"id": rule_id, "removed": True, "removed_by": removed_by})

    return _Repository()


def test_activate_rule_fails_fast_for_future_effective_at(lifecycle_repository) -> None:
    with pytest.raises(HTTPException) as exc_info:
        _run(
            activate_rule(
                ActivateRuleCommand(rule_id="rule-1", effective_at="2026-04-24T13:00:00+00:00"),
                lifecycle_repository,
                validation_artifact_repository=object(),
                gx_suite_repository=object(),
                catalog_repository=object(),
                current_time=lambda: datetime(2026, 4, 24, 12, 0, tzinfo=UTC),
                parse_effective_at_param=lambda value: datetime.fromisoformat(str(value)),
                is_transition_allowed=lambda **kwargs: True,
                resolve_current_rule_version=lambda *args, **kwargs: None,
                compile_rule_to_intermediate_model=lambda **kwargs: {},
                persist_compiler_artifact=lambda *args, **kwargs: None,
                persist_validation_artifact_from_compiler=lambda *args, **kwargs: None,
                set_span_attributes=lambda *args, **kwargs: None,
                log_event=lambda *args, **kwargs: None,
                logger=SimpleNamespace(),
            )
        )

    assert exc_info.value.status_code == 503
    assert exc_info.value.detail == {
        "error": "downstream_unavailable",
        "service": "lifecycle-scheduler",
        "message": "lifecycle-scheduler is unavailable",
    }


def test_activate_rule_compiles_persists_and_autopublishes(lifecycle_repository, monkeypatch) -> None:
    artifact_calls: list[dict] = []
    gx_suite_calls: list[dict] = []
    validation_artifact_publish_calls: list[dict] = []
    span_calls: list[tuple[object, dict]] = []
    log_events: list[tuple[str, dict]] = []
    validation_artifact_repository = object()
    gx_suite_repository = object()
    catalog_repository = object()
    publish_request = SimpleNamespace(
        dataObjectId="obj-1",
        datasetId="set-1",
        dataProductId="prod-1",
    )

    async def resolve_current_rule_version(repository, rule_id: str):
        del repository
        return SimpleNamespace(id=f"rv-{rule_id}", versionNumber=3)

    async def persist_compiler_artifact(repository, **kwargs):
        del repository
        artifact_calls.append(kwargs)

    async def persist_gx_suite_from_compiler(gx_suite_repository, **kwargs):
        del gx_suite_repository
        gx_suite_calls.append(kwargs)

    monkeypatch.setattr(activate_rule_module, "persist_gx_suite_from_compiler", persist_gx_suite_from_compiler)

    async def persist_validation_artifact_from_compiler(validation_artifact_repository, **kwargs):
        del validation_artifact_repository
        validation_artifact_publish_calls.append(kwargs)

    def set_span_attributes(span, **kwargs):
        span_calls.append((span, kwargs))

    def log_event(logger, event_name, **kwargs):
        del logger
        log_events.append((event_name, kwargs))

    payload = _run(
        activate_rule(
            ActivateRuleCommand(
                rule_id="rule-1",
                granted_scopes=["dq:rules:activate"],
                auto_publish_request=publish_request,
                saved_by="user-1",
            ),
            lifecycle_repository,
            validation_artifact_repository=validation_artifact_repository,
            gx_suite_repository=gx_suite_repository,
            catalog_repository=catalog_repository,
            span="span-1",
            is_transition_allowed=lambda **kwargs: kwargs["to_status"] == "activated",
            resolve_current_rule_version=resolve_current_rule_version,
            compile_rule_to_intermediate_model=lambda **kwargs: {
                "artifactKey": "artifact-1",
                "compilerVersion": "dq-7.3.0",
                "filter": {"normalized": kwargs["filter_expression"]},
            },
            persist_compiler_artifact=persist_compiler_artifact,
            persist_validation_artifact_from_compiler=persist_validation_artifact_from_compiler,
            set_span_attributes=set_span_attributes,
            log_event=log_event,
            logger=SimpleNamespace(),
        )
    )

    assert payload["id"] == "rule-1"
    assert payload["active"] is True
    assert lifecycle_repository.activated == ["rule-1"]
    assert artifact_calls == [
        {
            "rule_id": "rule-1",
            "filter_expression": "email IS NOT NULL",
            "intermediate_model": {
                "artifactKey": "artifact-1",
                "compilerVersion": "dq-7.3.0",
                "filter": {"normalized": "email IS NOT NULL"},
            },
        }
    ]
    assert len(gx_suite_calls) == 1
    assert gx_suite_calls[0]["rule_id"] == "rule-1"
    assert gx_suite_calls[0]["rule_version_id"] == "rv-rule-1"
    assert gx_suite_calls[0]["rule"] is lifecycle_repository.rule_entity
    assert gx_suite_calls[0]["catalog_repository"] is catalog_repository
    assert gx_suite_calls[0]["intermediate_model"] == {
        "artifactKey": "artifact-1",
        "compilerVersion": "dq-7.3.0",
        "filter": {"normalized": "email IS NOT NULL"},
    }
    assert gx_suite_calls[0]["publish_request"] is publish_request
    assert gx_suite_calls[0]["saved_by"] == "user-1"
    assert len(validation_artifact_publish_calls) == 1
    assert validation_artifact_publish_calls[0]["rule_id"] == "rule-1"
    assert validation_artifact_publish_calls[0]["rule_version_id"] == "rv-rule-1"
    assert validation_artifact_publish_calls[0]["rule"] is lifecycle_repository.rule_entity
    assert validation_artifact_publish_calls[0]["catalog_repository"] is catalog_repository
    assert validation_artifact_publish_calls[0]["intermediate_model"] == {
        "artifactKey": "artifact-1",
        "compilerVersion": "dq-7.3.0",
        "filter": {"normalized": "email IS NOT NULL"},
    }
    assert validation_artifact_publish_calls[0]["publish_request"] is publish_request
    assert validation_artifact_publish_calls[0]["saved_by"] == "user-1"
    assert span_calls == [
        ("span-1", {"rule_found": True}),
        ("span-1", {"rule_version_id": "rv-rule-1"}),
        ("span-1", {"autopublish_target_engine": "gx"}),
    ]
    assert [event_name for event_name, _ in log_events] == [
        "compiler.activate.start",
        "compiler.compile.complete",
        "compiler.artifact.persist",
        "compiler.gx.auto_publish.start",
        "compiler.gx.auto_publish.complete",
    ]


def test_activate_rule_autopublishes_sodacl_validation_artifact(lifecycle_repository, monkeypatch) -> None:
    artifact_calls: list[dict] = []
    gx_suite_calls: list[dict] = []
    validation_artifact_publish_calls: list[dict] = []
    log_events: list[tuple[str, dict]] = []
    validation_artifact_repository = object()
    gx_suite_repository = object()
    catalog_repository = object()
    publish_request = SimpleNamespace(
        dataObjectId="do-customer",
        datasetId="set-1",
        dataProductId="prod-1",
    )

    lifecycle_repository.rule_entity = _sodacl_rule_entity()

    async def resolve_current_rule_version(repository, rule_id: str):
        del repository
        return SimpleNamespace(id=f"rv-{rule_id}", versionNumber=3)

    async def persist_compiler_artifact(repository, **kwargs):
        del repository
        artifact_calls.append(kwargs)

    async def persist_gx_suite_from_compiler(gx_suite_repository, **kwargs):
        del gx_suite_repository
        gx_suite_calls.append(kwargs)

    async def persist_validation_artifact_from_compiler(validation_artifact_repository, **kwargs):
        del validation_artifact_repository
        validation_artifact_publish_calls.append(kwargs)

    def set_span_attributes(span, **kwargs):
        del span

    def log_event(logger, event_name, **kwargs):
        del logger
        log_events.append((event_name, kwargs))

    monkeypatch.setattr(activate_rule_module, "persist_gx_suite_from_compiler", persist_gx_suite_from_compiler)

    payload = _run(
        activate_rule(
            ActivateRuleCommand(
                rule_id="rule-1",
                granted_scopes=["dq:rules:activate"],
                auto_publish_request=publish_request,
                saved_by="user-1",
            ),
            lifecycle_repository,
            validation_artifact_repository=validation_artifact_repository,
            gx_suite_repository=gx_suite_repository,
            catalog_repository=catalog_repository,
            span="span-1",
            is_transition_allowed=lambda **kwargs: kwargs["to_status"] == "activated",
            resolve_current_rule_version=resolve_current_rule_version,
            compile_rule_to_intermediate_model=lambda **kwargs: {
                "artifactKey": "artifact-1",
                "compilerVersion": "dq-7.3.0",
                "filter": {"normalized": kwargs["filter_expression"]},
            },
            persist_compiler_artifact=persist_compiler_artifact,
            persist_validation_artifact_from_compiler=persist_validation_artifact_from_compiler,
            set_span_attributes=set_span_attributes,
            log_event=log_event,
            logger=SimpleNamespace(),
        )
    )

    assert payload["id"] == "rule-1"
    assert payload["active"] is True
    assert lifecycle_repository.activated == ["rule-1"]
    assert artifact_calls == [
        {
            "rule_id": "rule-1",
            "filter_expression": "email IS NOT NULL",
            "intermediate_model": {
                "artifactKey": "artifact-1",
                "compilerVersion": "dq-7.3.0",
                "filter": {"normalized": "email IS NOT NULL"},
            },
        }
    ]
    assert gx_suite_calls == []
    assert len(validation_artifact_publish_calls) == 1
    assert validation_artifact_publish_calls[0]["rule"] is lifecycle_repository.rule_entity
    assert validation_artifact_publish_calls[0]["publish_request"] is publish_request
    assert validation_artifact_publish_calls[0]["saved_by"] == "user-1"
    assert [event_name for event_name, _ in log_events] == [
        "compiler.activate.start",
        "compiler.compile.complete",
        "compiler.artifact.persist",
        "compiler.sodacl.auto_publish.start",
        "compiler.sodacl.auto_publish.complete",
    ]


def test_remove_rule_soft_deletes_with_transition_check(lifecycle_repository) -> None:
    lifecycle_repository.rows = [{"id": "rule-1", "active": False, "last_approval_status": "deactivated"}]
    seen: list[dict] = []

    def is_transition_allowed(**kwargs):
        seen.append(kwargs)
        return True

    payload = _run(
        remove_rule(
            RemoveRuleCommand(rule_id="rule-1", granted_scopes=["dq:rules:delete"], removed_by="user-2"),
            lifecycle_repository,
            is_transition_allowed=is_transition_allowed,
        )
    )

    assert payload["id"] == "rule-1"
    assert payload["removed"] is True
    assert payload["removed_by"] == "user-2"
    assert lifecycle_repository.soft_deleted == [("rule-1", "user-2")]
    assert seen == [
        {
            "entity": "rule",
            "from_status": "deactivated",
            "to_status": "removed",
            "granted_scopes": ["dq:rules:delete"],
        }
    ]


def test_remove_rule_raises_404_when_rule_is_missing(lifecycle_repository) -> None:
    lifecycle_repository.rows = []

    with pytest.raises(HTTPException) as exc_info:
        _run(
            remove_rule(
                RemoveRuleCommand(rule_id="missing-rule"),
                lifecycle_repository,
                is_transition_allowed=lambda **kwargs: True,
            )
        )

    assert exc_info.value.status_code == 404
    assert "missing-rule" in str(exc_info.value.detail)