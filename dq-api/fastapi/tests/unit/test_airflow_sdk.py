from __future__ import annotations

import httpx
import pytest

from app.airflow_sdk import AirflowRunPlanClientConfig
from app.airflow_sdk import AirflowSdkError
from app.airflow_sdk import ValidationRunPlanAirflowClient


@pytest.fixture
def base_config() -> AirflowRunPlanClientConfig:
    return AirflowRunPlanClientConfig(
        base_url="https://kong.example",
        token=None,
        issuer_url="https://keycloak.example/realms/jaccloud",
        client_id="dq-rules-ui",
        username="alice@example.com",
        password="secret",
        ca_cert=None,
        insecure=False,
        timeout=30.0,
        request_id="request-1",
        correlation_id="correlation-1",
    )


def test_replay_run_plan_posts_internal_path_with_airflow_payload(base_config: AirflowRunPlanClientConfig) -> None:
    requests: list[tuple[str, str, str | None, str | None]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = request.read().decode("utf-8")
        requests.append((request.method, str(request.url), body or None, request.headers.get("x-consumer-custom-id")))
        if request.url.path.endswith("/protocol/openid-connect/token"):
            return httpx.Response(200, json={"access_token": "token-123"})
        return httpx.Response(
            202,
            json={
                "run_id": "run-1",
                "queue_message_id": "queue-1",
                "run_plan_id": "run-plan-1",
                "run_plan_version_id": "run-plan-version-1",
                "trigger_type": "pipeline_run",
                "source_pipeline": "airflow",
                "scheduled_at": "2026-05-30T09:00:00Z",
                "correlation_id": "correlation-1",
            },
        )

    client = ValidationRunPlanAirflowClient(
        base_config,
        client_factory=lambda _config: httpx.Client(transport=httpx.MockTransport(handler), base_url="https://kong.example"),
    )

    result = client.replay_run_plan("run-plan-1", scheduled_at="2026-05-30T09:00:00Z")

    assert result.run_id == "run-1"
    assert result.queue_message_id == "queue-1"
    assert result.source_pipeline == "airflow"
    assert requests[0] == (
        "POST",
        "https://keycloak.example/realms/jaccloud/protocol/openid-connect/token",
        "grant_type=password&client_id=dq-rules-ui&username=alice%40example.com&password=secret",
        None,
    )
    assert requests[1] == (
        "POST",
        "https://kong.example/api/rulebuilder/v1/validation-run-plans/run-plan-1/replay",
        '{"trigger_type":"pipeline_run","source_pipeline":"airflow","scheduled_at":"2026-05-30T09:00:00Z"}',
        "dq-airflow",
    )


def test_wait_for_run_completion_returns_succeeded_run() -> None:
    call_count = {"runs": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        call_count["runs"] += 1
        status = "pending" if call_count["runs"] == 1 else "succeeded"
        return httpx.Response(200, json={"id": "run-1", "status": status})

    client = ValidationRunPlanAirflowClient(
        AirflowRunPlanClientConfig(base_url="https://kong.example", token="token-123"),
        client_factory=lambda _config: httpx.Client(transport=httpx.MockTransport(handler), base_url="https://kong.example"),
        sleep_fn=lambda _seconds: None,
        monotonic_fn=lambda: 0.0,
    )

    result = client.wait_for_run_completion("run-1", timeout_seconds=10.0, poll_interval_seconds=0.1)

    assert result.run_id == "run-1"
    assert result.status == "succeeded"
    assert call_count["runs"] == 2


def test_invoke_and_wait_fails_closed_when_run_fails(base_config: AirflowRunPlanClientConfig) -> None:
    responses = {
        "/realms/jaccloud/protocol/openid-connect/token": httpx.Response(200, json={"access_token": "token-123"}),
        "/api/rulebuilder/v1/validation-run-plans/run-plan-1/replay": httpx.Response(
            202,
            json={
                "run_id": "run-1",
                "queue_message_id": "queue-1",
                "run_plan_id": "run-plan-1",
            },
        ),
        "/api/rulebuilder/v1/gx/runs/run-1": httpx.Response(200, json={"id": "run-1", "status": "failed"}),
    }

    def handler(request: httpx.Request) -> httpx.Response:
        return responses[request.url.path]

    client = ValidationRunPlanAirflowClient(
        base_config,
        client_factory=lambda _config: httpx.Client(transport=httpx.MockTransport(handler), base_url="https://kong.example"),
        sleep_fn=lambda _seconds: None,
        monotonic_fn=lambda: 0.0,
    )

    with pytest.raises(AirflowSdkError, match="finished with status 'failed'"):
        client.invoke_and_wait("run-plan-1", timeout_seconds=10.0, poll_interval_seconds=0.1)