from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from dataclasses import field
from dataclasses import replace
from typing import Any
from typing import Callable
from uuid import uuid4

import httpx


INTERNAL_API_PREFIX = "/api/rulebuilder/v1"
DEFAULT_TIMEOUT_SECONDS = 30.0
DEFAULT_WAIT_TIMEOUT_SECONDS = 1800.0
DEFAULT_POLL_INTERVAL_SECONDS = 5.0
TRUSTED_PROXY_CALLER_HEADER = "x-consumer-custom-id"
TRUSTED_PROXY_CALLER_ID = "dq-airflow"
_TERMINAL_STATUSES = frozenset({"succeeded", "failed", "cancelled"})
_SUCCESS_STATUSES = frozenset({"succeeded"})


class AirflowSdkError(RuntimeError):
    pass


@dataclass(slots=True)
class AirflowRunPlanClientConfig:
    base_url: str
    token: str | None = None
    issuer_url: str | None = None
    client_id: str | None = None
    username: str | None = None
    password: str | None = None
    ca_cert: str | None = None
    insecure: bool = False
    timeout: float = DEFAULT_TIMEOUT_SECONDS
    request_id: str = field(default_factory=lambda: _generated_request_id("dq-airflow-request"))
    correlation_id: str = field(default_factory=lambda: _generated_request_id("dq-airflow-correlation"))


@dataclass(slots=True)
class ValidationRunPlanReplayResult:
    run_id: str
    queue_message_id: str
    run_plan_id: str
    run_plan_version_id: str | None
    trigger_type: str | None
    source_pipeline: str | None
    scheduled_at: str | None
    correlation_id: str | None
    payload: dict[str, Any]


@dataclass(slots=True)
class GxExecutionRunResult:
    run_id: str
    status: str
    payload: dict[str, Any]

    @property
    def is_terminal(self) -> bool:
        return self.status in _TERMINAL_STATUSES


def _env(name: str) -> str | None:
    value = os.environ.get(name)
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


def _generated_request_id(prefix: str) -> str:
    return f"{prefix}-{uuid4().hex}"


def _require(value: str | None, message: str) -> str:
    if value is None or not value.strip():
        raise AirflowSdkError(message)
    return value.strip()


def _parse_bool(value: str | None) -> bool:
    if value is None:
        return False
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off", ""}:
        return False
    raise AirflowSdkError(f"Invalid boolean value: {value!r}")


def build_airflow_run_plan_client_config_from_env(prefix: str = "DQ_AIRFLOW_") -> AirflowRunPlanClientConfig:
    return build_airflow_run_plan_client_config(prefix=prefix)


def build_airflow_run_plan_client_config(
    *,
    base_url: str | None = None,
    token: str | None = None,
    issuer_url: str | None = None,
    client_id: str | None = None,
    username: str | None = None,
    password: str | None = None,
    ca_cert: str | None = None,
    insecure: bool | None = None,
    timeout: float | None = None,
    request_id: str | None = None,
    correlation_id: str | None = None,
    prefix: str = "DQ_AIRFLOW_",
) -> AirflowRunPlanClientConfig:
    resolved_base_url = _require(base_url or _env(f"{prefix}BASE_URL"), f"{prefix}BASE_URL is required")
    timeout_value = _env(f"{prefix}TIMEOUT")
    resolved_timeout = timeout
    if resolved_timeout is None:
        resolved_timeout = DEFAULT_TIMEOUT_SECONDS if timeout_value is None else float(timeout_value)
    resolved_insecure = insecure
    if resolved_insecure is None:
        resolved_insecure = _parse_bool(_env(f"{prefix}INSECURE"))
    return AirflowRunPlanClientConfig(
        base_url=resolved_base_url,
        token=token if token is not None else _env(f"{prefix}TOKEN"),
        issuer_url=issuer_url if issuer_url is not None else _env(f"{prefix}ISSUER_URL"),
        client_id=client_id if client_id is not None else _env(f"{prefix}CLIENT_ID"),
        username=username if username is not None else _env(f"{prefix}USERNAME"),
        password=password if password is not None else _env(f"{prefix}PASSWORD"),
        ca_cert=ca_cert if ca_cert is not None else _env(f"{prefix}CA_CERT"),
        insecure=resolved_insecure,
        timeout=resolved_timeout,
        request_id=request_id if request_id is not None else _generated_request_id("dq-airflow-request"),
        correlation_id=correlation_id if correlation_id is not None else _generated_request_id("dq-airflow-correlation"),
    )


def _create_client(config: AirflowRunPlanClientConfig) -> httpx.Client:
    verify: bool | str = True
    if config.insecure:
        verify = False
    elif config.ca_cert:
        if not os.path.exists(config.ca_cert):
            raise AirflowSdkError(f"CA certificate not found: {config.ca_cert}")
        verify = config.ca_cert

    return httpx.Client(base_url=config.base_url.rstrip("/"), timeout=config.timeout, verify=verify)


def _response_data(response: httpx.Response) -> Any:
    try:
        return response.json()
    except ValueError as exc:
        raise AirflowSdkError(f"Response was not valid JSON: {response.text.strip() or '<empty>'}") from exc


def _error_message(response: httpx.Response, context: str) -> str:
    try:
        payload = response.json()
    except ValueError:
        payload = None
    if isinstance(payload, dict):
        detail = payload.get("detail")
        if isinstance(detail, str) and detail.strip():
            return f"{context}: {detail}"
        if isinstance(detail, dict):
            return f"{context}: {json.dumps(detail, sort_keys=True)}"
    text = response.text.strip()
    return f"{context}: HTTP {response.status_code}{f' - {text}' if text else ''}"


def _build_headers(config: AirflowRunPlanClientConfig, token: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {token}",
        "X-Kong-Request-Id": config.request_id,
        "X-Correlation-ID": config.correlation_id,
        TRUSTED_PROXY_CALLER_HEADER: TRUSTED_PROXY_CALLER_ID,
    }


def _acquire_access_token(client: httpx.Client, config: AirflowRunPlanClientConfig) -> str:
    if config.token is not None and config.token.strip():
        return config.token.strip()

    issuer_url = _require(config.issuer_url, "issuer_url is required when token is not provided")
    client_id = _require(config.client_id, "client_id is required when token is not provided")
    username = _require(config.username, "username is required when token is not provided")
    password = _require(config.password, "password is required when token is not provided")

    token_url = issuer_url.rstrip("/") + "/protocol/openid-connect/token"
    response = client.post(
        token_url,
        data={
            "grant_type": "password",
            "client_id": client_id,
            "username": username,
            "password": password,
        },
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    if response.status_code >= 400:
        raise AirflowSdkError(_error_message(response, "Keycloak token request failed"))

    payload = _response_data(response)
    if not isinstance(payload, dict):
        raise AirflowSdkError("Keycloak token response was not a JSON object")
    access_token = payload.get("access_token")
    if not isinstance(access_token, str) or not access_token.strip():
        raise AirflowSdkError("Keycloak token response did not include access_token")
    return access_token.strip()


class ValidationRunPlanAirflowClient:
    def __init__(
        self,
        config: AirflowRunPlanClientConfig,
        *,
        client_factory: Callable[[AirflowRunPlanClientConfig], httpx.Client] = _create_client,
        sleep_fn: Callable[[float], None] = time.sleep,
        monotonic_fn: Callable[[], float] = time.monotonic,
    ) -> None:
        self._config = config
        self._client_factory = client_factory
        self._sleep_fn = sleep_fn
        self._monotonic_fn = monotonic_fn

    def replay_run_plan(
        self,
        run_plan_id: str,
        *,
        source_pipeline: str = "airflow",
        trigger_type: str = "pipeline_run",
        scheduled_at: str | None = None,
    ) -> ValidationRunPlanReplayResult:
        normalized_run_plan_id = _require(run_plan_id, "run_plan_id is required")
        with self._client_factory(self._config) as client:
            token = _acquire_access_token(client, self._config)
            payload: dict[str, Any] = {
                "trigger_type": trigger_type,
                "source_pipeline": source_pipeline,
            }
            if scheduled_at is not None:
                payload["scheduled_at"] = scheduled_at
            response = client.post(
                f"{INTERNAL_API_PREFIX}/validation-run-plans/{normalized_run_plan_id}/replay",
                json=payload,
                headers=_build_headers(self._config, token),
            )
            if response.status_code != 202:
                raise AirflowSdkError(_error_message(response, "Validation run plan replay request failed"))

            body = _response_data(response)
            if not isinstance(body, dict):
                raise AirflowSdkError("Validation run plan replay response was not a JSON object")
            returned_run_plan_id = body.get("run_plan_id")
            if returned_run_plan_id != normalized_run_plan_id:
                raise AirflowSdkError(
                    f"Validation run plan replay response returned run_plan_id={returned_run_plan_id!r}, expected {normalized_run_plan_id!r}"
                )
            run_id = body.get("run_id")
            if not isinstance(run_id, str) or not run_id.strip():
                raise AirflowSdkError("Validation run plan replay response did not include run_id")
            queue_message_id = body.get("queue_message_id")
            if not isinstance(queue_message_id, str) or not queue_message_id.strip():
                raise AirflowSdkError("Validation run plan replay response did not include queue_message_id")
            return ValidationRunPlanReplayResult(
                run_id=run_id,
                queue_message_id=queue_message_id,
                run_plan_id=normalized_run_plan_id,
                run_plan_version_id=_as_optional_str(body.get("run_plan_version_id")),
                trigger_type=_as_optional_str(body.get("trigger_type")),
                source_pipeline=_as_optional_str(body.get("source_pipeline")),
                scheduled_at=_as_optional_str(body.get("scheduled_at")),
                correlation_id=_as_optional_str(body.get("correlation_id")),
                payload=body,
            )

    def get_execution_run(self, run_id: str) -> GxExecutionRunResult:
        normalized_run_id = _require(run_id, "run_id is required")
        with self._client_factory(self._config) as client:
            token = _acquire_access_token(client, self._config)
            response = client.get(
                f"{INTERNAL_API_PREFIX}/gx/runs/{normalized_run_id}",
                headers=_build_headers(self._config, token),
            )
            if response.status_code != 200:
                raise AirflowSdkError(_error_message(response, "Execution run fetch failed"))

            body = _response_data(response)
            if not isinstance(body, dict):
                raise AirflowSdkError("Execution run response was not a JSON object")
            status = body.get("status")
            if not isinstance(status, str) or not status.strip():
                raise AirflowSdkError("Execution run response did not include status")
            returned_run_id = body.get("id")
            if returned_run_id != normalized_run_id:
                raise AirflowSdkError(f"Execution run response returned id={returned_run_id!r}, expected {normalized_run_id!r}")
            return GxExecutionRunResult(run_id=normalized_run_id, status=status.strip(), payload=body)

    def wait_for_run_completion(
        self,
        run_id: str,
        *,
        timeout_seconds: float = DEFAULT_WAIT_TIMEOUT_SECONDS,
        poll_interval_seconds: float = DEFAULT_POLL_INTERVAL_SECONDS,
    ) -> GxExecutionRunResult:
        if timeout_seconds <= 0:
            raise AirflowSdkError("timeout_seconds must be greater than zero")
        if poll_interval_seconds <= 0:
            raise AirflowSdkError("poll_interval_seconds must be greater than zero")

        deadline = self._monotonic_fn() + timeout_seconds
        while True:
            run = self.get_execution_run(run_id)
            if run.is_terminal:
                if run.status not in _SUCCESS_STATUSES:
                    raise AirflowSdkError(f"Execution run '{run.run_id}' finished with status '{run.status}'")
                return run
            if self._monotonic_fn() >= deadline:
                raise AirflowSdkError(f"Timed out waiting for execution run '{run.run_id}' to finish")
            self._sleep_fn(poll_interval_seconds)

    def invoke_and_wait(
        self,
        run_plan_id: str,
        *,
        source_pipeline: str = "airflow",
        trigger_type: str = "pipeline_run",
        scheduled_at: str | None = None,
        timeout_seconds: float = DEFAULT_WAIT_TIMEOUT_SECONDS,
        poll_interval_seconds: float = DEFAULT_POLL_INTERVAL_SECONDS,
    ) -> GxExecutionRunResult:
        replay_result = self.replay_run_plan(
            run_plan_id,
            source_pipeline=source_pipeline,
            trigger_type=trigger_type,
            scheduled_at=scheduled_at,
        )
        return self.wait_for_run_completion(
            replay_result.run_id,
            timeout_seconds=timeout_seconds,
            poll_interval_seconds=poll_interval_seconds,
        )


def _as_optional_str(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    stripped = value.strip()
    return stripped or None