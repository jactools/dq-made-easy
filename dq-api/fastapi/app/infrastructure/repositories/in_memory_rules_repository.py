from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime

from app.domain.entities import RuleCreatorEntity, RuleEntity, RuleTagEntity
from app.domain.interfaces import RulesRepository
from app.infrastructure.repositories.in_memory_test_data import rules_seed_data
from app.infrastructure.repositories._in_memory_rule_helpers import InMemoryRuleHelpersMixin
from app.infrastructure.repositories._in_memory_rules_read import InMemoryRulesReadMixin
from app.infrastructure.repositories._in_memory_rules_write import InMemoryRulesWriteMixin
from app.infrastructure.repositories._in_memory_rule_lifecycle import InMemoryRuleLifecycleMixin
from app.infrastructure.repositories._in_memory_rule_versions import InMemoryRuleVersionsMixin
from app.infrastructure.repositories._in_memory_rule_audit import InMemoryRuleAuditMixin
from app.infrastructure.repositories._in_memory_compiler_artifacts import InMemoryCompilerArtifactsMixin
from app.infrastructure.repositories._in_memory_reusable_parts import InMemoryReusablePartsMixin


class InMemoryRulesRepository(
    InMemoryRuleHelpersMixin,
    InMemoryRulesReadMixin,
    InMemoryRulesWriteMixin,
    InMemoryRuleLifecycleMixin,
    InMemoryRuleVersionsMixin,
    InMemoryRuleAuditMixin,
    InMemoryCompilerArtifactsMixin,
    InMemoryReusablePartsMixin,
    RulesRepository,
):
    def __init__(self) -> None:
        seed = rules_seed_data()
        self._rules = {
            rule_id: RuleEntity(**rule)
            for rule_id, rule in seed["rules"].items()
        }
        self._users = {
            user_id: RuleCreatorEntity(**user)
            for user_id, user in seed["users"].items()
        }
        self._tags = {
            tag_id: RuleTagEntity(**tag)
            for tag_id, tag in seed["tags"].items()
        }
        self._rule_versions = seed["rule_versions"]
        self._rollback_history = seed["rollback_history"]
        self._status_history = seed.get("status_history", {})
        self._reusable_filters: dict[str, dict] = {}
        self._reusable_joins: dict[str, dict] = {}
        self._compiler_artifacts_by_version: dict[str, list[dict]] = {}
        self._rule_details: dict[str, dict] = {
            rule_id: {
                "workspace": "default",
                "lifecycle_status": "active",
                "generated": False,
                "is_template": False,
                "template_id": None,
                "suggestion_id": None,
                "comments": None,
                "dsl": None,
                "taxonomy": None,
                "join_conditions": [],
                "alias_mappings": {},
                "reusable_join_id": None,
                "manual_override_by": None,
                "manual_override_at": None,
                "reusableFilterIds": [],
                "reusableFilters": [],
            }
            for rule_id in self._rules
        }
