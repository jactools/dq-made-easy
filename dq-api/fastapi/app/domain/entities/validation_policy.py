from __future__ import annotations

from dq_domain_validation import RuleCompilerSeverity
from app.domain.entities.base import EntityModel


class ValidationPolicyEntity(EntityModel):
    """A single configurable validation check policy."""

    checkId: str
    enabled: bool = True
    severityOverride: RuleCompilerSeverity | None = None
    scope: str = "all"
