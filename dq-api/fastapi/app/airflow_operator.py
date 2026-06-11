from __future__ import annotations

import glob
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from typing import Any

from airflow.sdk import BaseOperator

DEFAULT_WAIT_TIMEOUT_SECONDS = 1800.0
DEFAULT_POLL_INTERVAL_SECONDS = 5.0
DEFAULT_AIRFLOW_CONFIG_PREFIX = "DQ_AIRFLOW_"
DEFAULT_SDK_WHEEL_PATH = "/opt/airflow/wheels/dq_made_easy_airflow_sdk-*.whl"
DEFAULT_SDK_INSTALL_ROOT = "/home/airflow/.cache/dq-made-easy-airflow-sdk"

_SDK_RUNNER = """
import json
import sys

from app.airflow_sdk import ValidationRunPlanAirflowClient
from app.airflow_sdk import build_airflow_run_plan_client_config

payload = json.loads(sys.stdin.read())
config_payload = payload["config"]
config = build_airflow_run_plan_client_config(
    base_url=config_payload.get("base_url"),
    token=config_payload.get("token"),
    issuer_url=config_payload.get("issuer_url"),
    client_id=config_payload.get("client_id"),
    username=config_payload.get("username"),
    password=config_payload.get("password"),
    ca_cert=config_payload.get("ca_cert"),
    insecure=config_payload.get("insecure"),
    timeout=config_payload.get("timeout"),
    request_id=config_payload.get("request_id"),
    correlation_id=config_payload.get("correlation_id"),
    prefix=config_payload["prefix"],
)
client = ValidationRunPlanAirflowClient(config)
replay_result = client.replay_run_plan(
    payload["run_plan_id"],
    source_pipeline=payload["source_pipeline"],
    scheduled_at=payload.get("scheduled_at"),
)
result = {
    "run_plan_id": replay_result.run_plan_id,
    "run_plan_version_id": replay_result.run_plan_version_id,
    "run_id": replay_result.run_id,
    "queue_message_id": replay_result.queue_message_id,
    "status": "queued",
    "correlation_id": replay_result.correlation_id,
    "replay": replay_result.payload,
}
if payload["wait_for_completion"]:
    execution_result = client.wait_for_run_completion(
        replay_result.run_id,
        timeout_seconds=float(payload["wait_timeout_seconds"]),
        poll_interval_seconds=float(payload["poll_interval_seconds"]),
    )
    result["status"] = execution_result.status
    result["execution_run"] = execution_result.payload
print(json.dumps(result))
"""


def _require_text(value: str | None, message: str) -> str:
    if value is None or not value.strip():
        raise ValueError(message)
    return value.strip()


def _optional_text(value: str | None) -> str | None:
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


def _context_identifier(context: dict[str, Any], key: str) -> str | None:
    value = context.get(key)
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _run_id_from_context(context: dict[str, Any]) -> str:
    run_id = _context_identifier(context, "run_id")
    if run_id is not None:
        return run_id
    ti = context.get("ti")
    task_run_id = getattr(ti, "run_id", None)
    if isinstance(task_run_id, str) and task_run_id.strip():
        return task_run_id.strip()
    dag_run = context.get("dag_run")
    dag_run_id = getattr(dag_run, "run_id", None)
    if isinstance(dag_run_id, str) and dag_run_id.strip():
        return dag_run_id.strip()
    return "manual"


def _task_id_from_context(context: dict[str, Any]) -> str:
    ti = context.get("ti")
    task_id = getattr(ti, "task_id", None)
    if isinstance(task_id, str) and task_id.strip():
        return task_id.strip()
    return "dq_validation_run_plan"


def _dag_id_from_context(context: dict[str, Any]) -> str:
    dag = context.get("dag")
    dag_id = getattr(dag, "dag_id", None)
    if isinstance(dag_id, str) and dag_id.strip():
        return dag_id.strip()
    ti = context.get("ti")
    task_dag_id = getattr(ti, "dag_id", None)
    if isinstance(task_dag_id, str) and task_dag_id.strip():
        return task_dag_id.strip()
    return "dq_validation_run_plan"


class DqValidationRunPlanOperator(BaseOperator):
    template_fields = ("run_plan_id", "scheduled_at", "source_pipeline", "correlation_id")
    ui_color = "#d9edf7"
    ui_fgcolor = "#1f2937"
    custom_operator_name = "DQ Validation Run Plan"

    def __init__(
        self,
        *,
        run_plan_id: str,
        wait_for_completion: bool = True,
        source_pipeline: str = "airflow",
        scheduled_at: str | None = None,
        correlation_id: str | None = None,
        request_id: str | None = None,
        base_url: str | None = None,
        token: str | None = None,
        issuer_url: str | None = None,
        client_id: str | None = None,
        username: str | None = None,
        password: str | None = None,
        ca_cert: str | None = None,
        insecure: bool | None = None,
        api_timeout: float | None = None,
        wait_timeout_seconds: float = DEFAULT_WAIT_TIMEOUT_SECONDS,
        poll_interval_seconds: float = DEFAULT_POLL_INTERVAL_SECONDS,
        airflow_config_prefix: str = DEFAULT_AIRFLOW_CONFIG_PREFIX,
        sdk_wheel_path: str = DEFAULT_SDK_WHEEL_PATH,
        sdk_install_root: str = DEFAULT_SDK_INSTALL_ROOT,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self.run_plan_id = run_plan_id
        self.wait_for_completion = wait_for_completion
        self.source_pipeline = source_pipeline
        self.scheduled_at = scheduled_at
        self.correlation_id = correlation_id
        self.request_id = request_id
        self.base_url = base_url
        self.token = token
        self.issuer_url = issuer_url
        self.client_id = client_id
        self.username = username
        self.password = password
        self.ca_cert = ca_cert
        self.insecure = insecure
        self.api_timeout = api_timeout
        self.wait_timeout_seconds = wait_timeout_seconds
        self.poll_interval_seconds = poll_interval_seconds
        self.airflow_config_prefix = airflow_config_prefix
        self.sdk_wheel_path = sdk_wheel_path
        self.sdk_install_root = sdk_install_root

    def _sdk_config_payload(self, context: dict[str, Any]) -> dict[str, Any]:
        run_id = _run_id_from_context(context)
        dag_id = _dag_id_from_context(context)
        task_id = _task_id_from_context(context)
        return {
            "base_url": _optional_text(self.base_url),
            "token": _optional_text(self.token),
            "issuer_url": _optional_text(self.issuer_url),
            "client_id": _optional_text(self.client_id),
            "username": _optional_text(self.username),
            "password": _optional_text(self.password),
            "ca_cert": _optional_text(self.ca_cert),
            "insecure": self.insecure,
            "timeout": self.api_timeout,
            "request_id": _optional_text(self.request_id) or f"airflow-request:{dag_id}:{task_id}:{run_id}",
            "correlation_id": _optional_text(self.correlation_id) or f"airflow:{dag_id}:{task_id}:{run_id}",
            "prefix": _require_text(_optional_text(self.airflow_config_prefix), "airflow_config_prefix is required"),
        }

    def _run_subprocess(
        self,
        args: list[str],
        *,
        input_text: str | None = None,
        env: dict[str, str] | None = None,
        context: str,
    ) -> subprocess.CompletedProcess[str]:
        completed = subprocess.run(
            args,
            input=input_text,
            text=True,
            capture_output=True,
            env=env,
            check=False,
        )
        if completed.returncode == 0:
            return completed
        stderr = completed.stderr.strip()
        stdout = completed.stdout.strip()
        detail = stderr or stdout or f"exit code {completed.returncode}"
        raise RuntimeError(f"{context}: {detail}")

    def _install_sdk_wheel(self) -> Path:
        wheel_pattern = _require_text(_optional_text(self.sdk_wheel_path), "sdk_wheel_path is required")
        wheel_matches = sorted(glob.glob(wheel_pattern))
        if not wheel_matches:
            raise RuntimeError(f"dq-made-easy-airflow-sdk wheel is missing: {wheel_pattern}")
        if len(wheel_matches) > 1:
            raise RuntimeError(f"dq-made-easy-airflow-sdk wheel pattern matched multiple files: {wheel_matches}")
        wheel_path = Path(wheel_matches[0])

        install_root = Path(_require_text(_optional_text(self.sdk_install_root), "sdk_install_root is required"))
        target_dir = install_root / "site-packages"
        shutil.rmtree(target_dir, ignore_errors=True)
        target_dir.mkdir(parents=True, exist_ok=True)

        self.log.info("Installing dq-made-easy-airflow-sdk wheel from %s", wheel_path)
        self._run_subprocess(
            [
                sys.executable,
                "-m",
                "pip",
                "install",
                "--disable-pip-version-check",
                "--no-deps",
                "--target",
                str(target_dir),
                str(wheel_path),
            ],
            context="dq-made-easy-airflow-sdk install failed",
        )
        return target_dir

    def _invoke_sdk(self, sdk_site_packages: Path, payload: dict[str, Any]) -> dict[str, Any]:
        env = dict(os.environ)
        existing_pythonpath = env.get("PYTHONPATH")
        if existing_pythonpath:
            env["PYTHONPATH"] = f"{sdk_site_packages}{os.pathsep}{existing_pythonpath}"
        else:
            env["PYTHONPATH"] = str(sdk_site_packages)

        completed = self._run_subprocess(
            [sys.executable, "-c", _SDK_RUNNER],
            input_text=json.dumps(payload),
            env=env,
            context="dq-made-easy-airflow-sdk execution failed",
        )
        output = completed.stdout.strip()
        if not output:
            raise RuntimeError("dq-made-easy-airflow-sdk execution failed: no JSON output returned")
        return json.loads(output)

    def execute(self, context: dict[str, Any]) -> dict[str, Any]:
        normalized_run_plan_id = _require_text(_optional_text(self.run_plan_id), "run_plan_id is required")
        normalized_source_pipeline = _require_text(_optional_text(self.source_pipeline), "source_pipeline is required")
        normalized_scheduled_at = _optional_text(self.scheduled_at)
        sdk_site_packages = self._install_sdk_wheel()
        return self._invoke_sdk(
            sdk_site_packages,
            {
                "config": self._sdk_config_payload(context),
                "run_plan_id": normalized_run_plan_id,
                "source_pipeline": normalized_source_pipeline,
                "scheduled_at": normalized_scheduled_at,
                "wait_for_completion": bool(self.wait_for_completion),
                "wait_timeout_seconds": float(self.wait_timeout_seconds),
                "poll_interval_seconds": float(self.poll_interval_seconds),
            },
        )