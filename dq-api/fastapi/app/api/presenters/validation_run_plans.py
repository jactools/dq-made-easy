from __future__ import annotations

from typing import Any

from app.api.v1.schemas import ValidationRunPlanView


def build_validation_run_plan_view(row: Any) -> ValidationRunPlanView:
    return ValidationRunPlanView.model_validate(row)
