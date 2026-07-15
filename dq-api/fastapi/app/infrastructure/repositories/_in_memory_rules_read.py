from __future__ import annotations

from app.domain.entities import build_rule_record_entity, RuleEntity, RuleRecordEntity
from app.domain.entities import rule_policy


class InMemoryRulesReadMixin:

    async def list_rule_records(
        self,
        workspace: str | None = None,
        include_deleted: bool = False,
        is_template: bool | None = None,
        query: str | None = None,
        limit: int = 200,
        offset: int = 0,
    ) -> list[RuleRecordEntity]:
        return [
            record
            for record in (
                build_rule_record_entity(payload)
                for payload in await self._list_rule_payloads(
                    workspace=workspace,
                    include_deleted=include_deleted,
                    is_template=is_template,
                    query=query,
                    limit=limit,
                    offset=offset,
                )
            )
            if record is not None
        ]

    async def _list_rule_payloads(
        self,
        workspace: str | None = None,
        include_deleted: bool = False,
        is_template: bool | None = None,
        query: str | None = None,
        limit: int = 200,
        offset: int = 0,
    ) -> list[dict]:
        import json
        del limit, offset

        normalized_query = str(query or "").strip().lower()

        rows = []
        for rule in self._rules.values():
            if workspace and workspace != "default":
                continue
            detail = self._rule_details.get(rule.id, {})
            details = detail
            row_is_template = bool(detail.get("is_template", False))
            if is_template is True and not row_is_template:
                continue
            if is_template is False and row_is_template:
                continue

            removed_at = details.get("removed_at")
            if removed_at and not include_deleted:
                continue

            current_version = next(
                (version for version in self._rule_versions.get(rule.id, []) if version.get("id")),
                None,
            )

            rows.append(
                {
                    "id": rule.id,
                    "name": rule.name,
                    "description": rule.description,
                    "comments": details.get("comments"),
                    "expression": rule.expression,
                    "dimension": rule.dimension,
                    "active": rule.active,
                    "lifecycle_status": str(self._rule_details.get(rule.id, {}).get("lifecycle_status") or "").strip() or rule_policy.derive_rule_lifecycle_status_from_row(detail),
                    "generated": bool(self._rule_details.get(rule.id, {}).get("generated", False)),
                    "is_template": row_is_template,
                    "template_id": self._rule_details.get(rule.id, {}).get("template_id"),
                    "workspace": self._rule_details.get(rule.id, {}).get("workspace", "default"),
                    "created_by": rule.created_by_user_id,
                    "last_approval_by": None,
                    "last_approval_status": self._rule_details.get(rule.id, {}).get("last_approval_status", "approved" if rule.active else None),
                    "last_approval_at": None,
                    "removed": bool(removed_at),
                    "removed_at": removed_at,
                    "removed_by": details.get("removed_by"),
                    "deleted_on": removed_at,
                    "deleted_by": details.get("removed_by"),
                    "suggestion_id": self._rule_details.get(rule.id, {}).get("suggestion_id"),
                    "dsl": self._rule_details.get(rule.id, {}).get("dsl"),
                    "taxonomy": self._rule_details.get(rule.id, {}).get("taxonomy"),
                    "join_conditions": json.dumps(self._rule_details.get(rule.id, {}).get("join_conditions", [])),
                    "alias_mappings": json.dumps(self._rule_details.get(rule.id, {}).get("alias_mappings", {})),
                    "reusable_join_id": self._rule_details.get(rule.id, {}).get("reusable_join_id"),
                    "manual_override_by": self._rule_details.get(rule.id, {}).get("manual_override_by"),
                    "manual_override_at": self._rule_details.get(rule.id, {}).get("manual_override_at"),
                    "check_type": self._rule_details.get(rule.id, {}).get("check_type"),
                    "check_type_params": json.dumps(self._rule_details.get(rule.id, {}).get("check_type_params")) if self._rule_details.get(rule.id, {}).get("check_type_params") is not None else None,
                    "validation_status": current_version.get("validationStatus") if current_version else None,
                    "validated_at": current_version.get("validatedAt") if current_version else None,
                    "current_version_id": current_version.get("id") if current_version else None,
                    "total_versions": len(self._rule_versions.get(rule.id, [])) or 1,
                    "versioning_enabled": True,
                    "version_created_at": current_version.get("createdAt") if current_version else None,
                    "version_updated_at": current_version.get("createdAt") if current_version else None,
                    "tagIds": list(rule.tag_ids),
                    "reusableFilterIds": list(self._rule_details.get(rule.id, {}).get("reusableFilterIds", [])),
                    "reusableFilters": list(self._rule_details.get(rule.id, {}).get("reusableFilters", [])),
                }
            )

        if normalized_query:
            rows = [
                row
                for row in rows
                if normalized_query in str(row.get("id") or "").lower()
                or normalized_query in str(row.get("name") or "").lower()
                or normalized_query in str(row.get("description") or "").lower()
                or normalized_query in str(row.get("expression") or "").lower()
            ]

        return sorted(
            rows,
            key=lambda row: (
                str(row.get("version_updated_at") or ""),
                str(row.get("id") or ""),
            ),
            reverse=True,
        )

    async def get_rule_by_id(self, rule_id: str) -> RuleEntity | None:
        from copy import deepcopy
        current = self._rules.get(rule_id)
        if current is None:
            return None
        details = self._rule_details.get(rule_id, {})
        if details.get("removed_at"):
            return None
        return RuleEntity(
            id=current.id,
            name=current.name,
            description=current.description,
            comments=str(details.get("comments") or "").strip() or None,
            expression=current.expression,
            dimension=current.dimension,
            active=current.active,
            lifecycle_status=str(details.get("lifecycle_status") or "").strip() or rule_policy.derive_rule_lifecycle_status_from_row(details),
            workspace=str(details.get("workspace") or "").strip() or None,
            createdByUserId=current.created_by_user_id,
            tagIds=list(current.tag_ids),
            manual_override_by=str(details.get("manual_override_by") or "").strip() or None,
            manual_override_at=str(details.get("manual_override_at") or "").strip() or None,
            checkType=str(details.get("check_type") or "").strip() or None,
            checkTypeParams=deepcopy(details.get("check_type_params")) if isinstance(details.get("check_type_params"), dict) else None,
            reusableJoinId=str(details.get("reusable_join_id") or "").strip() or None,
            reusableFilterIds=[
                str(item).strip()
                for item in (details.get("reusableFilterIds") if isinstance(details.get("reusableFilterIds"), list) else [])
                if str(item).strip()
            ],
            dsl=deepcopy(details.get("dsl")) if isinstance(details.get("dsl"), dict) else None,
            taxonomy=deepcopy(details.get("taxonomy")) if isinstance(details.get("taxonomy"), dict) else {},
        )
