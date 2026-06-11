from copy import deepcopy
from datetime import UTC, datetime, timedelta
import json
from uuid import uuid4
from typing import Any

from app.domain.entities import build_rule_record_entity, RuleCreatorEntity, RuleEntity, RuleRecordEntity, RuleTagEntity
from app.domain.entities import rule_policy
from app.domain.status_governance import canonicalize_status
from app.domain.status_governance import is_transition_defined
from app.domain.interfaces import RulesRepository
from app.infrastructure.repositories.in_memory_test_data import rules_seed_data


class InMemoryRulesRepository(RulesRepository):
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
                    "dsl": deepcopy(self._rule_details.get(rule.id, {}).get("dsl")),
                    "taxonomy": deepcopy(self._rule_details.get(rule.id, {}).get("taxonomy")),
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

    async def _create_rule_payload(
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
    ) -> dict:
        rule_id = f"rule-{uuid4().hex[:10]}"
        creator_id = created_by if created_by in self._users else "user-admin"
        created_at = datetime.now(UTC).isoformat().replace("+00:00", "Z")
        initial_version_id = "rv-001"

        self._rules[rule_id] = RuleEntity(
            id=rule_id,
            name=name,
            description=description,
            comments=comments,
            expression=expression,
            dimension=dimension,
            active=active,
            createdByUserId=creator_id,
            tagIds=[],
        )

        self._rule_details[rule_id] = {
            "workspace": workspace,
            "lifecycle_status": "active",
            "generated": bool(generated),
            "is_template": bool(is_template),
            "template_id": template_id,
            "suggestion_id": suggestion_id,
            "dsl": deepcopy(dsl) if dsl is not None else None,
            "taxonomy": deepcopy(taxonomy) if taxonomy is not None else None,
            "join_conditions": join_conditions,
            "alias_mappings": alias_mappings,
            "reusable_join_id": reusable_join_id,
            "manual_override_by": manual_override_by,
            "manual_override_at": manual_override_at.isoformat() if manual_override_at else None,
            "check_type": check_type,
            "check_type_params": check_type_params,
            "reusableFilterIds": list(reusable_filter_ids),
            "reusableFilters": [],
        }
        self._rule_versions[rule_id] = [
            {
                "id": initial_version_id,
                "ruleId": rule_id,
                "versionNumber": 1,
                "createdAt": created_at,
                "createdBy": {
                    "id": creator_id,
                    "name": self._users[creator_id].display_name,
                    "email": "admin@example.com",
                },
                "changeType": "created",
                "changeDescription": "Rule created",
                "markedForRollback": False,
                "tags": [],
                "rule": {
                    "name": name,
                    "description": description,
                    "comments": comments,
                    "expression": expression,
                    "dimension": dimension,
                    "active": bool(active),
                    "dsl": deepcopy(dsl) if dsl is not None else None,
                    "taxonomy": deepcopy(taxonomy) if taxonomy is not None else None,
                    "checkType": check_type,
                    "checkTypeParams": deepcopy(check_type_params) if check_type_params is not None else None,
                },
                "relationships": {
                    "approvals": [],
                    "testProofs": [],
                },
                "validationStatus": None,
                "validatedAt": None,
                "validatedBy": None,
                "validatedByUserId": None,
            }
        ]

        self._record_status_transition(
            rule_id=rule_id,
            from_status=None,
            action="create",
            to_status="activated" if bool(active) else "draft",
            changed_by=creator_id,
            reason="Rule created",
            allow_same_status=True,
        )

        rows = await self._list_rule_payloads(workspace=workspace)
        return next((row for row in rows if row["id"] == rule_id), rows[-1])

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
        payload = await self._create_rule_payload(
            name=name,
            description=description,
            comments=comments,
            expression=expression,
            dimension=dimension,
            active=active,
            workspace=workspace,
            created_by=created_by,
            generated=generated,
            is_template=is_template,
            template_id=template_id,
            suggestion_id=suggestion_id,
            dsl=dsl,
            join_conditions=join_conditions,
            alias_mappings=alias_mappings,
            reusable_join_id=reusable_join_id,
            reusable_filter_ids=reusable_filter_ids,
            manual_override_by=manual_override_by,
            manual_override_at=manual_override_at,
            check_type=check_type,
            check_type_params=check_type_params,
            taxonomy=taxonomy,
        )
        record = build_rule_record_entity(payload)
        if record is None:
            raise ValueError("Created rule payload is invalid")
        return record

    async def _update_rule_payload(
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
    ) -> dict | None:
        current = self._rules.get(rule_id)
        if current is None:
            return None

        from_status = self._current_rule_status(rule_id)
        desired_status = from_status
        if from_status == "deactivated":
            desired_status = "draft"
        if bool(active) and not bool(current.active):
            desired_status = "activated"
        elif not bool(active) and bool(current.active):
            desired_status = "deactivated"

        self._ensure_rule_transition_allowed(from_status=from_status, to_status=desired_status)

        rows = self._rule_versions.setdefault(rule_id, [])
        new_version_number = max((int(row.get("versionNumber", 0)) for row in rows), default=0) + 1
        new_version_id = f"rv-{new_version_number:03d}"
        created_at = datetime.now(UTC).isoformat().replace("+00:00", "Z")

        new_version_row = {
            "id": new_version_id,
            "ruleId": rule_id,
            "versionNumber": new_version_number,
            "createdAt": created_at,
            "createdBy": {
                "id": current.created_by_user_id,
                "name": self._users[current.created_by_user_id].display_name if current.created_by_user_id in self._users else current.created_by_user_id,
                "email": "admin@example.com",
            },
            "changeType": "modified",
            "changeDescription": "Rule updated",
            "markedForRollback": False,
            "tags": list(current.tag_ids),
            "rule": {
                "name": name,
                "description": description,
                "comments": comments,
                "expression": expression,
                "dimension": dimension,
                "active": bool(active),
                "dsl": deepcopy(dsl) if dsl is not None else None,
                "taxonomy": deepcopy(taxonomy) if taxonomy is not None else None,
                "checkType": check_type,
                "checkTypeParams": deepcopy(check_type_params) if check_type_params is not None else None,
            },
            "relationships": {
                "approvals": [],
                "testProofs": [],
            },
            "validationStatus": None,
            "validatedAt": None,
            "validatedBy": None,
            "validatedByUserId": None,
        }
        rows.insert(0, new_version_row)

        details = self._rule_details.setdefault(rule_id, {})

        self._rules[rule_id] = RuleEntity(
            id=rule_id,
            name=name,
            description=description,
            comments=comments,
            expression=expression,
            dimension=dimension,
            active=active,
            lifecycle_status=str(details.get("lifecycle_status") or "").strip() or "active",
            createdByUserId=current.created_by_user_id,
            tagIds=list(current.tag_ids),
        )
        details["dsl"] = deepcopy(dsl) if dsl is not None else None
        details["taxonomy"] = deepcopy(taxonomy) if taxonomy is not None else None
        details["comments"] = comments
        details["join_conditions"] = join_conditions
        details["alias_mappings"] = alias_mappings
        details["reusable_join_id"] = reusable_join_id
        details["manual_override_by"] = manual_override_by
        details["manual_override_at"] = manual_override_at.isoformat() if manual_override_at else None
        details["check_type"] = check_type
        details["check_type_params"] = check_type_params
        details["validation_status"] = None
        details["validated_at"] = None
        details["validated_by"] = None
        if from_status == "deactivated":
            details["last_approval_status"] = "draft"
        details["reusableFilterIds"] = list(reusable_filter_ids)
        details["reusableFilters"] = []

        to_status = self._current_rule_status(rule_id)
        self._record_status_transition(
            rule_id=rule_id,
            action="edit",
            from_status=from_status,
            to_status=to_status,
            changed_by=current.created_by_user_id,
            reason="Rule updated",
            allow_same_status=True,
        )

        rows = await self._list_rule_payloads(workspace=str(details.get("workspace") or "default"))
        return next((row for row in rows if row["id"] == rule_id), None)

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
        payload = await self._update_rule_payload(
            rule_id=rule_id,
            name=name,
            description=description,
            comments=comments,
            expression=expression,
            dimension=dimension,
            active=active,
            dsl=dsl,
            join_conditions=join_conditions,
            alias_mappings=alias_mappings,
            reusable_join_id=reusable_join_id,
            reusable_filter_ids=reusable_filter_ids,
            manual_override_by=manual_override_by,
            manual_override_at=manual_override_at,
            check_type=check_type,
            check_type_params=check_type_params,
            taxonomy=taxonomy,
        )
        return build_rule_record_entity(payload)

    async def _activate_rule_payload(self, rule_id: str) -> dict | None:
        current = self._rules.get(rule_id)
        if current is None:
            return None

        from_status = self._current_rule_status(rule_id)
        self._ensure_rule_transition_allowed(from_status=from_status, to_status="activated")

        self._rules[rule_id] = RuleEntity(
            id=rule_id,
            name=current.name,
            description=current.description,
            comments=str(details.get("comments") or "").strip() or None,
            expression=current.expression,
            dimension=current.dimension,
            active=True,
            createdByUserId=current.created_by_user_id,
            tagIds=list(current.tag_ids),
        )

        details = self._rule_details.setdefault(rule_id, {})
        details["validation_status"] = "valid"
        details["last_approval_status"] = "approved"
        self._record_status_transition(
            rule_id=rule_id,
            action="activate",
            from_status=from_status,
            to_status="activated",
            changed_by=current.created_by_user_id,
            reason="Rule activated",
        )
        rows = await self._list_rule_payloads(workspace=str(details.get("workspace") or "default"))
        updated = next((row for row in rows if row["id"] == rule_id), None)
        return updated if updated is not None else {"id": rule_id, "active": True}

    async def activate_rule_record(self, rule_id: str) -> RuleRecordEntity | None:
        payload = await self._activate_rule_payload(rule_id)
        return build_rule_record_entity(payload)

    async def set_rule_lifecycle_status(
        self,
        rule_id: str,
        *,
        lifecycle_status: str,
        changed_by: str | None,
        reason: str | None = None,
    ) -> RuleRecordEntity | None:
        current = self._rules.get(rule_id)
        if current is None:
            return None

        details = self._rule_details.setdefault(rule_id, {})
        if details.get("removed_at"):
            return None

        current_lifecycle_status = str(details.get("lifecycle_status") or "").strip() or rule_policy.derive_rule_lifecycle_status_from_row(details)
        target_lifecycle_status = self._normalize_rule_lifecycle_status(lifecycle_status)
        if not target_lifecycle_status:
            raise ValueError("Lifecycle status is required")
        if target_lifecycle_status == "retired" and current.active:
            raise ValueError("Active rules must be deactivated before they can be retired")

        self._ensure_rule_lifecycle_transition_allowed(
            from_status=current_lifecycle_status,
            to_status=target_lifecycle_status,
        )

        details["lifecycle_status"] = target_lifecycle_status
        if self._rule_versions.get(rule_id):
            self._rule_versions[rule_id][0].setdefault("rule", {})["lifecycleStatus"] = target_lifecycle_status
        self._record_status_transition(
            rule_id=rule_id,
            action=self._rule_lifecycle_action(target_lifecycle_status),
            from_status=current_lifecycle_status,
            to_status=target_lifecycle_status,
            changed_by=changed_by,
            reason=reason or f"Lifecycle status set to {target_lifecycle_status}",
        )
        rows = await self._list_rule_payloads(workspace=str(details.get("workspace") or "default"))
        updated = next((row for row in rows if row["id"] == rule_id), None)
        return build_rule_record_entity(updated) if updated is not None else None

    async def deactivate_rule(self, rule_id: str) -> dict | None:
        current = self._rules.get(rule_id)
        if current is None:
            return None

        from_status = self._current_rule_status(rule_id)
        self._ensure_rule_transition_allowed(from_status=from_status, to_status="deactivated")

        self._rules[rule_id] = RuleEntity(
            id=rule_id,
            name=current.name,
            description=current.description,
            expression=current.expression,
            dimension=current.dimension,
            active=False,
            createdByUserId=current.created_by_user_id,
            tagIds=list(current.tag_ids),
        )

        details = self._rule_details.setdefault(rule_id, {})
        details["last_approval_status"] = "deactivated"
        self._record_status_transition(
            rule_id=rule_id,
            action="deactivate",
            from_status=from_status,
            to_status="deactivated",
            changed_by=current.created_by_user_id,
            reason="Rule deactivated",
        )
        rows = await self._list_rule_payloads(workspace=str(details.get("workspace") or "default"))
        updated = next((row for row in rows if row["id"] == rule_id), None)
        return updated if updated is not None else {"id": rule_id, "active": False, "last_approval_status": "deactivated"}

    async def _soft_delete_rule_payload(self, rule_id: str, *, removed_by: str) -> dict | None:
        current = self._rules.get(rule_id)
        if current is None:
            return None

        details = self._rule_details.setdefault(rule_id, {})
        if details.get("removed_at"):
            raise ValueError("Rule is already removed")

        if bool(current.active):
            raise ValueError("Rule must be deactivated before it can be removed")

        normalized_status = str(details.get("last_approval_status") or "").strip().lower().replace("_", "-")
        if normalized_status != "deactivated":
            raise ValueError("Rule must be in deactivated status before it can be removed")

        from_status = self._current_rule_status(rule_id)
        self._ensure_rule_transition_allowed(from_status=from_status, to_status="removed")
        now = datetime.now(UTC).isoformat()
        details["removed_at"] = now
        details["removed_by"] = removed_by
        details["last_approval_status"] = "removed"
        self._record_status_transition(
            rule_id=rule_id,
            action="remove",
            from_status=from_status,
            to_status="removed",
            changed_by=removed_by,
            reason="Rule removed",
        )

        rows = await self._list_rule_payloads(
            workspace=str(details.get("workspace") or "default"),
            include_deleted=True,
        )
        updated = next((row for row in rows if row["id"] == rule_id), None)
        if updated is None:
            return {
                "id": rule_id,
                "removed": True,
                "removed_at": now,
                "removed_by": removed_by,
                "last_approval_status": "removed",
                "ok": True,
            }
        updated["ok"] = True
        return updated

    async def soft_delete_rule_record(self, rule_id: str, *, removed_by: str) -> RuleRecordEntity | None:
        payload = await self._soft_delete_rule_payload(rule_id, removed_by=removed_by)
        return build_rule_record_entity(payload)

    async def recover_rule(self, rule_id: str, *, recovered_by: str) -> dict | None:
        current = self._rules.get(rule_id)
        if current is None:
            return None

        details = self._rule_details.setdefault(rule_id, {})
        if not details.get("removed_at"):
            raise ValueError("Rule is not removed")

        from_status = self._current_rule_status(rule_id)
        self._ensure_rule_transition_allowed(from_status=from_status, to_status="recovered")
        details["removed_at"] = None
        details["removed_by"] = None
        details["last_approval_status"] = "recovered"

        self._rules[rule_id] = RuleEntity(
            id=rule_id,
            name=current.name,
            description=current.description,
            expression=current.expression,
            dimension=current.dimension,
            active=False,
            createdByUserId=current.created_by_user_id,
            tagIds=list(current.tag_ids),
        )

        self._record_status_transition(
            rule_id=rule_id,
            action="recover",
            from_status=from_status,
            to_status="recovered",
            changed_by=recovered_by,
            reason="Rule recovered",
        )

        rows = await self._list_rule_payloads(workspace=str(details.get("workspace") or "default"))
        updated = next((row for row in rows if row["id"] == rule_id), None)
        if updated is None:
            return {
                "id": rule_id,
                "active": False,
                "removed": False,
                "last_approval_status": "recovered",
                "ok": True,
            }
        updated["ok"] = True
        return updated

    async def save_rule_as_template(
        self,
        *,
        rule_id: str,
        template_name: str,
        template_description: str | None,
        created_by: str,
    ) -> dict | None:
        source = self._rules.get(rule_id)
        if source is None:
            return None

        creator_id = created_by if created_by in self._users else "user-admin"
        template_id = f"tmpl-{uuid4().hex[:10]}"
        self._rules[template_id] = RuleEntity(
            id=template_id,
            name=template_name,
            description=template_description,
            expression=source.expression,
            dimension=source.dimension,
            active=False,
            createdByUserId=creator_id,
            tagIds=list(source.tag_ids),
        )
        source_detail = self._rule_details.get(rule_id, {})
        self._rule_details[template_id] = {
            "workspace": source_detail.get("workspace", "default"),
            "generated": False,
            "is_template": True,
            "template_id": rule_id,
            "suggestion_id": None,
            "dsl": deepcopy(source_detail.get("dsl")) if isinstance(source_detail.get("dsl"), dict) else None,
            "taxonomy": deepcopy(source_detail.get("taxonomy")) if isinstance(source_detail.get("taxonomy"), dict) else None,
            "join_conditions": source_detail.get("join_conditions", []),
            "alias_mappings": source_detail.get("alias_mappings", {}),
            "reusable_join_id": source_detail.get("reusable_join_id"),
            "manual_override_by": source_detail.get("manual_override_by"),
            "manual_override_at": source_detail.get("manual_override_at"),
            "reusableFilterIds": list(source_detail.get("reusableFilterIds", [])),
            "reusableFilters": list(source_detail.get("reusableFilters", [])),
        }

        self._record_status_transition(
            rule_id=template_id,
            action="create",
            from_status=None,
            to_status="draft",
            changed_by=creator_id,
            reason="Template created",
            allow_same_status=True,
        )

        rows = await self._list_rule_payloads(workspace=str(source_detail.get("workspace") or "default"))
        created = next((row for row in rows if row["id"] == template_id), None)
        if created is None:
            return {"id": template_id, "ok": True}
        created["ok"] = True
        return created

    async def list_rule_versions(self, rule_id: str, limit: int = 20, offset: int = 0) -> dict | None:
        if rule_id not in self._rules:
            return None

        rows = self._rule_versions.get(rule_id, [])
        safe_limit = max(1, min(100, limit))
        safe_offset = max(0, offset)
        window = rows[safe_offset : safe_offset + safe_limit]

        return {
            "ruleId": rule_id,
            "ruleName": self._rules[rule_id].name,
            "versioning": {
                "enabled": True,
                "currentVersion": rows[0]["versionNumber"] if rows else 0,
                "totalVersions": len(rows),
            },
            "pagination": {
                "limit": safe_limit,
                "offset": safe_offset,
                "total": len(rows),
                "hasMore": safe_offset + safe_limit < len(rows),
            },
            "versions": [
                {
                    "id": row["id"],
                    "versionNumber": row["versionNumber"],
                    "createdAt": row["createdAt"],
                    "createdBy": row["createdBy"],
                    "changeType": row["changeType"],
                    "changeDescription": row["changeDescription"],
                    "markedForRollback": bool(row.get("markedForRollback", False)),
                    "tags": row["tags"],
                    "isCurrentVersion": idx == 0,
                    "validationStatus": row.get("validationStatus"),
                    "validatedAt": row.get("validatedAt"),
                    "validatedBy": row.get("validatedBy", ""),
                    "validatedByUserId": row.get("validatedByUserId"),
                }
                for idx, row in enumerate(window)
            ],
        }

    async def get_rule_version(self, rule_id: str, version_id: str) -> dict | None:
        rows = self._rule_versions.get(rule_id)
        if not rows:
            return None

        for row in rows:
            if row["id"] == version_id:
                row.setdefault("validationStatus", None)
                row.setdefault("validatedAt", None)
                row.setdefault("validatedBy", "")
                row.setdefault("validatedByUserId", None)
                return row
        return None

    async def get_rule_rollback_history(
        self,
        rule_id: str,
        limit: int = 10,
        offset: int = 0,
    ) -> dict | None:
        if rule_id not in self._rules:
            return None

        rows = self._rollback_history.get(rule_id, [])
        safe_limit = max(1, min(100, limit))
        safe_offset = max(0, offset)
        window = rows[safe_offset : safe_offset + safe_limit]

        return {
            "ruleId": rule_id,
            "rollbacks": window,
            "pagination": {
                "limit": safe_limit,
                "offset": safe_offset,
                "total": len(rows),
                "hasMore": safe_offset + safe_limit < len(rows),
            },
        }

    async def list_rule_status_history(self, rule_id: str, limit: int = 100, offset: int = 0) -> list[dict] | None:
        if rule_id not in self._rules:
            return None

        # Return newest-first to match the API contract and other repositories.
        rows = list(reversed(self._status_history.get(rule_id, [])))
        safe_limit = max(1, min(100, limit))
        safe_offset = max(0, offset)
        window = rows[safe_offset : safe_offset + safe_limit]
        return [deepcopy(row) for row in window]

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
        if rule_id not in self._rules:
            return None

        row = self._record_status_transition(
            rule_id=rule_id,
            action=action,
            from_status=from_status,
            to_status=to_status or self._current_rule_status(rule_id),
            changed_by=changed_by,
            reason=reason,
            details=details,
            allow_same_status=True,
        )
        return deepcopy(row) if row is not None else None

    async def record_rule_status_transition(
        self,
        rule_id: str,
        from_status: str | None,
        to_status: str,
        changed_by: str | None = None,
        reason: str | None = None,
    ) -> dict | None:
        if rule_id not in self._rules:
            return None

        self._ensure_rule_transition_allowed(from_status=from_status, to_status=to_status)

        normalized_to = self._normalize_rule_status(to_status)
        if normalized_to:
            details = self._rule_details.setdefault(rule_id, {})
            details["last_approval_status"] = normalized_to
            details["last_approval_by"] = str(changed_by or "").strip() or None

        row = self._record_status_transition(
            rule_id=rule_id,
            action=self._infer_rule_transition_action(normalized_to),
            from_status=from_status,
            to_status=to_status,
            changed_by=changed_by,
            reason=reason,
        )
        return deepcopy(row) if row is not None else None

    async def compare_rule_versions(
        self,
        rule_id: str,
        version_1: str,
        version_2: str,
    ) -> dict | None:
        if rule_id not in self._rules:
            return None

        rows = self._rule_versions.get(rule_id, [])
        first = next((row for row in rows if row["id"] == version_1), None)
        second = next((row for row in rows if row["id"] == version_2), None)
        if first is None or second is None:
            return None

        details: list[dict] = []

        for field in ("name", "description", "expression", "dimension", "active"):
            old_value = first["rule"].get(field)
            new_value = second["rule"].get(field)
            if old_value != new_value:
                details.append(
                    {
                        "field": field,
                        "oldValue": old_value,
                        "newValue": new_value,
                        "changeType": "modified",
                    }
                )

        old_tags = sorted(first.get("tags", []))
        new_tags = sorted(second.get("tags", []))
        if old_tags != new_tags:
            details.append(
                {
                    "field": "tags",
                    "oldValue": old_tags,
                    "newValue": new_tags,
                    "changeType": "modified",
                }
            )

        return {
            "fromVersion": {
                "id": first["id"],
                "versionNumber": first["versionNumber"],
                "createdAt": first["createdAt"],
                "createdBy": first["createdBy"]["name"],
            },
            "toVersion": {
                "id": second["id"],
                "versionNumber": second["versionNumber"],
                "createdAt": second["createdAt"],
                "createdBy": second["createdBy"]["name"],
            },
            "changes": {
                "summary": {
                    "fieldsChanged": len(details),
                    "totalChanges": len(details),
                },
                "details": details,
            },
        }

    async def get_rule_version_statistics(self, rule_id: str) -> dict | None:
        if rule_id not in self._rules:
            return None

        rows = self._rule_versions.get(rule_id, [])
        rollback_rows = self._rollback_history.get(rule_id, [])

        change_types: dict[str, int] = {}
        active_count = 0
        rollback_targets: dict[str, int] = {}
        testing_rows: list[dict] = []

        for row in rows:
            change_type = str(row.get("changeType", "unknown"))
            change_types[change_type] = change_types.get(change_type, 0) + 1

            if bool(row.get("rule", {}).get("active", False)):
                active_count += 1

            testing_rows.append(
                {
                    "versionId": row["id"],
                    "versionNumber": row["versionNumber"],
                    "testCount": 0,
                    "passedTests": 0,
                    "avgCoverage": None,
                }
            )

        for rb in rollback_rows:
            target_version = str(rb.get("toVersionNumber", ""))
            if target_version:
                rollback_targets[target_version] = rollback_targets.get(target_version, 0) + 1

        return {
            "versions": {
                "total": len(rows),
                "active": active_count,
                "markedForRollback": 0,
                "changeTypes": change_types,
            },
            "testing": testing_rows,
            "rollbacks": {
                "total": len(rollback_rows),
                "rollbackTargets": rollback_targets,
            },
        }

    async def execute_rule_rollback(
        self,
        rule_id: str,
        to_version_id: str,
        reason: str,
        requested_by_user_id: str | None = None,
        skip_approval: bool = False,
        tags: list[str] | None = None,
    ) -> dict | None:
        if rule_id not in self._rules:
            return None

        rows = self._rule_versions.get(rule_id, [])
        if not rows:
            raise LookupError(f"No versions found for rule '{rule_id}'")

        current = rows[0]
        if current["id"] == to_version_id:
            raise ValueError("Cannot rollback to the current version")

        target = next((row for row in rows if row["id"] == to_version_id), None)
        if target is None:
            raise LookupError(f"Version '{to_version_id}' not found for rule '{rule_id}'")

        now = datetime.now(UTC)
        rolled_back_at = now.isoformat().replace("+00:00", "Z")
        estimated_completion = (now + timedelta(seconds=30)).isoformat().replace("+00:00", "Z")

        new_version_number = max(row["versionNumber"] for row in rows) + 1
        new_version_id = f"rv-{new_version_number:03d}"
        rollback_id = f"rb-{new_version_number:03d}"
        requested_by = requested_by_user_id or "system"
        actor_id = requested_by if requested_by in self._users else "user-admin"

        target_rule = deepcopy(target["rule"])
        rollback_row = {
            "id": new_version_id,
            "ruleId": rule_id,
            "versionNumber": new_version_number,
            "createdAt": rolled_back_at,
            "createdBy": {
                "id": actor_id,
                "name": self._users[actor_id].display_name,
                "email": "admin@example.com",
            },
            "changeType": "rollback",
            "changeDescription": reason,
            "markedForRollback": False,
            "tags": list(tags) if tags else ["rollback"],
            "rule": target_rule,
            "relationships": {
                "approvals": [],
                "testProofs": [],
            },
        }
        rows.insert(0, rollback_row)
        self._rollback_history.setdefault(rule_id, []).insert(
            0,
            {
                "id": rollback_id,
                "ruleId": rule_id,
                "rolledBackAt": rolled_back_at,
                "rolledBackBy": self._users[actor_id].display_name,
                "reason": reason,
                "fromVersionNumber": current["versionNumber"],
                "toVersionNumber": target["versionNumber"],
                "newVersionNumber": new_version_number,
            },
        )

        self._rules[rule_id] = RuleEntity(
            id=rule_id,
            name=target_rule["name"],
            description=target_rule["description"],
            expression=target_rule["expression"],
            dimension=target_rule["dimension"],
            active=bool(target_rule["active"]),
            createdByUserId=actor_id,
            tagIds=self._rules[rule_id].tag_ids,
        )
        details = self._rule_details.setdefault(rule_id, {})
        details["dsl"] = deepcopy(target_rule.get("dsl")) if isinstance(target_rule.get("dsl"), dict) else None
        details["taxonomy"] = deepcopy(target_rule.get("taxonomy")) if isinstance(target_rule.get("taxonomy"), dict) else None
        details["check_type"] = target_rule.get("checkType")
        details["check_type_params"] = deepcopy(target_rule.get("checkTypeParams")) if isinstance(target_rule.get("checkTypeParams"), dict) else target_rule.get("checkTypeParams")

        return {
            "id": rollback_id,
            "status": "processing",
            "fromVersion": {
                "id": current["id"],
                "versionNumber": current["versionNumber"],
            },
            "toVersion": {
                "id": target["id"],
                "versionNumber": target["versionNumber"],
            },
            "newVersionCreated": {
                "id": new_version_id,
                "versionNumber": new_version_number,
                "status": "pending_approval" if not skip_approval else "activated",
            },
            "rolledBackBy": {
                "name": rollback_row["createdBy"]["name"],
            },
            "rolledBackAt": rolled_back_at,
            "estimatedCompletionTime": estimated_completion,
            "links": {
                "checkStatus": f"/rulebuilder/v1/rules/{rule_id}/rollbacks/{rollback_id}",
                "viewNewVersion": f"/rulebuilder/v1/rules/{rule_id}/versions/{new_version_id}",
            },
        }

    async def update_rule_version_tags(
        self,
        rule_id: str,
        version_id: str,
        tags: list[str],
        updated_by_user_id: str | None = None,
    ) -> dict | None:
        if rule_id not in self._rules:
            return None

        rows = self._rule_versions.get(rule_id, [])
        row = next((entry for entry in rows if entry["id"] == version_id), None)
        if row is None:
            return None

        actor_id = updated_by_user_id if updated_by_user_id in self._users else "user-admin"
        now = datetime.now(UTC).isoformat().replace("+00:00", "Z")

        row["tags"] = list(tags)
        row["updatedAt"] = now
        row["updatedBy"] = {
            "id": actor_id,
            "name": self._users[actor_id].display_name,
        }

        return {
            "id": row["id"],
            "versionNumber": row["versionNumber"],
            "tags": row["tags"],
            "updatedAt": row["updatedAt"],
            "updatedBy": row["updatedBy"],
        }

    async def mark_rule_version_for_rollback(
        self,
        rule_id: str,
        version_id: str,
        marked: bool,
    ) -> dict | None:
        if rule_id not in self._rules:
            return None

        rows = self._rule_versions.get(rule_id, [])
        row = next((entry for entry in rows if entry["id"] == version_id), None)
        if row is None:
            return None

        row["markedForRollback"] = bool(marked)
        return {
            "id": row["id"],
            "marked": bool(row["markedForRollback"]),
        }

    async def set_current_rule_version_validation(
        self,
        *,
        rule_id: str,
        validation_status: str,
        validated_by: str | None,
    ) -> dict | None:
        rows = self._rule_versions.get(rule_id, [])
        if not rows:
            return None

        current = rows[0]
        now = datetime.now(UTC).isoformat().replace("+00:00", "Z")
        validator_id = str(validated_by or "").strip() or None
        validator_name = ""
        if validator_id and validator_id in self._users:
            validator_name = self._users[validator_id].display_name
        elif validator_id:
            validator_name = validator_id

        current["validationStatus"] = str(validation_status or "").strip() or None
        current["validatedAt"] = now
        current["validatedBy"] = validator_name
        current["validatedByUserId"] = validator_id

        return {
            "ruleId": rule_id,
            "versionId": current.get("id"),
            "validationStatus": current.get("validationStatus"),
            "validatedAt": current.get("validatedAt"),
            "validatedBy": current.get("validatedBy"),
            "validatedByUserId": current.get("validatedByUserId"),
        }

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
        history = self._compiler_artifacts_by_version.setdefault(rule_version_id, [])
        for row in history:
            row["isActive"] = False

        next_revision = max((int(row.get("compilerRevision", 0)) for row in history), default=0) + 1
        created_at = datetime.now(UTC).isoformat().replace("+00:00", "Z")
        artifact_id = f"rca-{uuid4().hex[:12]}"

        row = {
            "id": artifact_id,
            "ruleVersionId": rule_version_id,
            "compilerVersion": compiler_version,
            "compilerRevision": next_revision,
            "artifactKey": artifact_key,
            "artifactPayload": deepcopy(artifact_payload),
            "diagnosticsPayload": deepcopy(diagnostics_payload),
            "compileStatus": compile_status,
            "sourceFingerprint": source_fingerprint,
            "isActive": True,
            "createdAt": created_at,
        }
        history.append(row)
        history.sort(key=lambda item: int(item.get("compilerRevision", 0)), reverse=True)
        return deepcopy(row)

    async def get_active_compiler_artifact(self, rule_version_id: str) -> dict | None:
        history = self._compiler_artifacts_by_version.get(rule_version_id, [])
        for row in history:
            if bool(row.get("isActive")):
                return deepcopy(row)
        return None

    async def list_compiler_artifacts(self, rule_version_id: str) -> list[dict]:
        history = self._compiler_artifacts_by_version.get(rule_version_id, [])
        return [deepcopy(row) for row in history]

    async def get_user_by_id(self, user_id: str) -> RuleCreatorEntity | None:
        return self._users.get(user_id)

    async def get_tags_by_ids(self, tag_ids: list[str]) -> list[RuleTagEntity]:
        return [self._tags[tag_id] for tag_id in tag_ids if tag_id in self._tags]

    def _current_rule_status(self, rule_id: str) -> str:
        current = self._rules.get(rule_id)
        if current is None:
            return "draft"

        details = self._rule_details.get(rule_id, {})
        if details.get("removed_at"):
            return "removed"
        if bool(current.active):
            return "activated"

        normalized_status = self._normalize_rule_status(details.get("last_approval_status"))
        return normalized_status or "draft"

    @staticmethod
    def _normalize_rule_status(value: str | None) -> str:
        normalized = str(value or "").strip().lower().replace("_", "-")
        if normalized == "pending":
            return "pending-approval"
        if normalized == "declined":
            return "rejected"
        return normalized

    def _ensure_rule_transition_allowed(self, *, from_status: str | None, to_status: str) -> None:
        normalized_from = self._normalize_rule_status(from_status)
        normalized_to = self._normalize_rule_status(to_status)
        if not normalized_from or normalized_from == normalized_to:
            return

        if not is_transition_defined(entity="rule", from_status=normalized_from, to_status=normalized_to):
            raise ValueError(f"Transition '{normalized_from}' -> '{normalized_to}' is not allowed")

    @staticmethod
    def _normalize_rule_lifecycle_status(value: str | None) -> str:
        return canonicalize_status(entity="rule_lifecycle", status=value)

    def _ensure_rule_lifecycle_transition_allowed(self, *, from_status: str | None, to_status: str) -> None:
        normalized_from = self._normalize_rule_lifecycle_status(from_status)
        normalized_to = self._normalize_rule_lifecycle_status(to_status)
        if not normalized_from or normalized_from == normalized_to:
            return

        if not is_transition_defined(entity="rule_lifecycle", from_status=normalized_from, to_status=normalized_to):
            raise ValueError(f"Transition '{normalized_from}' -> '{normalized_to}' is not allowed")

    def _record_status_transition(
        self,
        *,
        rule_id: str,
        action: str,
        from_status: str | None,
        to_status: str,
        changed_by: str | None,
        reason: str | None,
        details: dict | None = None,
        allow_same_status: bool = False,
    ) -> dict | None:
        normalized_from = self._normalize_rule_status(from_status)
        normalized_to = self._normalize_rule_status(to_status)
        normalized_action = self._normalize_rule_audit_action(action)
        if not normalized_to:
            return None
        if normalized_from and normalized_from == normalized_to and not allow_same_status:
            return None

        row = {
            "id": f"rsh-{uuid4().hex[:12]}",
            "ruleId": rule_id,
            "action": normalized_action,
            "fromStatus": normalized_from or None,
            "toStatus": normalized_to,
            "changedBy": str(changed_by or "").strip() or None,
            "changedAt": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            "reason": reason,
            "details": deepcopy(details) if details is not None else None,
        }
        history = self._status_history.setdefault(rule_id, [])
        history.append(row)
        history.sort(key=lambda item: (str(item.get("changedAt") or ""), str(item.get("id") or "")))

        return row

    @staticmethod
    def _normalize_rule_audit_action(value: str | None) -> str:
        normalized = str(value or "").strip().lower().replace("_", "-")
        return normalized or "transition"

    @staticmethod
    def _infer_rule_transition_action(to_status: str | None) -> str:
        normalized = str(to_status or "").strip().lower().replace("_", "-")
        action_map = {
            "approved": "approve",
            "rejected": "reject",
            "activated": "activate",
            "deactivated": "deactivate",
            "deprecated": "deprecate",
            "superseded": "supersede",
            "retired": "retire",
            "removed": "remove",
            "recovered": "recover",
        }
        return action_map.get(normalized, "transition")

    @staticmethod
    def _rule_lifecycle_action(lifecycle_status: str) -> str:
        normalized = str(lifecycle_status or "").strip().lower().replace("_", "-")
        action_map = {
            "active": "activate",
            "deprecated": "deprecate",
            "superseded": "supersede",
            "retired": "retire",
        }
        return action_map.get(normalized, "transition")

    async def list_reusable_filters(self, workspace: str | None = None, query: str | None = None) -> list[dict]:
        rows = [row.copy() for row in self._reusable_filters.values()]
        if workspace:
            rows = [row for row in rows if str(row.get("workspace") or "") == workspace]
        normalized_query = str(query or "").strip().lower()
        if normalized_query:
            rows = [
                row for row in rows
                if normalized_query in " ".join([
                    str(row.get("name") or ""),
                    str(row.get("description") or ""),
                    str(row.get("filter_expression") or row.get("expression") or ""),
                ]).lower()
            ]
        return sorted(rows, key=lambda row: str(row.get("name") or "").lower())

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
        now = datetime.now(UTC).isoformat().replace("+00:00", "Z")
        filter_id = f"rf_{uuid4().hex[:10]}"
        row = {
            "id": filter_id,
            "name": name,
            "description": description,
            "expression": expression,
            "filter_expression": expression,
            "workspace": workspace,
            "created_by": created_by,
            "active": bool(active),
            "created_at": now,
            "updated_at": now,
        }
        self._reusable_filters[filter_id] = row
        return row.copy()

    async def delete_reusable_filter(self, filter_id: str) -> bool:
        if filter_id not in self._reusable_filters:
            return False

        in_use = any(
            filter_id in (row.get("reusableFilterIds") or [])
            for row in await self._list_rule_payloads(include_deleted=False)
        )
        if in_use:
            raise ValueError("Cannot delete reusable filter that is assigned to one or more rules")

        del self._reusable_filters[filter_id]
        return True

    async def get_reusable_filter(self, filter_id: str) -> dict | None:
        row = self._reusable_filters.get(filter_id)
        if row is None:
            return None
        return row.copy()

    async def update_reusable_filter(
        self,
        *,
        filter_id: str,
        name: str,
        expression: str,
        description: str | None,
        active: bool,
    ) -> dict | None:
        row = self._reusable_filters.get(filter_id)
        if row is None:
            return None

        row["name"] = name
        row["description"] = description
        row["expression"] = expression
        row["filter_expression"] = expression
        row["active"] = bool(active)
        row["updated_at"] = datetime.now(UTC).isoformat().replace("+00:00", "Z")
        return row.copy()

    async def list_reusable_joins(self, workspace: str | None = None) -> list[dict]:
        rows = [row.copy() for row in self._reusable_joins.values()]
        if workspace:
            rows = [row for row in rows if str(row.get("workspace") or "") == workspace]
        return sorted(rows, key=lambda row: str(row.get("name") or "").lower())

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
        now = datetime.now(UTC).isoformat().replace("+00:00", "Z")
        join_id = f"rj_{uuid4().hex[:10]}"
        row = {
            "id": join_id,
            "name": name,
            "description": description,
            "join_definition": join_definition,
            "workspace": workspace,
            "created_by": created_by,
            "active": bool(active),
            "created_at": now,
            "updated_at": now,
        }
        self._reusable_joins[join_id] = row
        return row.copy()

    async def delete_reusable_join(self, join_id: str) -> bool:
        if join_id not in self._reusable_joins:
            return False

        in_use = any(
            str(row.get("reusable_join_id") or "") == join_id
            for row in await self._list_rule_payloads(include_deleted=False)
        )
        if in_use:
            raise ValueError("Cannot delete reusable join that is assigned to one or more rules")

        del self._reusable_joins[join_id]
        return True

    async def get_reusable_join(self, join_id: str) -> dict | None:
        row = self._reusable_joins.get(join_id)
        if row is None:
            return None
        return row.copy()

    async def update_reusable_join(
        self,
        *,
        join_id: str,
        name: str,
        join_definition: str,
        description: str | None,
        active: bool,
    ) -> dict | None:
        row = self._reusable_joins.get(join_id)
        if row is None:
            return None

        row["name"] = name
        row["description"] = description
        row["join_definition"] = join_definition
        row["active"] = bool(active)
        row["updated_at"] = datetime.now(UTC).isoformat().replace("+00:00", "Z")
        return row.copy()
