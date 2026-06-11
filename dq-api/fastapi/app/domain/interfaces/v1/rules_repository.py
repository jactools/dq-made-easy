from typing import Any, Protocol
from datetime import datetime

from app.domain.entities import RuleCreatorEntity, RuleEntity, RuleRecordEntity, RuleTagEntity


class RulesRepository(Protocol):
    async def list_rule_records(
        self,
        workspace: str | None = None,
        include_deleted: bool = False,
        is_template: bool | None = None,
        query: str | None = None,
        limit: int = 200,
        offset: int = 0,
    ) -> list[RuleRecordEntity]:
        ...

    async def get_rule_by_id(self, rule_id: str) -> RuleEntity | None:
        ...

    async def create_rule_record(
        self,
        *,
        name: str,
        description: str | None,
        comments: str | None = None,
        expression: str,
        dimension: str,
        active: bool,
        workspace: str,
        created_by: str,
        generated: bool,
        is_template: bool,
        template_id: str | None,
        suggestion_id: str | None,
        dsl: dict | None,
        join_conditions: list[dict],
        alias_mappings: dict,
        reusable_join_id: str | None,
        reusable_filter_ids: list[str],
        manual_override_by: str | None,
        manual_override_at: datetime | None,
        check_type: str | None,
        check_type_params: dict | None,
        taxonomy: dict | None,
    ) -> RuleRecordEntity:
        ...

    async def update_rule_record(
        self,
        *,
        rule_id: str,
        name: str,
        description: str | None,
        comments: str | None = None,
        expression: str,
        dimension: str,
        active: bool,
        dsl: dict | None,
        join_conditions: list[dict],
        alias_mappings: dict,
        reusable_join_id: str | None,
        reusable_filter_ids: list[str],
        manual_override_by: str | None,
        manual_override_at: datetime | None,
        check_type: str | None,
        check_type_params: dict | None,
        taxonomy: dict | None,
    ) -> RuleRecordEntity | None:
        ...

    async def activate_rule_record(self, rule_id: str) -> RuleRecordEntity | None:
        ...

    async def set_rule_lifecycle_status(
        self,
        rule_id: str,
        *,
        lifecycle_status: str,
        changed_by: str | None,
        reason: str | None = None,
    ) -> RuleRecordEntity | None:
        ...

    async def deactivate_rule(self, rule_id: str) -> dict | None:
        ...

    async def soft_delete_rule_record(self, rule_id: str, *, removed_by: str) -> RuleRecordEntity | None:
        ...

    async def recover_rule(self, rule_id: str, *, recovered_by: str) -> dict | None:
        ...

    async def save_rule_as_template(
        self,
        *,
        rule_id: str,
        template_name: str,
        template_description: str | None,
        created_by: str,
    ) -> dict | None:
        ...

    async def list_rule_versions(self, rule_id: str, limit: int = 20, offset: int = 0) -> dict | None:
        ...

    async def get_rule_version(self, rule_id: str, version_id: str) -> dict | None:
        ...

    async def get_rule_rollback_history(
        self,
        rule_id: str,
        limit: int = 10,
        offset: int = 0,
    ) -> dict | None:
        ...

    async def list_rule_status_history(
        self,
        rule_id: str,
        limit: int = 100,
        offset: int = 0,
    ) -> list[dict] | None:
        ...

    async def record_rule_audit_event(
        self,
        rule_id: str,
        *,
        action: str,
        from_status: str | None = None,
        to_status: str | None = None,
        changed_by: str | None = None,
        reason: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> dict | None:
        ...

    async def record_rule_status_transition(
        self,
        rule_id: str,
        from_status: str | None,
        to_status: str,
        changed_by: str | None = None,
        reason: str | None = None,
    ) -> dict | None:
        ...

    async def compare_rule_versions(
        self,
        rule_id: str,
        version_1: str,
        version_2: str,
    ) -> dict | None:
        ...

    async def get_rule_version_statistics(self, rule_id: str) -> dict | None:
        ...

    async def execute_rule_rollback(
        self,
        rule_id: str,
        to_version_id: str,
        reason: str,
        requested_by_user_id: str | None = None,
        skip_approval: bool = False,
        tags: list[str] | None = None,
    ) -> dict | None:
        ...

    async def update_rule_version_tags(
        self,
        rule_id: str,
        version_id: str,
        tags: list[str],
        updated_by_user_id: str | None = None,
    ) -> dict | None:
        ...

    async def mark_rule_version_for_rollback(
        self,
        rule_id: str,
        version_id: str,
        marked: bool,
    ) -> dict | None:
        ...

    async def set_current_rule_version_validation(
        self,
        *,
        rule_id: str,
        validation_status: str,
        validated_by: str | None,
    ) -> dict | None:
        ...

    async def upsert_active_compiler_artifact(
        self,
        *,
        rule_version_id: str,
        compiler_version: str,
        artifact_key: str,
        artifact_payload: dict,
        diagnostics_payload: list[dict],
        compile_status: str,
        source_fingerprint: str,
    ) -> dict:
        ...

    async def get_active_compiler_artifact(self, rule_version_id: str) -> dict | None:
        ...

    async def list_compiler_artifacts(self, rule_version_id: str) -> list[dict]:
        ...

    async def get_user_by_id(self, user_id: str) -> RuleCreatorEntity | None:
        ...

    async def get_tags_by_ids(self, tag_ids: list[str]) -> list[RuleTagEntity]:
        ...

    async def list_reusable_filters(self, workspace: str | None = None, query: str | None = None) -> list[dict]:
        ...

    async def create_reusable_filter(
        self,
        *,
        name: str,
        expression: str,
        description: str | None,
        workspace: str,
        created_by: str,
        active: bool,
    ) -> dict:
        ...

    async def delete_reusable_filter(self, filter_id: str) -> bool:
        ...

    async def get_reusable_filter(self, filter_id: str) -> dict | None:
        ...

    async def update_reusable_filter(
        self,
        *,
        filter_id: str,
        name: str,
        expression: str,
        description: str | None,
        active: bool,
    ) -> dict | None:
        ...

    async def list_reusable_joins(self, workspace: str | None = None) -> list[dict]:
        ...

    async def create_reusable_join(
        self,
        *,
        name: str,
        join_definition: str,
        description: str | None,
        workspace: str,
        created_by: str,
        active: bool,
    ) -> dict:
        ...

    async def delete_reusable_join(self, join_id: str) -> bool:
        ...

    async def get_reusable_join(self, join_id: str) -> dict | None:
        ...

    async def update_reusable_join(
        self,
        *,
        join_id: str,
        name: str,
        join_definition: str,
        description: str | None,
        active: bool,
    ) -> dict | None:
        ...
