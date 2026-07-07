from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

from app.domain.entities import RuleEntity


class InMemoryRuleVersionsMixin:

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
