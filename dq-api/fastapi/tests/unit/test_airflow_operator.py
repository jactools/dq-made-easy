from __future__ import annotations

import importlib
from pathlib import Path
from types import ModuleType
from types import SimpleNamespace
import sys

import pytest


def _install_fake_airflow_sdk(monkeypatch: pytest.MonkeyPatch) -> None:
    airflow_module = ModuleType("airflow")
    airflow_sdk_module = ModuleType("airflow.sdk")

    class BaseOperator:
        template_fields: tuple[str, ...] = ()

        def __init__(self, task_id: str | None = None, **_: object) -> None:
            self.task_id = task_id or "task"

    airflow_sdk_module.BaseOperator = BaseOperator
    monkeypatch.setitem(sys.modules, "airflow", airflow_module)
    monkeypatch.setitem(sys.modules, "airflow.sdk", airflow_sdk_module)


def _load_operator_module(monkeypatch: pytest.MonkeyPatch):
    _install_fake_airflow_sdk(monkeypatch)
    sys.modules.pop("app.airflow_operator", None)
    return importlib.import_module("app.airflow_operator")


def test_operator_waits_for_completion(monkeypatch: pytest.MonkeyPatch) -> None:
    module = _load_operator_module(monkeypatch)
    captured: dict[str, object] = {}

    monkeypatch.setattr(module.DqValidationRunPlanOperator, "_install_sdk_wheel", lambda self: Path("/sdk/site-packages"))

    def _fake_invoke(self, sdk_site_packages: Path, payload: dict[str, object]) -> dict[str, object]:
        captured["sdk_site_packages"] = sdk_site_packages
        captured["payload"] = payload
        return {
            "run_plan_id": "run-plan-1",
            "run_plan_version_id": "run-plan-version-1",
            "run_id": "run-1",
            "queue_message_id": "queue-1",
            "status": "succeeded",
            "correlation_id": "airflow:dq_validation_run_plan:invoke_validation_run_plan:manual__1",
            "replay": {"run_id": "run-1"},
            "execution_run": {"id": "run-1", "status": "succeeded"},
        }

    monkeypatch.setattr(module.DqValidationRunPlanOperator, "_invoke_sdk", _fake_invoke)

    operator = module.DqValidationRunPlanOperator(
        task_id="invoke_validation_run_plan",
        run_plan_id="run-plan-1",
        base_url="https://kong.example",
        token="token-123",
        wait_timeout_seconds=600.0,
        poll_interval_seconds=2.5,
    )

    payload = operator.execute(
        {
            "dag": SimpleNamespace(dag_id="dq_validation_run_plan"),
            "ti": SimpleNamespace(task_id="invoke_validation_run_plan", dag_id="dq_validation_run_plan", run_id="manual__1"),
        }
    )

    assert payload["run_id"] == "run-1"
    assert payload["status"] == "succeeded"
    assert payload["execution_run"] == {"id": "run-1", "status": "succeeded"}
    assert captured["sdk_site_packages"] == Path("/sdk/site-packages")
    assert captured["payload"] == {
        "config": {
            "base_url": "https://kong.example",
            "token": "token-123",
            "issuer_url": None,
            "client_id": None,
            "username": None,
            "password": None,
            "ca_cert": None,
            "insecure": None,
            "timeout": None,
            "request_id": "airflow-request:dq_validation_run_plan:invoke_validation_run_plan:manual__1",
            "correlation_id": "airflow:dq_validation_run_plan:invoke_validation_run_plan:manual__1",
            "prefix": "DQ_AIRFLOW_",
        },
        "run_plan_id": "run-plan-1",
        "source_pipeline": "airflow",
        "scheduled_at": None,
        "wait_for_completion": True,
        "wait_timeout_seconds": 600.0,
        "poll_interval_seconds": 2.5,
    }


def test_operator_can_return_queue_payload_without_waiting(monkeypatch: pytest.MonkeyPatch) -> None:
    module = _load_operator_module(monkeypatch)
    captured: dict[str, object] = {}

    monkeypatch.setattr(module.DqValidationRunPlanOperator, "_install_sdk_wheel", lambda self: Path("/sdk/site-packages"))

    def _fake_invoke(self, sdk_site_packages: Path, payload: dict[str, object]) -> dict[str, object]:
        captured["sdk_site_packages"] = sdk_site_packages
        captured["payload"] = payload
        return {
            "run_plan_id": "run-plan-2",
            "run_plan_version_id": "run-plan-version-2",
            "run_id": "run-2",
            "queue_message_id": "queue-2",
            "status": "queued",
            "correlation_id": "corr-2",
            "replay": {"run_id": "run-2", "queue_message_id": "queue-2"},
        }

    monkeypatch.setattr(module.DqValidationRunPlanOperator, "_invoke_sdk", _fake_invoke)

    operator = module.DqValidationRunPlanOperator(
        task_id="invoke_validation_run_plan",
        run_plan_id="run-plan-2",
        base_url="https://kong.example",
        token="token-123",
        wait_for_completion=False,
    )

    payload = operator.execute({"run_id": "manual__2"})

    assert payload == {
        "run_plan_id": "run-plan-2",
        "run_plan_version_id": "run-plan-version-2",
        "run_id": "run-2",
        "queue_message_id": "queue-2",
        "status": "queued",
        "correlation_id": "corr-2",
        "replay": {"run_id": "run-2", "queue_message_id": "queue-2"},
    }
    assert captured["sdk_site_packages"] == Path("/sdk/site-packages")
    assert captured["payload"] == {
        "config": {
            "base_url": "https://kong.example",
            "token": "token-123",
            "issuer_url": None,
            "client_id": None,
            "username": None,
            "password": None,
            "ca_cert": None,
            "insecure": None,
            "timeout": None,
            "request_id": "airflow-request:dq_validation_run_plan:invoke_validation_run_plan:manual__2",
            "correlation_id": "airflow:dq_validation_run_plan:invoke_validation_run_plan:manual__2",
            "prefix": "DQ_AIRFLOW_",
        },
        "run_plan_id": "run-plan-2",
        "source_pipeline": "airflow",
        "scheduled_at": None,
        "wait_for_completion": False,
        "wait_timeout_seconds": 1800.0,
        "poll_interval_seconds": 5.0,
    }


def test_operator_requires_run_plan_id(monkeypatch: pytest.MonkeyPatch) -> None:
    module = _load_operator_module(monkeypatch)

    operator = module.DqValidationRunPlanOperator(task_id="invoke_validation_run_plan", run_plan_id="   ")

    with pytest.raises(ValueError, match="run_plan_id is required"):
        operator.execute({})