from __future__ import annotations

import os
from datetime import datetime

from airflow.sdk import dag

from dq_airflow_operator.validation_run_plan_operator import DqValidationRunPlanOperator


def _require_env(name: str) -> str:
    value = os.environ.get(name)
    if value is None or not value.strip():
        raise RuntimeError(f"{name} is required")
    return value.strip()


def _float_env(name: str, default: float) -> float:
    value = os.environ.get(name)
    if value is None or not value.strip():
        return default
    return float(value)


def _optional_env(name: str) -> str | None:
    value = os.environ.get(name)
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


@dag(
    dag_id="dq_validation_run_plan",
    schedule=None,
    start_date=datetime(2026, 5, 30),
    catchup=False,
    tags=["dq-made-easy", "airflow", "validation-run-plan"],
    description="Invoke a dq-made-easy validation run plan with an image-owned operator and task-installed SDK wheel.",
)
def dq_validation_run_plan() -> None:
    DqValidationRunPlanOperator(
        task_id="invoke_validation_run_plan",
        run_plan_id=_optional_env("DQ_AIRFLOW_RUN_PLAN_ID") or "",
        source_pipeline=os.environ.get("DQ_AIRFLOW_SOURCE_PIPELINE", "airflow"),
        scheduled_at=os.environ.get("DQ_AIRFLOW_SCHEDULED_AT"),
        wait_for_completion=True,
        wait_timeout_seconds=_float_env("DQ_AIRFLOW_WAIT_TIMEOUT_SECONDS", 1800.0),
        poll_interval_seconds=_float_env("DQ_AIRFLOW_POLL_INTERVAL_SECONDS", 5.0),
    )


dq_validation_run_plan()