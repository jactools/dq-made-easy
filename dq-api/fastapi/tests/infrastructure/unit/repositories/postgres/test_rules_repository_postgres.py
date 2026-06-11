import asyncio
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

import app.infrastructure.repositories.postgres_rules_repository as rules_mod
from app.infrastructure.repositories.postgres_rules_repository import PostgresRulesRepository


class _ScalarResult:
    def __init__(self, values):
        self._values = values

    def scalars(self):
        return self

    def all(self):
        return self._values if isinstance(self._values, list) else [self._values]

    def scalar_one_or_none(self):
        if isinstance(self._values, list):
            return self._values[0] if self._values else None
        return self._values

    def mappings(self):
        return self

    def one(self):
        if isinstance(self._values, list):
            return self._values[0]
        return self._values

    def first(self):
        if isinstance(self._values, list):
            return self._values[0] if self._values else None
        return self._values


class _Session:
    def __init__(self, scalar_values=None, gets=None):
        self.scalar_values = list(scalar_values or [])
        self.gets = dict(gets or {})
        self.added = []
        self.deleted = []
        self.flush_calls = 0

    def execute(self, stmt):
        if self.scalar_values:
            return _ScalarResult(self.scalar_values.pop(0))
        return _ScalarResult([])

    def get(self, model, key):
        return self.gets.get((model, key))

    def add(self, value):
        self.added.append(value)

    def delete(self, value):
        self.deleted.append(value)

    def commit(self):
        return None

    def refresh(self, _value):
        return None

    def flush(self):
        self.flush_calls += 1
        return None


class _Ctx:
    def __init__(self, session):
        self._session = session

    def __enter__(self):
        return self._session

    def __exit__(self, exc_type, exc, tb):
        return False


def _rule_row():
    return SimpleNamespace(
        id="rule-1",
        name="Rule One",
        description="Desc",
        expression="value > 0",
        dimension="validity",
        active=True,
        generated=False,
        is_template=False,
        template_id=None,
        workspace="default",
        created_by="user-admin",
        last_approval_by=None,
        last_approval_status="approved",
        lifecycle_status="active",
        last_approval_at=None,
        deleted_on=None,
        deleted_by=None,
        suggestion_id=None,
        join_conditions=None,
        alias_mappings=None,
        reusable_join_id="rj-1",
        validation_status=None,
        validated_at=None,
        current_version_id=None,
        total_versions=1,
        versioning_enabled=True,
        version_created_at=None,
        version_updated_at=None,
        validated_by=None,
        manual_override_by=None,
        manual_override_at=None,
        check_type="sql",
        check_type_params=None,
    )


def test_list_rule_records_maps_rows(monkeypatch) -> None:
    session = _Session(scalar_values=[[_rule_row()]])
    monkeypatch.setattr(rules_mod, "session_scope", lambda db_url: _Ctx(session))

    repo = PostgresRulesRepository("postgresql://example")
    payload = asyncio.run(repo.list_rule_records())

    assert len(payload) == 1
    assert payload[0].id == "rule-1"
    assert payload[0].created_by == "user-admin"


def test_get_rule_by_id_maps_entity(monkeypatch) -> None:
    session = _Session(
        scalar_values=[
            _rule_row(),
            [("rf-1",), ("rf-2",)],
        ]
    )
    monkeypatch.setattr(rules_mod, "session_scope", lambda db_url: _Ctx(session))

    repo = PostgresRulesRepository("postgresql://example")
    payload = asyncio.run(repo.get_rule_by_id("rule-1"))

    assert payload is not None
    assert payload.id == "rule-1"
    assert payload.created_by_user_id == "user-admin"
    assert payload.reusable_join_id == "rj-1"
    assert payload.reusable_filter_ids == ["rf-1", "rf-2"]


def test_get_user_by_id_maps_rule_creator(monkeypatch) -> None:
    user = SimpleNamespace(id="user-admin", name="Platform Admin", email="admin@example.com")
    session = _Session(gets={(rules_mod.UserRow, "user-admin"): user})
    monkeypatch.setattr(rules_mod, "session_scope", lambda db_url: _Ctx(session))

    repo = PostgresRulesRepository("postgresql://example")
    payload = asyncio.run(repo.get_user_by_id("user-admin"))

    assert payload is not None
    assert payload.id == "user-admin"
    assert payload.username == "admin"
    assert payload.display_name == "Platform Admin"


def _version_row(version_id="rv-001", number=2, created_by="user-admin"):
    return SimpleNamespace(
        id=version_id,
        rule_id="rule-1",
        version_number=number,
        created_at=None,
        created_by=created_by,
        change_type="modified",
        change_description="Updated expression",
        name="Rule One",
        description="Desc",
        expression="value > 0",
        dimension="validity",
        active=True,
        is_template=False,
        template_id=None,
        tags=["stable"],
        marked_for_rollback=False,
        validated_by=None,
        validation_status="approved",
        validated_at=None,
        check_type="sql",
        check_type_params=None,
        manual_override_by=None,
        manual_override_at=None,
    )


def test_list_rule_versions_maps_postgres_rows(monkeypatch) -> None:
    session = _Session(
        scalar_values=[
            _rule_row(),
            [_version_row("rv-002", 3), _version_row("rv-001", 2)],
            [SimpleNamespace(id="user-admin", name="Platform Admin", email="admin@example.com")],
        ]
    )
    monkeypatch.setattr(rules_mod, "session_scope", lambda db_url: _Ctx(session))

    repo = PostgresRulesRepository("postgresql://example")
    payload = asyncio.run(repo.list_rule_versions("rule-1", limit=1, offset=0))

    assert payload is not None
    assert payload["ruleId"] == "rule-1"
    assert payload["pagination"]["limit"] == 1
    assert payload["versions"][0]["id"] == "rv-002"
    assert payload["versions"][0]["createdBy"] == "Platform Admin"


def test_get_rule_version_maps_postgres_detail(monkeypatch) -> None:
    session = _Session(
        scalar_values=[
            _version_row("rv-001", 2),
            [SimpleNamespace(id="user-admin", name="Platform Admin", email="admin@example.com")],
        ]
    )
    monkeypatch.setattr(rules_mod, "session_scope", lambda db_url: _Ctx(session))

    repo = PostgresRulesRepository("postgresql://example")
    payload = asyncio.run(repo.get_rule_version("rule-1", "rv-001"))

    assert payload is not None
    assert payload["id"] == "rv-001"
    assert payload["versionNumber"] == 2
    assert payload["createdBy"] == "Platform Admin"


def test_get_rule_by_id_returns_none_when_missing(monkeypatch) -> None:
    session = _Session(scalar_values=[None])
    monkeypatch.setattr(rules_mod, "session_scope", lambda db_url: _Ctx(session))

    repo = PostgresRulesRepository("postgresql://example")
    payload = asyncio.run(repo.get_rule_by_id("missing"))

    assert payload is None


def test_create_rule_adds_only_non_empty_unique_reusable_filters(monkeypatch) -> None:
    session = _Session()
    monkeypatch.setattr(rules_mod, "session_scope", lambda db_url: _Ctx(session))

    repo = PostgresRulesRepository("postgresql://example")
    payload = asyncio.run(
        repo.create_rule_record(
            name="Rule",
            description=None,
            comments=None,
            expression="x > 0",
            dimension="validity",
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
            reusable_filter_ids=["rf-1", "", "rf-1", "rf-2"],
            manual_override_by=None,
            manual_override_at=None,
            check_type="sql",
            check_type_params=None,
            taxonomy={"owner": "steward@example.com"},
        )
    )

    assert payload.id.startswith("rule-")
    assert len(session.added) == 6
    assert session.flush_calls == 1
    assert any(getattr(entry, "taxonomy", None) == '{"owner": "steward@example.com"}' for entry in session.added)
    history_entry = next(entry for entry in session.added if entry.__class__.__name__ == "RuleStatusHistoryRow")
    assert history_entry.action == "create"
    assert history_entry.reason == "Rule created"


def test_update_rule_returns_none_when_missing(monkeypatch) -> None:
    session = _Session(scalar_values=[None])
    monkeypatch.setattr(rules_mod, "session_scope", lambda db_url: _Ctx(session))

    repo = PostgresRulesRepository("postgresql://example")
    payload = asyncio.run(
        repo.update_rule_record(
            rule_id="missing",
            name="Rule",
            description=None,
            comments=None,
            expression="x > 0",
            dimension="validity",
            active=True,
            dsl=None,
            join_conditions=[],
            alias_mappings={},
            reusable_join_id=None,
            reusable_filter_ids=[],
            manual_override_by=None,
            manual_override_at=None,
            check_type="sql",
            check_type_params=None,
            taxonomy=None,
        )
    )

    assert payload is None


def test_update_rule_replaces_existing_filter_links(monkeypatch) -> None:
    row = _rule_row()
    row.validation_status = "validated"
    row.validated_at = datetime(2026, 3, 10, tzinfo=UTC)
    links = [SimpleNamespace(id="l1"), SimpleNamespace(id="l2")]
    current_pointer = SimpleNamespace(rule_id="rule-1", version_id="rv-001")
    session = _Session(scalar_values=[row, links], gets={(rules_mod.RuleCurrentVersionRow, "rule-1"): current_pointer})
    monkeypatch.setattr(rules_mod, "session_scope", lambda db_url: _Ctx(session))

    repo = PostgresRulesRepository("postgresql://example")
    payload = asyncio.run(
        repo.update_rule_record(
            rule_id="rule-1",
            name="Updated",
            description="desc",
            comments=None,
            expression="x >= 0",
            dimension="consistency",
            active=False,
            dsl=None,
            join_conditions=[{"k": "v"}],
            alias_mappings={"a": "b"},
            reusable_join_id="rj-1",
            reusable_filter_ids=["rf-1", "rf-1", "", "rf-2"],
            manual_override_by=None,
            manual_override_at=None,
            check_type="sql",
            check_type_params=None,
            taxonomy={"owner": "steward@example.com"},
        )
    )

    assert payload is not None
    assert payload.total_versions == 2
    assert payload.current_version_id == current_pointer.version_id
    assert payload.validation_status is None
    assert payload.validated_at is None
    assert payload.taxonomy.owner == "steward@example.com"
    assert current_pointer.version_id != "rv-001"
    assert len(session.deleted) == 2
    assert len(session.added) == 4
    assert session.flush_calls == 1
    assert any(entry.__class__.__name__ == "RuleVersionRow" for entry in session.added)
    history_entry = next(entry for entry in session.added if entry.__class__.__name__ == "RuleStatusHistoryRow")
    assert history_entry.action == "edit"
    assert history_entry.reason == "Rule updated"


def test_activate_rule_record_returns_none_when_missing(monkeypatch) -> None:
    session = _Session(scalar_values=[None])
    monkeypatch.setattr(rules_mod, "session_scope", lambda db_url: _Ctx(session))

    repo = PostgresRulesRepository("postgresql://example")
    assert asyncio.run(repo.activate_rule_record("missing")) is None


def test_save_rule_as_template_returns_none_when_source_missing(monkeypatch) -> None:
    session = _Session(scalar_values=[None])
    monkeypatch.setattr(rules_mod, "session_scope", lambda db_url: _Ctx(session))

    repo = PostgresRulesRepository("postgresql://example")
    payload = asyncio.run(
        repo.save_rule_as_template(
            rule_id="missing",
            template_name="Template",
            template_description=None,
            created_by="user-admin",
        )
    )

    assert payload is None


def test_list_rule_versions_returns_none_when_rule_missing(monkeypatch) -> None:
    session = _Session()
    monkeypatch.setattr(rules_mod, "session_scope", lambda db_url: _Ctx(session))
    monkeypatch.setattr(PostgresRulesRepository, "_get_rule_row", staticmethod(lambda _s, _id: None))

    repo = PostgresRulesRepository("postgresql://example")
    assert asyncio.run(repo.list_rule_versions("missing")) is None


def test_get_rule_version_returns_none_when_missing(monkeypatch) -> None:
    session = _Session(scalar_values=[None])
    monkeypatch.setattr(rules_mod, "session_scope", lambda db_url: _Ctx(session))

    repo = PostgresRulesRepository("postgresql://example")
    assert asyncio.run(repo.get_rule_version("rule-1", "missing")) is None


def test_upsert_active_compiler_artifact_creates_new_internal_revision(monkeypatch) -> None:
    existing = SimpleNamespace(compiler_revision=1, is_active=True)
    session = _Session(
        scalar_values=[
            _version_row("rv-001", 2),
            [existing],
        ]
    )
    monkeypatch.setattr(rules_mod, "session_scope", lambda db_url: _Ctx(session))

    repo = PostgresRulesRepository("postgresql://example")
    payload = asyncio.run(
        repo.upsert_active_compiler_artifact(
            rule_version_id="rv-001",
            compiler_version="dq-7.3.1",
            artifact_key="rule::rule-1::version::rv-001::abc123",
            artifact_payload={"target": "dsl"},
            diagnostics_payload=[{"code": "DQ7_INFO", "severity": "info", "message": "ok"}],
            compile_status="compiled",
            source_fingerprint="fp-001",
        )
    )

    assert existing.is_active is False
    assert payload["compilerRevision"] == 2
    assert payload["ruleVersionId"] == "rv-001"
    assert payload["isActive"] is True


def test_upsert_active_compiler_artifact_raises_for_missing_rule_version(monkeypatch) -> None:
    session = _Session(scalar_values=[None])
    monkeypatch.setattr(rules_mod, "session_scope", lambda db_url: _Ctx(session))

    repo = PostgresRulesRepository("postgresql://example")
    with pytest.raises(LookupError):
        asyncio.run(
            repo.upsert_active_compiler_artifact(
                rule_version_id="rv-missing",
                compiler_version="dq-7.3.1",
                artifact_key="rule::missing",
                artifact_payload={},
                diagnostics_payload=[],
                compile_status="failed",
                source_fingerprint="fp-missing",
            )
        )


def test_get_and_list_compiler_artifacts_map_payload(monkeypatch) -> None:
    artifact_active = SimpleNamespace(
        id="rca-1",
        rule_version_id="rv-001",
        compiler_version="dq-7.3.1",
        compiler_revision=2,
        artifact_key="rule::rule-1::version::rv-001::a2",
        artifact_payload={"target": "dsl"},
        diagnostics_payload={"items": [{"code": "DQ7_INFO", "severity": "info", "message": "ok"}]},
        compile_status="compiled",
        source_fingerprint="fp-2",
        is_active=True,
        created_at=None,
    )
    artifact_old = SimpleNamespace(
        id="rca-0",
        rule_version_id="rv-001",
        compiler_version="dq-7.3.0",
        compiler_revision=1,
        artifact_key="rule::rule-1::version::rv-001::a1",
        artifact_payload={"target": "dsl"},
        diagnostics_payload={"items": []},
        compile_status="compiled",
        source_fingerprint="fp-1",
        is_active=False,
        created_at=None,
    )
    session = _Session(scalar_values=[artifact_active, [artifact_active, artifact_old]])
    monkeypatch.setattr(rules_mod, "session_scope", lambda db_url: _Ctx(session))

    repo = PostgresRulesRepository("postgresql://example")
    active = asyncio.run(repo.get_active_compiler_artifact("rv-001"))
    history = asyncio.run(repo.list_compiler_artifacts("rv-001"))

    assert active is not None
    assert active["compilerRevision"] == 2
    assert active["diagnosticsPayload"][0]["code"] == "DQ7_INFO"
    assert len(history) == 2
    assert history[0]["compilerRevision"] == 2
    assert history[1]["compilerRevision"] == 1


def test_get_rule_rollback_history_returns_none_when_rule_missing(monkeypatch) -> None:
    session = _Session()
    monkeypatch.setattr(rules_mod, "session_scope", lambda db_url: _Ctx(session))
    monkeypatch.setattr(PostgresRulesRepository, "_get_rule_row", staticmethod(lambda _s, _id: None))

    repo = PostgresRulesRepository("postgresql://example")
    assert asyncio.run(repo.get_rule_rollback_history("missing")) is None


def test_compare_rule_versions_returns_none_when_missing_version(monkeypatch) -> None:
    session = _Session(scalar_values=[[_version_row("v1", 1)]])
    monkeypatch.setattr(rules_mod, "session_scope", lambda db_url: _Ctx(session))

    repo = PostgresRulesRepository("postgresql://example")
    payload = asyncio.run(repo.compare_rule_versions("rule-1", "v1", "v2"))

    assert payload is None


def test_compare_rule_versions_collects_field_and_tag_changes(monkeypatch) -> None:
    first = _version_row("v1", 1)
    second = _version_row("v2", 2)
    second.expression = "x < 100"
    second.tags = ["new"]
    session = _Session(
        scalar_values=[
            [first, second],
            [SimpleNamespace(id="user-admin", name="Platform Admin", email="admin@example.com")],
        ]
    )
    monkeypatch.setattr(rules_mod, "session_scope", lambda db_url: _Ctx(session))

    repo = PostgresRulesRepository("postgresql://example")
    payload = asyncio.run(repo.compare_rule_versions("rule-1", "v1", "v2"))

    assert payload is not None
    assert payload["changes"]["summary"]["totalChanges"] >= 2


def test_get_rule_version_statistics_returns_none_when_rule_missing(monkeypatch) -> None:
    session = _Session()
    monkeypatch.setattr(rules_mod, "session_scope", lambda db_url: _Ctx(session))
    monkeypatch.setattr(PostgresRulesRepository, "_get_rule_row", staticmethod(lambda _s, _id: None))

    repo = PostgresRulesRepository("postgresql://example")
    assert asyncio.run(repo.get_rule_version_statistics("missing")) is None


def test_get_rule_version_statistics_aggregates_counts(monkeypatch) -> None:
    versions = [
        _version_row("v1", 1),
        _version_row("v2", 2),
    ]
    versions[1].change_type = None
    versions[1].active = False
    versions[1].marked_for_rollback = True
    rollbacks = [
        SimpleNamespace(to_version_id="v1"),
        SimpleNamespace(to_version_id=""),
    ]

    session = _Session(scalar_values=[versions, rollbacks])
    monkeypatch.setattr(rules_mod, "session_scope", lambda db_url: _Ctx(session))
    monkeypatch.setattr(PostgresRulesRepository, "_get_rule_row", staticmethod(lambda _s, _id: _rule_row()))

    repo = PostgresRulesRepository("postgresql://example")
    payload = asyncio.run(repo.get_rule_version_statistics("rule-1"))

    assert payload is not None
    assert payload["versions"]["total"] == 2
    assert payload["versions"]["markedForRollback"] == 1
    assert payload["rollbacks"]["rollbackTargets"]["v1"] == 1


def test_execute_rule_rollback_returns_none_when_rule_missing(monkeypatch) -> None:
    session = _Session()
    monkeypatch.setattr(rules_mod, "session_scope", lambda db_url: _Ctx(session))
    monkeypatch.setattr(PostgresRulesRepository, "_get_rule_row", staticmethod(lambda _s, _id: None))

    repo = PostgresRulesRepository("postgresql://example")
    payload = asyncio.run(repo.execute_rule_rollback("rule-1", "v1", "reason"))
    assert payload is None


def test_execute_rule_rollback_rejects_invalid_states(monkeypatch) -> None:
    session = _Session()
    monkeypatch.setattr(rules_mod, "session_scope", lambda db_url: _Ctx(session))

    repo = PostgresRulesRepository("postgresql://example")

    same_rule = _rule_row()
    same_rule.current_version_id = "v1"
    monkeypatch.setattr(PostgresRulesRepository, "_get_rule_row", staticmethod(lambda _s, _id: same_rule))
    with pytest.raises(ValueError):
        asyncio.run(repo.execute_rule_rollback("rule-1", "v1", "reason"))

    no_current = _rule_row()
    no_current.current_version_id = None
    monkeypatch.setattr(PostgresRulesRepository, "_get_rule_row", staticmethod(lambda _s, _id: no_current))
    with pytest.raises(ValueError):
        asyncio.run(repo.execute_rule_rollback("rule-1", "v2", "reason"))


def test_execute_rule_rollback_rejects_missing_target(monkeypatch) -> None:
    session = _Session(scalar_values=[None])
    monkeypatch.setattr(rules_mod, "session_scope", lambda db_url: _Ctx(session))

    rule = _rule_row()
    rule.current_version_id = "v1"
    monkeypatch.setattr(PostgresRulesRepository, "_get_rule_row", staticmethod(lambda _s, _id: rule))

    repo = PostgresRulesRepository("postgresql://example")
    with pytest.raises(LookupError):
        asyncio.run(repo.execute_rule_rollback("rule-1", "v2", "reason"))


def test_execute_rule_rollback_success_uses_fallback_timestamp(monkeypatch) -> None:
    target = _version_row("v2", 2)
    session = _Session(scalar_values=[target], gets={(rules_mod.RuleCurrentVersionRow, "rule-1"): SimpleNamespace(rule_id="rule-1", version_id="v1")})
    monkeypatch.setattr(rules_mod, "session_scope", lambda db_url: _Ctx(session))

    rule = _rule_row()
    rule.current_version_id = "v1"
    rule.total_versions = 2
    monkeypatch.setattr(PostgresRulesRepository, "_get_rule_row", staticmethod(lambda _s, _id: rule))
    monkeypatch.setattr(PostgresRulesRepository, "_to_text", staticmethod(lambda _v: None))
    monkeypatch.setattr(PostgresRulesRepository, "_load_creator_names", staticmethod(lambda _s, _ids: {"user-admin": "Admin"}))
    monkeypatch.setattr(PostgresRulesRepository, "_load_version_numbers", staticmethod(lambda _s, _ids: {"v1": 2}))

    repo = PostgresRulesRepository("postgresql://example")
    payload = asyncio.run(repo.execute_rule_rollback("rule-1", "v2", "reason", skip_approval=True))

    assert payload is not None
    assert payload["newVersionCreated"]["status"] == "activated"
    assert payload["rolledBackBy"]["name"] == "Admin"
    assert session.flush_calls == 1


def test_update_rule_version_tags_and_mark_for_rollback_none_paths(monkeypatch) -> None:
    session = _Session(scalar_values=[None, None])
    monkeypatch.setattr(rules_mod, "session_scope", lambda db_url: _Ctx(session))

    repo = PostgresRulesRepository("postgresql://example")
    assert asyncio.run(repo.update_rule_version_tags("rule-1", "missing", ["a"])) is None
    assert asyncio.run(repo.mark_rule_version_for_rollback("rule-1", "missing", True)) is None


def test_reusable_asset_delete_branches(monkeypatch) -> None:
    # filter: missing row -> False
    session_filter_missing = _Session(scalar_values=[None])
    monkeypatch.setattr(rules_mod, "session_scope", lambda db_url: _Ctx(session_filter_missing))
    repo = PostgresRulesRepository("postgresql://example")
    assert asyncio.run(repo.delete_reusable_filter("rf-missing")) is False

    # filter: in use -> ValueError
    session_filter_in_use = _Session(scalar_values=[SimpleNamespace(id="rf-1"), SimpleNamespace(id="link")])
    monkeypatch.setattr(rules_mod, "session_scope", lambda db_url: _Ctx(session_filter_in_use))
    with pytest.raises(ValueError):
        asyncio.run(repo.delete_reusable_filter("rf-1"))

    # join: missing row -> False
    session_join_missing = _Session(scalar_values=[None])
    monkeypatch.setattr(rules_mod, "session_scope", lambda db_url: _Ctx(session_join_missing))
    assert asyncio.run(repo.delete_reusable_join("rj-missing")) is False

    # join: in use -> ValueError
    session_join_in_use = _Session(scalar_values=[SimpleNamespace(id="rj-1"), SimpleNamespace(id="rule")])
    monkeypatch.setattr(rules_mod, "session_scope", lambda db_url: _Ctx(session_join_in_use))
    with pytest.raises(ValueError):
        asyncio.run(repo.delete_reusable_join("rj-1"))


def test_helper_branches_for_username_tags_and_lookup_loading(monkeypatch) -> None:
    repo = PostgresRulesRepository("postgresql://example")

    assert repo._display_name_for_tag("tag") == "tag"
    assert repo._display_name_for_tag("abc-def") == "ABC DEF"

    assert repo._username_for_user(SimpleNamespace(email="a@b.com", name="", id="u1")) == "a"
    assert repo._username_for_user(SimpleNamespace(email="", name="Jane Doe", id="u2")) == "jane-doe"
    assert repo._username_for_user(SimpleNamespace(email="", name="", id="u3")) == "u3"

    assert asyncio.run(repo.get_tags_by_ids(["", " tag_quality "]))[0].name == "Quality"

    empty_session = _Session()
    assert repo._load_creator_names(empty_session, []) == {}
    assert repo._load_version_numbers(empty_session, set()) == {}

    non_empty = _Session(
        scalar_values=[
            [SimpleNamespace(id="u1", name="User One", email="u1@example.com")],
            [SimpleNamespace(id="v1", version_number=7)],
        ]
    )
    assert repo._load_creator_names(non_empty, ["u1"]) == {"u1": "User One"}
    assert repo._load_version_numbers(non_empty, {"v1"}) == {"v1": 7}


def test_to_rule_entity_created_by_fallback() -> None:
    repo = PostgresRulesRepository("postgresql://example")
    row = _rule_row()
    row.created_by = ""
    row.lifecycle_status = "deprecated"

    entity = repo._to_rule_entity(row)
    assert entity.created_by_user_id == "user-admin"
    assert entity.lifecycle_status == "deprecated"


def test_activate_deactivate_and_save_template_success_paths(monkeypatch) -> None:
    row_active = _rule_row()
    row_active.validation_status = None
    row_active.validated_at = None
    row_inactive = _rule_row()
    row_template_source = _rule_row()

    session = _Session(scalar_values=[row_active, row_inactive, row_template_source])
    monkeypatch.setattr(rules_mod, "session_scope", lambda db_url: _Ctx(session))

    repo = PostgresRulesRepository("postgresql://example")
    activated = asyncio.run(repo.activate_rule_record("rule-1"))
    deactivated = asyncio.run(repo.deactivate_rule("rule-1"))
    template = asyncio.run(
        repo.save_rule_as_template(
            rule_id="rule-1",
            template_name="Template One",
            template_description="desc",
            created_by="user-admin",
        )
    )

    assert activated is not None
    assert activated.active is True
    assert activated.last_approval_status == "approved"
    assert activated.validation_status == "valid"

    assert deactivated is not None
    assert deactivated["ok"] is True
    assert deactivated["active"] is False
    assert deactivated["last_approval_status"] == "deactivated"

    assert template is not None
    assert template["ok"] is True
    assert template["is_template"] is True


def test_soft_delete_and_recover_rule_success_paths(monkeypatch) -> None:
    removable = _rule_row()
    removable.active = False
    removable.last_approval_status = "deactivated"
    removed = _rule_row()
    removed.deleted_on = "2026-01-01T00:00:00+00:00"
    removed.deleted_by = "user-admin"

    session_remove = _Session(scalar_values=[removable])
    monkeypatch.setattr(rules_mod, "session_scope", lambda db_url: _Ctx(session_remove))

    repo = PostgresRulesRepository("postgresql://example")
    removed_payload = asyncio.run(repo.soft_delete_rule_record("rule-1", removed_by="user-admin"))

    assert removed_payload is not None
    assert removed_payload.removed is True
    assert removed_payload.removed_by == "user-admin"
    assert removed_payload.last_approval_status == "removed"

    session_recover = _Session(scalar_values=[removed])
    monkeypatch.setattr(rules_mod, "session_scope", lambda db_url: _Ctx(session_recover))
    recovered_payload = asyncio.run(repo.recover_rule("rule-1", recovered_by="user-admin"))

    assert recovered_payload is not None
    assert recovered_payload["ok"] is True
    assert recovered_payload["removed"] is False
    assert recovered_payload["active"] is False
    assert recovered_payload["last_approval_status"] == "recovered"


def test_soft_delete_rule_requires_deactivated_state(monkeypatch) -> None:
    active_row = _rule_row()
    session = _Session(scalar_values=[active_row])
    monkeypatch.setattr(rules_mod, "session_scope", lambda db_url: _Ctx(session))

    repo = PostgresRulesRepository("postgresql://example")
    with pytest.raises(ValueError, match="deactivated"):
        asyncio.run(repo.soft_delete_rule_record("rule-1", removed_by="user-admin"))


@pytest.mark.parametrize(
    ("to_status", "expected_action"),
    [
        ("approved", "approve"),
        ("rejected", "reject"),
    ],
)
def test_record_rule_status_transition_updates_rule_row(monkeypatch, to_status: str, expected_action: str) -> None:
    row = _rule_row()
    row.active = False
    row.last_approval_status = "pending-approval"
    session = _Session(scalar_values=[row])
    monkeypatch.setattr(rules_mod, "session_scope", lambda db_url: _Ctx(session))

    repo = PostgresRulesRepository("postgresql://example")
    payload = asyncio.run(
        repo.record_rule_status_transition(
            "rule-1",
            "pending-approval",
            to_status,
            changed_by="reviewer-1",
            reason="Approval reviewed",
        )
    )

    assert payload is not None
    assert row.last_approval_status == to_status
    assert row.last_approval_by == "reviewer-1"
    assert row.last_approval_at is not None
    assert len(session.added) == 1
    assert session.added[0].action == expected_action


@pytest.mark.parametrize(
    ("lifecycle_status", "expected_action"),
    [
        ("deprecated", "deprecate"),
        ("superseded", "supersede"),
        ("retired", "retire"),
    ],
)
def test_set_rule_lifecycle_status_records_lifecycle_action(
    monkeypatch,
    lifecycle_status: str,
    expected_action: str,
) -> None:
    row = _rule_row()
    row.active = False
    row.current_version_id = None
    session = _Session(scalar_values=[row])
    monkeypatch.setattr(rules_mod, "session_scope", lambda db_url: _Ctx(session))

    repo = PostgresRulesRepository("postgresql://example")
    payload = asyncio.run(
        repo.set_rule_lifecycle_status(
            "rule-1",
            lifecycle_status=lifecycle_status,
            changed_by="user-admin",
            reason="Lifecycle review",
        )
    )

    assert payload is not None
    assert payload.lifecycle_status == lifecycle_status
    assert len(session.added) == 1
    assert session.added[0].action == expected_action


def test_get_rule_rollback_history_success_path(monkeypatch) -> None:
    rollback_rows = [
        SimpleNamespace(
            id="rb-1",
            rule_id="rule-1",
            from_version_id="v2",
            to_version_id="v1",
            rolled_back_by="user-admin",
            rolled_back_at=None,
            reason="stability",
            new_version_created_id="v3",
        )
    ]
    session = _Session(scalar_values=[rollback_rows])
    monkeypatch.setattr(rules_mod, "session_scope", lambda db_url: _Ctx(session))
    monkeypatch.setattr(PostgresRulesRepository, "_get_rule_row", staticmethod(lambda _s, _id: _rule_row()))

    repo = PostgresRulesRepository("postgresql://example")
    payload = asyncio.run(repo.get_rule_rollback_history("rule-1", limit=10, offset=0))

    assert payload is not None
    assert payload["ruleId"] == "rule-1"
    assert payload["pagination"]["total"] == 1
    assert payload["rollbacks"][0]["id"] == "rb-1"


def test_update_tags_and_mark_for_rollback_success_paths(monkeypatch) -> None:
    repo = PostgresRulesRepository("postgresql://example")

    session_tags = _Session(
        scalar_values=[
            _version_row("v1", 1),
            [],
            [SimpleNamespace(id="user-admin", name="Platform Admin", email="admin@example.com")],
        ]
    )
    monkeypatch.setattr(rules_mod, "session_scope", lambda db_url: _Ctx(session_tags))
    updated_tags = asyncio.run(
        repo.update_rule_version_tags("rule-1", "v1", ["critical"], updated_by_user_id="user-admin")
    )

    assert updated_tags is not None
    assert updated_tags["id"] == "v1"
    assert updated_tags["tags"] == ["critical"]
    assert updated_tags["updatedBy"]["id"] == "user-admin"

    session_mark = _Session(scalar_values=[_version_row("v1", 1), []])
    monkeypatch.setattr(rules_mod, "session_scope", lambda db_url: _Ctx(session_mark))
    updated_mark = asyncio.run(repo.mark_rule_version_for_rollback("rule-1", "v1", True))

    assert updated_mark is not None
    assert updated_mark["id"] == "v1"
    assert updated_mark["marked"] is True


def test_set_current_rule_version_validation_variants(monkeypatch) -> None:
    repo = PostgresRulesRepository("postgresql://example")

    session_none = _Session()
    monkeypatch.setattr(rules_mod, "session_scope", lambda db_url: _Ctx(session_none))
    monkeypatch.setattr(PostgresRulesRepository, "_get_rule_row", staticmethod(lambda _s, _id: None))
    assert asyncio.run(
        repo.set_current_rule_version_validation(rule_id="rule-1", validation_status="valid", validated_by=None)
    ) is None

    row_no_current = _rule_row()
    row_no_current.current_version_id = None
    session_no_current = _Session()
    monkeypatch.setattr(rules_mod, "session_scope", lambda db_url: _Ctx(session_no_current))
    monkeypatch.setattr(PostgresRulesRepository, "_get_rule_row", staticmethod(lambda _s, _id: row_no_current))
    assert asyncio.run(
        repo.set_current_rule_version_validation(rule_id="rule-1", validation_status="valid", validated_by=None)
    ) is None

    row_missing_version = _rule_row()
    row_missing_version.current_version_id = "v1"
    session_missing_version = _Session(scalar_values=[None])
    monkeypatch.setattr(rules_mod, "session_scope", lambda db_url: _Ctx(session_missing_version))
    monkeypatch.setattr(PostgresRulesRepository, "_get_rule_row", staticmethod(lambda _s, _id: row_missing_version))
    assert asyncio.run(
        repo.set_current_rule_version_validation(rule_id="rule-1", validation_status="valid", validated_by="user-admin")
    ) is None

    row_ok = _rule_row()
    row_ok.current_version_id = "v1"
    version_row = _version_row("v1", 1)
    session_ok = _Session(scalar_values=[version_row])
    monkeypatch.setattr(rules_mod, "session_scope", lambda db_url: _Ctx(session_ok))
    monkeypatch.setattr(PostgresRulesRepository, "_get_rule_row", staticmethod(lambda _s, _id: row_ok))

    payload = asyncio.run(
        repo.set_current_rule_version_validation(
            rule_id="rule-1",
            validation_status="approved",
            validated_by="user-admin",
        )
    )
    assert payload is not None
    assert payload["ruleId"] == "rule-1"
    assert payload["versionId"] == "v1"
    assert payload["validationStatus"] == "approved"


def test_compiler_artifact_and_reusable_assets_success_paths(monkeypatch) -> None:
    repo = PostgresRulesRepository("postgresql://example")

    session_active_none = _Session(scalar_values=[None])
    monkeypatch.setattr(rules_mod, "session_scope", lambda db_url: _Ctx(session_active_none))
    assert asyncio.run(repo.get_active_compiler_artifact("rv-missing")) is None

    reusable_filter_row = SimpleNamespace(
        id="rf-1",
        name="Filter One",
        description="desc",
        filter_expression="status = 'A'",
        workspace="default",
        created_by="user-admin",
        active=True,
        created_at=None,
        updated_at=None,
    )
    reusable_join_row = SimpleNamespace(
        id="rj-1",
        name="Join One",
        description="desc",
        join_definition="left.id = right.id",
        workspace="default",
        created_by="user-admin",
        active=True,
        created_at=None,
        updated_at=None,
    )
    session_filters = _Session(scalar_values=[[reusable_filter_row]])
    monkeypatch.setattr(rules_mod, "session_scope", lambda db_url: _Ctx(session_filters))
    filters = asyncio.run(repo.list_reusable_filters(workspace="default"))

    session_joins = _Session(scalar_values=[[reusable_join_row]])
    monkeypatch.setattr(rules_mod, "session_scope", lambda db_url: _Ctx(session_joins))
    joins = asyncio.run(repo.list_reusable_joins(workspace="default"))

    session_create_filter = _Session()
    monkeypatch.setattr(rules_mod, "session_scope", lambda db_url: _Ctx(session_create_filter))
    created_filter = asyncio.run(
        repo.create_reusable_filter(
            name="Filter New",
            expression="status = 'B'",
            description=None,
            workspace="default",
            created_by="user-admin",
            active=True,
        )
    )

    session_create_join = _Session()
    monkeypatch.setattr(rules_mod, "session_scope", lambda db_url: _Ctx(session_create_join))
    created_join = asyncio.run(
        repo.create_reusable_join(
            name="Join New",
            join_definition="left.id = right.id",
            description=None,
            workspace="default",
            created_by="user-admin",
            active=True,
        )
    )

    session_delete_filter = _Session(scalar_values=[reusable_filter_row, None])
    monkeypatch.setattr(rules_mod, "session_scope", lambda db_url: _Ctx(session_delete_filter))
    deleted_filter = asyncio.run(repo.delete_reusable_filter("rf-1"))

    session_delete_join = _Session(scalar_values=[reusable_join_row, None])
    monkeypatch.setattr(rules_mod, "session_scope", lambda db_url: _Ctx(session_delete_join))
    deleted_join = asyncio.run(repo.delete_reusable_join("rj-1"))

    assert filters[0]["id"] == "rf-1"
    assert joins[0]["id"] == "rj-1"
    assert created_filter["id"].startswith("rf_")
    assert created_join["id"].startswith("rj_")
    assert deleted_filter is True
    assert deleted_join is True


def test_get_user_and_json_parse_fallback_paths(monkeypatch) -> None:
    session = _Session(gets={(rules_mod.UserRow, "missing"): None})
    monkeypatch.setattr(rules_mod, "session_scope", lambda db_url: _Ctx(session))
    repo = PostgresRulesRepository("postgresql://example")
    assert asyncio.run(repo.get_user_by_id("missing")) is None

    bad_version = _version_row("v-bad", 9)
    bad_version.check_type_params = "{bad-json"
    detail = repo._serialize_version_detail(
        bad_version,
        created_by_name="Admin",
        validated_by_name="",
    )
    assert detail["checkTypeParams"] is None

    bad_rule = _rule_row()
    bad_rule.check_type_params = "{bad-json"
    entity = repo._to_rule_entity(bad_rule)
    assert entity.check_type_params is None