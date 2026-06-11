from __future__ import annotations

from types import SimpleNamespace

import pytest

import app.api.v1.testing_api as testing_api


def test_testing_api_simple_forwarders_delegate(monkeypatch: pytest.MonkeyPatch) -> None:
    sentinels: dict[str, object] = {}

    monkeypatch.setattr(
        testing_api._testing_data_requests_api,
        "build_report_test_data_materialization_completion_command",
        lambda request_id, payload: sentinels.setdefault("report_command", (request_id, payload)),
    )
    monkeypatch.setattr(
        testing_api._testing_data_requests_api,
        "bind_queued_test_data_request_enqueuer",
        lambda request: sentinels.setdefault("queued_enqueuer", request),
    )
    monkeypatch.setattr(
        testing_api._testing_data_requests_api,
        "bind_test_data_materialization_request_enqueuer",
        lambda request, catalog_repository: sentinels.setdefault("materialization_enqueuer", (request, catalog_repository)),
    )
    monkeypatch.setattr(
        testing_api._testing_data_requests_api,
        "bind_materialized_delivery_completion_registrar",
        lambda catalog_repository: sentinels.setdefault("delivery_registrar", catalog_repository),
    )
    monkeypatch.setattr(
        testing_api._testing_data_requests_api,
        "queued_test_data_request_view_payload",
        lambda payload: {"queued": payload},
    )
    monkeypatch.setattr(
        testing_api._testing_data_requests_api,
        "test_data_materialization_request_view_payload",
        lambda payload: {"materialization": payload},
    )
    monkeypatch.setattr(testing_api._testing_data_requests_api, "resolve_test_data_redis_url", lambda: "redis://queue")
    monkeypatch.setattr(
        testing_api._testing_data_requests_api,
        "build_report_test_data_materialization_completion_command",
        lambda request_id, payload: {"request_id": request_id, "payload": payload},
    )
    monkeypatch.setattr(
        testing_api._testing_generated_data_api,
        "_persist_generated_data_test_proof",
        lambda repository, **kwargs: {"repository": repository, **kwargs},
    )
    monkeypatch.setattr(
        testing_api._testing_generated_data_api,
        "build_generated_test_data_services",
        lambda request, catalog_repository: (request, catalog_repository),
    )
    monkeypatch.setattr(
        testing_api._testing_generated_data_api,
        "build_start_generated_data_rule_test_services",
        lambda repository, rules_repository: (repository, rules_repository),
    )
    monkeypatch.setattr(
        testing_api._testing_generated_data_api,
        "build_generated_data_rule_test_services",
        lambda request, repository, rules_repository, catalog_repository: (request, repository, rules_repository, catalog_repository),
    )
    monkeypatch.setattr(
        testing_api._testing_generated_data_api,
        "build_generated_data_failure_context",
        lambda detail: {"detail": detail},
    )
    monkeypatch.setattr(
        testing_api._testing_generated_data_api,
        "build_generated_data_success_span_attributes",
        lambda response_payload: {"payload": response_payload},
    )
    monkeypatch.setattr(
        testing_api._testing_generated_data_api,
        "generate_test_data_payload",
        lambda request, version_id, payload, catalog_repository: {"request": request, "version_id": version_id, "payload": payload, "catalog_repository": catalog_repository},
    )

    result = testing_api.build_report_test_data_materialization_completion_command("req-1", {"status": "done"})
    enqueuer = testing_api.bind_queued_test_data_request_enqueuer(SimpleNamespace(name="request"))
    materialization_enqueuer = testing_api.bind_test_data_materialization_request_enqueuer(SimpleNamespace(name="request"), SimpleNamespace(name="catalog"))
    delivery_registrar = testing_api.bind_materialized_delivery_completion_registrar(SimpleNamespace(name="catalog"))
    queued_payload = testing_api.queued_test_data_request_view_payload({"id": "queued"})
    materialization_payload = testing_api.test_data_materialization_request_view_payload({"id": "mat"})
    redis_url = testing_api.resolve_test_data_redis_url()

    assert result == {"request_id": "req-1", "payload": {"status": "done"}}
    assert enqueuer.name == "request"
    assert materialization_enqueuer[1].name == "catalog"
    assert delivery_registrar.name == "catalog"
    assert queued_payload == {"queued": {"id": "queued"}}
    assert materialization_payload == {"materialization": {"id": "mat"}}
    assert redis_url == "redis://queue"


@pytest.mark.anyio
async def test_testing_api_async_forwarders_and_binders(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    async def _read_test_data_request_record(redis_url: str, request_id: str) -> dict[str, str]:
        captured["read_request"] = (redis_url, request_id)
        return {"redis_url": redis_url, "request_id": request_id}

    async def _read_test_data_materialization_record(redis_url: str, request_id: str) -> dict[str, str]:
        captured["read_materialization"] = (redis_url, request_id)
        return {"redis_url": redis_url, "request_id": request_id}

    async def _build_execution_context(rules_repository: object, rule_id: str) -> dict[str, object]:
        captured["execution_context"] = (rules_repository, rule_id)
        return {"rule_id": rule_id}

    async def _resolve_current_rule_status(rules_repository: object, rule_id: str) -> str:
        captured["current_status"] = (rules_repository, rule_id)
        return "approved"

    async def _record_transition(rule_id: str, current_status: str, next_status: str, actor_id: str | None, *, reason: str | None = None) -> None:
        captured["transition"] = (rule_id, current_status, next_status, actor_id, reason)

    monkeypatch.setattr(testing_api._testing_data_requests_api, "read_test_data_request_record", _read_test_data_request_record)
    monkeypatch.setattr(testing_api._testing_data_requests_api, "read_test_data_materialization_record", _read_test_data_materialization_record)
    monkeypatch.setattr(testing_api._rule_testing_context, "build_execution_context", _build_execution_context)
    monkeypatch.setattr(testing_api._rule_testing_context, "resolve_current_rule_status", _resolve_current_rule_status)
    monkeypatch.setattr(testing_api._testing_generated_data_api, "build_generated_data_failure_context", lambda detail: {"detail": detail})
    monkeypatch.setattr(testing_api._testing_generated_data_api, "build_generated_data_success_span_attributes", lambda response_payload: {"payload": response_payload})

    rules_repository = SimpleNamespace(
        record_rule_status_transition=_record_transition,
        compare_rule_versions=lambda rule_id, previous_version_id, latest_version_id: (rule_id, previous_version_id, latest_version_id),
        get_rule_by_id=lambda rule_id: {"rule_id": rule_id},
        get_rule_version=lambda rule_id, version_id: {"rule_id": rule_id, "version_id": version_id},
    )
    repository = SimpleNamespace(
        get_batch_test_request=lambda request_id: {"request_id": request_id},
        run_batch_test_request=lambda request_id: {"request_id": request_id},
        run_rule_against_test_data=lambda rule_id, payload: {"rule_id": rule_id, "payload": payload},
        store_test_proof=lambda **kwargs: kwargs,
        list_test_proofs=lambda rule_id: [{"rule_id": rule_id}],
    )

    request_record = await testing_api.read_test_data_request_record("redis://queue", "request-1")
    materialization_record = await testing_api.read_test_data_materialization_record("redis://queue", "materialization-1")
    execution_context_builder = testing_api._bind_execution_context_builder(rules_repository)
    current_status_resolver = testing_api._bind_current_rule_status_resolver(rules_repository)
    transition_recorder = testing_api._bind_rule_tested_transition_recorder(rules_repository)
    compare_versions = testing_api._bind_rule_versions_comparer(rules_repository)
    get_rule = testing_api._bind_rule_getter(rules_repository)
    get_rule_version = testing_api._bind_rule_version_getter(rules_repository)

    assert request_record == {"redis_url": "redis://queue", "request_id": "request-1"}
    assert materialization_record == {"redis_url": "redis://queue", "request_id": "materialization-1"}
    assert await execution_context_builder("rule-1") == {"rule_id": "rule-1"}
    assert await current_status_resolver("rule-1") == "approved"
    await transition_recorder("rule-1", "approved", "user-1")
    assert compare_versions("rule-1", "v1", "v2") == ("rule-1", "v1", "v2")
    assert get_rule("rule-1") == {"rule_id": "rule-1"}
    assert get_rule_version("rule-1", "v2") == {"rule_id": "rule-1", "version_id": "v2"}

    batch_services = testing_api.build_batch_test_request_execution_services(repository, rules_repository)
    rule_services = testing_api.build_rule_with_data_execution_services(repository, rules_repository)
    manual_services = testing_api.build_manual_test_proof_services(repository, rules_repository)
    proof_report_services = testing_api.build_test_proof_report_services(repository, rules_repository)

    assert batch_services.get_batch_test_request("request-1") == {"request_id": "request-1"}
    assert rule_services.run_rule_against_test_data("rule-1", {"payload": True}) == {"rule_id": "rule-1", "payload": {"payload": True}}
    assert await manual_services.resolve_current_rule_status("rule-1") == "approved"
    assert proof_report_services.list_test_proofs("rule-1") == [{"rule_id": "rule-1"}]
    assert captured["transition"] == ("rule-1", "approved", "tested", "user-1", "Rule test passed")
