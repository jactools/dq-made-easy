from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime
from uuid import uuid4

from app.domain.entities import build_rule_record_entity, RuleEntity, RuleRecordEntity


class InMemoryRulesWriteMixin:

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
