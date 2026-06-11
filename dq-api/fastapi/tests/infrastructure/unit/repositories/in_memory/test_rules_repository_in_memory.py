import asyncio

import pytest

from app.infrastructure.repositories import InMemoryRulesRepository

pytestmark = pytest.mark.usefixtures("clone_payload")


def test_list_rule_records_returns_seed_rule() -> None:
    repository = InMemoryRulesRepository()

    payload = asyncio.run(repository.list_rule_records())

    assert len(payload) == 1
    assert payload[0].id == "rule-email-format"
    assert payload[0].created_by == "user-admin"


def test_list_rule_versions_returns_paginated_window() -> None:
    repository = InMemoryRulesRepository()

    payload = asyncio.run(repository.list_rule_versions("rule-email-format", limit=1, offset=0))

    assert payload is not None
    assert payload["ruleId"] == "rule-email-format"
    assert payload["pagination"]["limit"] == 1
    assert len(payload["versions"]) == 1


def test_list_rule_versions_returns_none_for_missing_rule() -> None:
    repository = InMemoryRulesRepository()

    payload = asyncio.run(repository.list_rule_versions("missing-rule"))

    assert payload is None


def test_get_rule_version_returns_expected_version() -> None:
    repository = InMemoryRulesRepository()

    payload = asyncio.run(repository.get_rule_version("rule-email-format", "rv-001"))

    assert payload is not None
    assert payload["versionNumber"] == 2


def test_get_rule_version_returns_none_for_missing_version() -> None:
    repository = InMemoryRulesRepository()

    payload = asyncio.run(repository.get_rule_version("rule-email-format", "does-not-exist"))

    assert payload is None


def test_get_rule_rollback_history_returns_paginated_window() -> None:
    repository = InMemoryRulesRepository()

    payload = asyncio.run(repository.get_rule_rollback_history("rule-email-format", limit=1, offset=0))

    assert payload is not None
    assert payload["ruleId"] == "rule-email-format"
    assert payload["pagination"]["limit"] == 1
    assert len(payload["rollbacks"]) == 1


def test_get_rule_rollback_history_returns_none_for_missing_rule() -> None:
    repository = InMemoryRulesRepository()

    payload = asyncio.run(repository.get_rule_rollback_history("missing-rule"))

    assert payload is None


def test_get_rule_by_id_includes_reusable_assets() -> None:
    repository = InMemoryRulesRepository()
    repository._rule_details["rule-email-format"]["reusable_join_id"] = "rj-1"
    repository._rule_details["rule-email-format"]["reusableFilterIds"] = ["rf-1", "rf-2"]

    payload = asyncio.run(repository.get_rule_by_id("rule-email-format"))

    assert payload is not None
    assert payload.reusable_join_id == "rj-1"
    assert payload.reusable_filter_ids == ["rf-1", "rf-2"]


def test_get_rule_by_id_includes_lifecycle_status() -> None:
    repository = InMemoryRulesRepository()
    repository._rule_details["rule-email-format"]["lifecycle_status"] = "deprecated"

    payload = asyncio.run(repository.get_rule_by_id("rule-email-format"))

    assert payload is not None
    assert payload.lifecycle_status == "deprecated"


def test_list_rule_status_history_returns_seeded_transition() -> None:
    repository = InMemoryRulesRepository()

    payload = asyncio.run(repository.list_rule_status_history("rule-email-format", limit=10, offset=0))

    assert payload is not None
    assert len(payload) >= 1
    assert payload[0]["ruleId"] == "rule-email-format"
    assert payload[0]["action"] == "activate"
    assert payload[0]["toStatus"] == "activated"


@pytest.mark.parametrize(
    ("to_status", "expected_action"),
    [
        ("approved", "approve"),
        ("rejected", "reject"),
    ],
)
def test_record_rule_status_transition_appends_history_row(to_status: str, expected_action: str) -> None:
    repository = InMemoryRulesRepository()

    created = asyncio.run(
        repository.record_rule_status_transition(
            "rule-email-format",
            "pending-approval",
            to_status,
            changed_by="user-admin",
            reason="Rule test passed",
        )
    )

    assert created is not None
    assert created["fromStatus"] == "pending-approval"
    assert created["toStatus"] == to_status
    assert created["action"] == expected_action


@pytest.mark.parametrize(
    ("lifecycle_status", "expected_action"),
    [
        ("deprecated", "deprecate"),
        ("superseded", "supersede"),
        ("retired", "retire"),
    ],
)
def test_set_rule_lifecycle_status_records_lifecycle_action(lifecycle_status: str, expected_action: str) -> None:
    repository = InMemoryRulesRepository()
    if lifecycle_status == "retired":
        repository._rules["rule-email-format"] = repository._rules["rule-email-format"].model_copy(update={"active": False})

    payload = asyncio.run(
        repository.set_rule_lifecycle_status(
            "rule-email-format",
            lifecycle_status=lifecycle_status,
            changed_by="user-admin",
            reason="Lifecycle review",
        )
    )

    assert payload is not None
    assert payload.lifecycle_status == lifecycle_status
    history = asyncio.run(repository.list_rule_status_history("rule-email-format"))
    assert history is not None
    assert history[0]["action"] == expected_action
    assert history[0]["changedBy"] == "user-admin"
    assert history[0]["changedAt"]
    assert history[0]["reason"] == "Lifecycle review"


def test_compare_rule_versions_returns_diff_payload() -> None:
    repository = InMemoryRulesRepository()

    payload = asyncio.run(repository.compare_rule_versions("rule-email-format", "rv-000", "rv-001"))

    assert payload is not None
    assert payload["fromVersion"]["id"] == "rv-000"
    assert payload["toVersion"]["id"] == "rv-001"
    assert payload["changes"]["summary"]["fieldsChanged"] >= 1


def test_compare_rule_versions_returns_none_for_missing_versions() -> None:
    repository = InMemoryRulesRepository()

    payload = asyncio.run(repository.compare_rule_versions("rule-email-format", "rv-missing", "rv-001"))

    assert payload is None


def test_get_rule_version_statistics_returns_payload() -> None:
    repository = InMemoryRulesRepository()

    payload = asyncio.run(repository.get_rule_version_statistics("rule-email-format"))

    assert payload is not None
    assert payload["versions"]["total"] >= 1
    assert "changeTypes" in payload["versions"]
    assert "rollbacks" in payload


def test_get_rule_version_statistics_returns_none_for_missing_rule() -> None:
    repository = InMemoryRulesRepository()

    payload = asyncio.run(repository.get_rule_version_statistics("missing-rule"))

    assert payload is None


def test_mark_rule_version_for_rollback_returns_updated_flag() -> None:
    repository = InMemoryRulesRepository()

    payload = asyncio.run(
        repository.mark_rule_version_for_rollback(
            rule_id="rule-email-format",
            version_id="rv-001",
            marked=True,
        )
    )

    assert payload is not None
    assert payload["id"] == "rv-001"
    assert payload["marked"] is True


def test_mark_rule_version_for_rollback_returns_none_for_missing_version() -> None:
    repository = InMemoryRulesRepository()

    payload = asyncio.run(
        repository.mark_rule_version_for_rollback(
            rule_id="rule-email-format",
            version_id="rv-missing",
            marked=True,
        )
    )

    assert payload is None


def test_execute_rule_rollback_creates_new_version() -> None:
    repository = InMemoryRulesRepository()

    payload = asyncio.run(
        repository.execute_rule_rollback(
            rule_id="rule-email-format",
            to_version_id="rv-000",
            reason="Rollback to stable version",
            requested_by_user_id="user-admin",
        )
    )

    assert payload is not None
    assert payload["status"] == "processing"
    assert payload["toVersion"]["id"] == "rv-000"

    new_version_id = payload["newVersionCreated"]["id"]
    created = asyncio.run(repository.get_rule_version("rule-email-format", new_version_id))
    assert created is not None
    assert created["changeType"] == "rollback"


def test_execute_rule_rollback_returns_none_for_missing_rule() -> None:
    repository = InMemoryRulesRepository()

    payload = asyncio.run(
        repository.execute_rule_rollback(
            rule_id="missing-rule",
            to_version_id="rv-000",
            reason="Rollback request",
        )
    )

    assert payload is None


def test_update_rule_creates_new_version_and_clears_validation() -> None:
    repository = InMemoryRulesRepository()

    payload = asyncio.run(
        repository.update_rule_record(
            rule_id="rule-email-format",
            name="Email format validation",
            description="Ensure customer email values still match expected pattern",
            comments=None,
            expression="email ~ '^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\\.[A-Za-z]{2,}$'",
            dimension="validity",
            active=True,
            dsl=None,
            join_conditions=[],
            alias_mappings={},
            reusable_join_id=None,
            reusable_filter_ids=["rf-1", "rf-1", "rf-2"],
            manual_override_by=None,
            manual_override_at=None,
            check_type="sql",
            check_type_params=None,
            taxonomy={"owner": "steward@example.com"},
        )
    )

    assert payload is not None
    assert payload.validation_status is None
    assert payload.current_version_id == "rv-003"
    assert payload.total_versions == 3
    assert payload.taxonomy.owner == "steward@example.com"

    versions = asyncio.run(repository.list_rule_versions("rule-email-format"))
    assert versions is not None
    assert versions["versioning"]["totalVersions"] == 3
    assert versions["versions"][0]["versionNumber"] == 3
    assert versions["versions"][0]["validationStatus"] is None

    version_detail = asyncio.run(repository.get_rule_version("rule-email-format", "rv-003"))
    assert version_detail is not None
    assert version_detail["rule"]["taxonomy"]["owner"] == "steward@example.com"


def test_execute_rule_rollback_raises_for_current_version() -> None:
    repository = InMemoryRulesRepository()

    with pytest.raises(ValueError):
        asyncio.run(
            repository.execute_rule_rollback(
                rule_id="rule-email-format",
                to_version_id="rv-001",
                reason="Invalid rollback",
            )
        )


def test_execute_rule_rollback_raises_for_missing_target_version() -> None:
    repository = InMemoryRulesRepository()

    with pytest.raises(LookupError):
        asyncio.run(
            repository.execute_rule_rollback(
                rule_id="rule-email-format",
                to_version_id="rv-missing",
                reason="Invalid rollback",
            )
        )


def test_update_rule_version_tags_returns_updated_payload() -> None:
    repository = InMemoryRulesRepository()

    payload = asyncio.run(
        repository.update_rule_version_tags(
            rule_id="rule-email-format",
            version_id="rv-001",
            tags=["production", "stable"],
            updated_by_user_id="user-admin",
        )
    )

    assert payload is not None
    assert payload["id"] == "rv-001"
    assert payload["tags"] == ["production", "stable"]
    assert payload["updatedBy"]["id"] == "user-admin"


def test_update_rule_version_tags_returns_none_for_missing_rule() -> None:
    repository = InMemoryRulesRepository()

    payload = asyncio.run(
        repository.update_rule_version_tags(
            rule_id="missing-rule",
            version_id="rv-001",
            tags=["production"],
        )
    )

    assert payload is None


def test_update_rule_version_tags_returns_none_for_missing_version() -> None:
    repository = InMemoryRulesRepository()

    payload = asyncio.run(
        repository.update_rule_version_tags(
            rule_id="rule-email-format",
            version_id="rv-missing",
            tags=["production"],
        )
    )

    assert payload is None


def test_compiler_artifact_upsert_creates_internal_revisions() -> None:
    repository = InMemoryRulesRepository()

    first = asyncio.run(
        repository.upsert_active_compiler_artifact(
            rule_version_id="rv-001",
            compiler_version="dq-7.3.0",
            artifact_key="rule::rule-email-format::version::rv-001::a1",
            artifact_payload={"foo": "bar"},
            diagnostics_payload=[],
            compile_status="compiled",
            source_fingerprint="fp-1",
        )
    )
    second = asyncio.run(
        repository.upsert_active_compiler_artifact(
            rule_version_id="rv-001",
            compiler_version="dq-7.3.1",
            artifact_key="rule::rule-email-format::version::rv-001::a2",
            artifact_payload={"foo": "baz"},
            diagnostics_payload=[{"code": "DQ7_INFO", "severity": "info", "message": "ok"}],
            compile_status="compiled",
            source_fingerprint="fp-2",
        )
    )

    assert first["compilerRevision"] == 1
    assert second["compilerRevision"] == 2

    active = asyncio.run(repository.get_active_compiler_artifact("rv-001"))
    assert active is not None
    assert active["id"] == second["id"]
    assert active["isActive"] is True

    history = asyncio.run(repository.list_compiler_artifacts("rv-001"))
    assert len(history) == 2
    assert history[0]["compilerRevision"] == 2
    assert history[1]["compilerRevision"] == 1
    assert history[1]["isActive"] is False


def test_compiler_artifact_get_active_returns_none_when_missing() -> None:
    repository = InMemoryRulesRepository()
    assert asyncio.run(repository.get_active_compiler_artifact("rv-missing")) is None


def test_soft_delete_and_recover_rule_lifecycle() -> None:
    repository = InMemoryRulesRepository()

    created = asyncio.run(
        repository.create_rule_record(
            name="Removable Rule",
            description="soft delete flow",
            comments=None,
            expression="email IS NOT NULL",
            dimension="completeness",
            active=True,
            workspace="default",
            created_by="user-admin",
            generated=False,
            is_template=False,
            template_id=None,
            suggestion_id=None,
            dsl=None,
            join_conditions=[],
            alias_mappings={},
            reusable_join_id=None,
            reusable_filter_ids=[],
            manual_override_by=None,
            manual_override_at=None,
            check_type=None,
            check_type_params=None,
            taxonomy=None,
        )
    )
    rule_id = str(created.id)

    with pytest.raises(ValueError, match="deactivated"):
        asyncio.run(repository.soft_delete_rule_record(rule_id, removed_by="user-admin"))

    asyncio.run(repository.deactivate_rule(rule_id))
    removed = asyncio.run(repository.soft_delete_rule_record(rule_id, removed_by="user-admin"))

    assert removed is not None
    assert removed.id == rule_id
    assert removed.removed is True
    assert removed.removed_by == "user-admin"
    assert removed.last_approval_status == "removed"
    assert asyncio.run(repository.get_rule_by_id(rule_id)) is None

    recovered = asyncio.run(repository.recover_rule(rule_id, recovered_by="user-admin"))

    assert recovered is not None
    assert recovered["id"] == rule_id
    assert recovered["removed"] is False
    assert recovered["active"] is False
    assert recovered["last_approval_status"] == "recovered"
    assert recovered["ok"] is True
