from __future__ import annotations

from typing import Any

from pydantic import Field

from app.domain.entities.base import EntityModel


class ValidationRunItemEntity(EntityModel):
    id: str
    rule_id: str
    rule_name: str | None = None
    rule_version_number: int | None = None
    valid: bool
    errors: int = 0
    warnings: int = 0
    diagnostics: list[dict[str, Any]] = Field(default_factory=list)
    conflicts: list[dict[str, Any]] = Field(default_factory=list)


class ValidationRunEntity(EntityModel):
    id: str
    workspace: str | None = None
    triggered_by: str | None = None
    run_at: str
    total: int
    valid_count: int
    invalid_count: int
    status: str
    validation_items: list[ValidationRunItemEntity] = Field(default_factory=list)


class ValidationRunListEntity(EntityModel):
    data: list[ValidationRunEntity] = Field(default_factory=list)
    total: int