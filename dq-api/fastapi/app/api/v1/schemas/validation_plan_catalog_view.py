from __future__ import annotations

from typing import Any

from pydantic import Field

from app.api.v1.schemas.validation_run_plan_view import ValidationRunPlanScheduleDefinitionView
from app.api.v1.schemas.validation_run_plan_view import ValidationRunPlanView
from app.schemas.pydantic_base import SnakeModel


class ValidationPlanCatalogSuiteView(SnakeModel):
    runPlanId: str
    runPlanVersionId: str
    governanceState: str
    artifactId: str | None = None
    artifactVersion: int | None = None
    engineType: str | None = None
    tagIds: list[str] = Field(default_factory=list)
    scheduleDefinition: ValidationRunPlanScheduleDefinitionView = Field(default_factory=ValidationRunPlanScheduleDefinitionView)
    artifactSnapshot: dict[str, Any] | None = None
    createdAt: str


class ValidationPlanCatalogSummaryView(SnakeModel):
    runPlanCount: int = 0
    suiteCount: int = 0
    engineTypes: list[str] = Field(default_factory=list)


class ValidationPlanCatalogView(SnakeModel):
    validationRunPlans: list[ValidationRunPlanView] = Field(default_factory=list)
    validationSuites: list[ValidationPlanCatalogSuiteView] = Field(default_factory=list)
    validationSummary: ValidationPlanCatalogSummaryView = Field(default_factory=ValidationPlanCatalogSummaryView)
