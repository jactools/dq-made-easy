from __future__ import annotations

from app.domain.interfaces.v1.rules_repository import RulesRepository
from app.infrastructure.repositories._postgres_rule_helpers import RuleHelpersMixin
from app.infrastructure.repositories._postgres_rules_read import RulesReadMixin
from app.infrastructure.repositories._postgres_rules_write import RulesWriteMixin
from app.infrastructure.repositories._postgres_rule_lifecycle import RuleLifecycleMixin
from app.infrastructure.repositories._postgres_rule_versions import RuleVersionsMixin
from app.infrastructure.repositories._postgres_rule_audit import RuleAuditMixin
from app.infrastructure.repositories._postgres_compiler_artifacts import CompilerArtifactsMixin
from app.infrastructure.repositories._postgres_reusable_parts import ReusablePartsMixin


class PostgresRulesRepository(
    RuleHelpersMixin,
    RulesReadMixin,
    RulesWriteMixin,
    RuleLifecycleMixin,
    RuleVersionsMixin,
    RuleAuditMixin,
    CompilerArtifactsMixin,
    ReusablePartsMixin,
    RulesRepository,
):
    """Postgres-backed rules repository."""

    def __init__(self, database_url: str) -> None:
        self.database_url = database_url
