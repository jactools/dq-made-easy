from __future__ import annotations

from contextlib import contextmanager
from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace

import pytest

import app.infrastructure.orm.session as orm_session
import app.infrastructure.repositories.postgres_admin_repository as admin_mod
import app.infrastructure.repositories.postgres_app_config_repository as appcfg_mod
import app.infrastructure.repositories.postgres_data_catalog_repository as catalog_mod
import app.infrastructure.repositories.postgres_testing_repository as testing_mod
from app.infrastructure.repositories.postgres_admin_repository import PostgresAdminRepository
from app.infrastructure.repositories.postgres_app_config_repository import PostgresAppConfigRepository
from app.infrastructure.repositories.postgres_data_catalog_repository import PostgresDataCatalogRepository
from app.infrastructure.repositories.postgres_testing_repository import PostgresTestingRepository


def test_orm_session_normalize_database_url_and_compile_positional_query() -> None:
    assert orm_session.normalize_database_url("postgresql://user:pw@host/db") == "postgresql+psycopg://user:pw@host/db"
    assert orm_session.normalize_database_url("postgresql+psycopg://user:pw@host/db") == "postgresql+psycopg://user:pw@host/db"
    assert orm_session.normalize_database_url("sqlite:///tmp.db") == "sqlite:///tmp.db"

    unchanged, binds = orm_session.compile_positional_query("select 1", None)
    assert unchanged == "select 1"
    assert binds == {}

    query, params = orm_session.compile_positional_query(
        "select * from t where a=%s and b=%s",
        ["x", 2],
    )
    assert query == "select * from t where a=:p0 and b=:p1"
    assert params == {"p0": "x", "p1": 2}

    with pytest.raises(ValueError):
        orm_session.compile_positional_query("select * from t where a=%s", ["x", "y"])


def test_postgres_admin_repository_preference_and_workspace_helpers() -> None:
    repo = PostgresAdminRepository("postgresql://example")

    assert repo._decode_preferences('{"a":1}') == {"a": 1}
    assert repo._decode_preferences("{broken") is None
    assert repo._encode_preferences({"k": "v"}) == '{"k": "v"}'
    assert repo._encode_preferences(None) is None

    # Covers the fallback branch where legacy payloads use singular workspace.
    assert repo._parse_workspaces({"workspace": "default"}) == ["default"]


def test_postgres_admin_repository_update_current_user_raises_when_write_not_persisted(monkeypatch) -> None:
    repo = PostgresAdminRepository("postgresql://example")

    monkeypatch.setattr(
        repo,
        "_find_current_user",
        lambda user_id, claims: {"id": "u1", "preferences": None},
    )

    class _Session:
        def execute(self, _stmt):
            return SimpleNamespace(rowcount=0)

        def commit(self):
            return None

    @contextmanager
    def _scope(_dsn: str):
        yield _Session()

    monkeypatch.setattr(admin_mod, "session_scope", _scope)

    with pytest.raises(RuntimeError):
        repo.update_current_user("u1", None, {"preferences": {"theme": "dark"}})


def test_postgres_admin_repository_assert_workspace_capacity_enforced(monkeypatch) -> None:
    repo = PostgresAdminRepository("postgresql://example")

    class _Session:
        def execute(self, _stmt):
            return SimpleNamespace(
                all=lambda: [
                    ("u-other-1", "default;w2"),
                    ("u-other-2", "default"),
                    ("u-target", "default"),  # target user should be ignored
                ]
            )

    @contextmanager
    def _scope(_dsn: str):
        yield _Session()

    monkeypatch.setattr(admin_mod, "session_scope", _scope)

    with pytest.raises(ValueError):
        repo._assert_workspace_capacity("u-target", ["default"], max_users_per_workspace=2)


def test_postgres_data_catalog_add_rule_attributes_continues_on_exception(monkeypatch) -> None:
    repo = PostgresDataCatalogRepository("postgresql://example")

    class _SessionOK:
        def __init__(self):
            self.added = 0
            self.committed = 0

        def execute(self, _stmt):
            return SimpleNamespace(scalars=lambda: SimpleNamespace(all=lambda: []))

        def add(self, _obj):
            self.added += 1

        def commit(self):
            self.committed += 1

    class _SessionFail:
        def add(self, _obj):
            raise RuntimeError("insert failed")

        def commit(self):
            return None

    sessions = [_SessionFail(), _SessionOK()]

    @contextmanager
    def _scope(_dsn: str):
        yield sessions.pop(0)

    monkeypatch.setattr(catalog_mod, "session_scope", _scope)

    result = repo.add_rule_attributes(
        [
            {"ruleId": "r1", "attributeId": "a1"},
            {"ruleId": "r2", "attributeId": "a2"},
        ]
    )

    assert result.added == 1


def test_postgres_data_catalog_to_text_additional_types() -> None:
    repo = PostgresDataCatalogRepository("postgresql://example")

    assert repo._to_text(Decimal("3.14")) == "3.14"
    assert repo._to_text(datetime(2026, 3, 15, tzinfo=UTC)).startswith("2026-03-15")


def test_postgres_testing_repository_matcher_fallback_and_type_guards() -> None:
    repo = PostgresTestingRepository("postgresql://example")

    fallback = repo._build_rule_matcher("unsupported expression")
    with pytest.raises(ValueError):
        fallback({"anything": "goes"})

    regex = repo._build_rule_matcher("email ~ '.*@.*'")
    assert regex({"email": 123}) is False

    contains = repo._build_rule_matcher("email contains '@'")
    assert contains({"email": None}) is False


def test_postgres_testing_repository_store_test_proof_zero_records() -> None:
    class _Session:
        def add(self, _row):
            return None

        def commit(self):
            return None

    @contextmanager
    def _scope(_dsn: str):
        yield _Session()

    testing_mod.session_scope = _scope
    repo = PostgresTestingRepository("postgresql://example")

    out = repo.store_test_proof(
        "r1",
        {
            "recordsTestedCount": 0,
            "failuresFound": 5,
            "coverage": 50.0,
            "passed": False,
            "proofData": {},
        },
    )

    assert out.recordsTestedCount == 0
    assert out.successRate == 0
    assert out.proofData["executionTrace"]["resultStatus"] == "failed"


def test_postgres_testing_repository_get_batch_request_maps_optional_proof_id(monkeypatch) -> None:
    repo = PostgresTestingRepository("postgresql://example")

    row = SimpleNamespace(
        id="b1",
        rule_id="r1",
        requested_by="u1",
        requested_at=datetime(2026, 3, 15, tzinfo=UTC),
        test_data_config={"sampleCount": 3},
        status="completed",
        workspace="default",
        completed_at=datetime(2026, 3, 15, tzinfo=UTC),
        proof_id="proof-1",
    )

    class _Session:
        def get(self, _model, _key):
            return row

    @contextmanager
    def _scope(_dsn: str):
        yield _Session()

    monkeypatch.setattr(testing_mod, "session_scope", _scope)

    out = repo.get_batch_test_request("b1")

    assert out is not None
    assert out.proofId == "proof-1"


def test_postgres_app_config_get_parses_number_and_false_boolean() -> None:
    repo = PostgresAppConfigRepository("postgresql://example")
    repo._fetch_all = lambda: [  # type: ignore[method-assign]
        {"config_key": "api_retry_delay", "config_value": "2500", "value_type": "number"},
        {"config_key": "enable_export", "config_value": "0", "value_type": "boolean"},
    ]

    out = repo.get_app_config()

    assert out.apiRetryDelay == 2500
    assert out.enableExport is False
    assert repo._coerce_value("2500.5", "number") == 2500.5


def test_postgres_app_config_set_accepts_snake_case_keys(monkeypatch) -> None:
    repo = PostgresAppConfigRepository("postgresql://example")
    captured: list[tuple[str, str | None, str]] = []

    repo._upsert = lambda key, value, kind: captured.append((key, value, kind))  # type: ignore[method-assign]
    repo.get_app_config = lambda: {"apiVersion": "v1"}  # type: ignore[method-assign]

    repo.set_app_config({"maintenance_mode": "true", "default_page_size": "30"})

    assert ("maintenance_mode", "true", "boolean") in captured
    assert ("default_page_size", "30", "number") in captured


def test_postgres_app_config_fetch_all_maps_rows_from_session(monkeypatch) -> None:
    repo = PostgresAppConfigRepository("postgresql://example")
    rows = [
        SimpleNamespace(config_key="api_version", config_value="v2", value_type="string"),
        SimpleNamespace(config_key="enable_export", config_value="false", value_type="boolean"),
    ]

    class _Session:
        def execute(self, _stmt):
            return SimpleNamespace(scalars=lambda: SimpleNamespace(all=lambda: rows))

    @contextmanager
    def _scope(_dsn: str):
        yield _Session()

    monkeypatch.setattr(appcfg_mod, "session_scope", _scope)

    out = repo._fetch_all()

    assert out[0]["config_key"] == "api_version"
    assert out[1]["value_type"] == "boolean"


def test_postgres_app_config_upsert_executes_statement_and_commits(monkeypatch) -> None:
    repo = PostgresAppConfigRepository("postgresql://example")
    recorded = {"executed": 0, "commits": 0}

    class _FakeStmt:
        class _Excluded:
            config_value = "excluded_config_value"
            value_type = "excluded_value_type"

        excluded = _Excluded()

        def values(self, **_kwargs):
            return self

        def on_conflict_do_update(self, **_kwargs):
            return self

    class _Session:
        def execute(self, _stmt):
            recorded["executed"] += 1

        def commit(self):
            recorded["commits"] += 1

    @contextmanager
    def _scope(_dsn: str):
        yield _Session()

    monkeypatch.setattr(appcfg_mod, "insert", lambda _model: _FakeStmt())
    monkeypatch.setattr(appcfg_mod, "session_scope", _scope)

    repo._upsert("api_version", "v2", "string")

    assert recorded == {"executed": 1, "commits": 1}


def test_postgres_app_config_infer_type_and_json_passthrough() -> None:
    repo = PostgresAppConfigRepository("postgresql://example")

    assert repo._infer_type("defaultPageSize") == "number"
    assert repo._infer_type("enableExport") == "boolean"
    assert repo._infer_type("validationPolicies") == "json"
    assert repo._infer_type("apiVersion") == "string"
    assert repo._coerce_value({"a": 1}, "json") == {"a": 1}


def test_postgres_data_catalog_lists_objects_catalog_and_attributes(monkeypatch) -> None:
    repo = PostgresDataCatalogRepository("postgresql://example")

    object_row = SimpleNamespace(id="o1", name="Obj 1", description="Desc")
    catalog_row = SimpleNamespace(
        id="c1",
        dataset_id="ds1",
        name="Catalog 1",
        description="Catalog desc",
        icon="table",
        created_at=datetime(2026, 3, 15, tzinfo=UTC),
        latest_version_id="v2",
    )
    attr_row = SimpleNamespace(
        id="a1",
        name="email",
        type="text",
        nullable=False,
        format="email",
        is_cde=True,
        is_primary_key=False,
        data_object_id="c1",
        version_id="v2",
    )
    version_row = SimpleNamespace(id="v2", data_object_id="c1", version=2)

    scalar_batches = [[object_row], [catalog_row], [attr_row], [attr_row], [], [version_row]]

    class _Session:
        def execute(self, _stmt):
            batch = scalar_batches.pop(0)
            return SimpleNamespace(scalars=lambda: SimpleNamespace(all=lambda: batch))

    @contextmanager
    def _scope(_dsn: str):
        yield _Session()

    monkeypatch.setattr(catalog_mod, "session_scope", _scope)

    objects = repo.list_data_objects()
    catalog = repo.list_data_objects_catalog(data_set_id="ds1")
    attrs = repo.list_attributes_catalog(version_id="v2")

    assert objects[0].id == "o1"
    assert catalog[0].latest_version_id == "v2"
    assert attrs[0].is_cde is True
    assert attrs[0].version_id == "v2"


def test_postgres_data_catalog_list_data_deliveries_without_version_filter(monkeypatch) -> None:
    repo = PostgresDataCatalogRepository("postgresql://example")

    row = SimpleNamespace(
        id="d1",
        data_object_id="c1",
        version=2,
        timestamp=datetime(2026, 3, 15, tzinfo=UTC),
        record_count=150,
        size_bytes=2048,
        status="completed",
        attributes_count=7,
    )

    class _Session:
        def execute(self, _stmt):
            return SimpleNamespace(scalars=lambda: SimpleNamespace(all=lambda: [row]))

    @contextmanager
    def _scope(_dsn: str):
        yield _Session()

    monkeypatch.setattr(catalog_mod, "session_scope", _scope)

    out = repo.list_data_deliveries()
    assert out[0].version == 2
    assert out[0].record_count == 150


def test_postgres_testing_repository_lists_batch_requests_without_filters(monkeypatch) -> None:
    repo = PostgresTestingRepository("postgresql://example")

    row = SimpleNamespace(
        id="b2",
        rule_id="r2",
        requested_by="u2",
        requested_at=datetime(2026, 3, 15, tzinfo=UTC),
        test_data_config={"sampleCount": 5},
        status="pending",
        workspace="default",
        completed_at=None,
        proof_id=None,
    )

    class _Session:
        def execute(self, _stmt):
            return SimpleNamespace(scalars=lambda: SimpleNamespace(all=lambda: [row]))

    @contextmanager
    def _scope(_dsn: str):
        yield _Session()

    monkeypatch.setattr(testing_mod, "session_scope", _scope)

    out = repo.list_batch_test_requests()
    assert out[0].id == "b2"
    assert out[0].proofId is None


def test_postgres_testing_repository_list_test_proofs_failed_status(monkeypatch) -> None:
    repo = PostgresTestingRepository("postgresql://example")

    failed_row = SimpleNamespace(
        id="p2",
        rule_id="r2",
        test_date=datetime(2026, 3, 15, tzinfo=UTC),
        coverage=70.0,
        passed=False,
        records_tested_count=10,
        failures_found=3,
    )

    class _Session:
        def execute(self, _stmt):
            return SimpleNamespace(scalars=lambda: SimpleNamespace(all=lambda: [failed_row]))

    @contextmanager
    def _scope(_dsn: str):
        yield _Session()

    monkeypatch.setattr(testing_mod, "session_scope", _scope)

    out = repo.list_test_proofs("r2")
    assert out[0].status == "failed"
