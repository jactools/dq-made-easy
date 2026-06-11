import json
from contextlib import contextmanager

from app.infrastructure.repositories.postgres_approvals_repository import PostgresApprovalsRepository


def test_postgres_approvals_repository_parsing_helpers(
    postgres_dsn: str,
    approval_pg_row: dict[str, object],
) -> None:
    repository = PostgresApprovalsRepository(postgres_dsn)

    mapped = repository._to_approval_entity(approval_pg_row)
    assert mapped.id == "approval-1"
    assert mapped.businessKey == "approval-1"
    assert mapped.ruleId == "rule-1"
    assert mapped.effectiveStatus == "activated"
    assert repository._parse_json_object('{"a": 1}') == {"a": 1}
    assert repository._parse_json_object("bad-json") == {}


def test_postgres_approvals_repository_update_permission_guard(
    postgres_dsn: str,
    approval_pg_row: dict[str, object],
    approval_status_update_payload: dict[str, object],
) -> None:
    repository = PostgresApprovalsRepository(postgres_dsn)
    repository._fetch_one = lambda approval_id: {**approval_pg_row, "id": approval_id}  # type: ignore[method-assign]

    try:
        repository.update_approval("approval-1", approval_status_update_payload, actor_id="user-1")
    except PermissionError as error:
        assert str(error) == "Requester cannot approve their own request"
    else:
        raise AssertionError("Expected PermissionError")


def test_postgres_approvals_repository_delete_permission_guard(
    postgres_dsn: str,
    approval_requester_only_row: dict[str, object],
) -> None:
    repository = PostgresApprovalsRepository(postgres_dsn)
    repository._fetch_one = lambda approval_id: {**approval_requester_only_row, "id": approval_id}  # type: ignore[method-assign]

    try:
        repository.delete_approval("approval-1", actor_id="someone-else")
    except PermissionError as error:
        assert str(error) == "Only requester can cancel"
    else:
        raise AssertionError("Expected PermissionError")


def test_postgres_approvals_repository_create_uses_session_and_returns_entity(
    monkeypatch,
    postgres_dsn: str,
    approval_create_payload: dict[str, object],
    approval_created_row: dict[str, object],
) -> None:
    import app.infrastructure.repositories.postgres_approvals_repository as approvals_module

    repository = PostgresApprovalsRepository(postgres_dsn)

    class FakeSession:
        def add(self, _obj) -> None:
            return None

        def commit(self) -> None:
            return None

    @contextmanager
    def fake_scope(_database_url: str):
        yield FakeSession()

    monkeypatch.setattr(approvals_module, "session_scope", fake_scope)
    repository._fetch_one = lambda approval_id: {**approval_created_row, "id": approval_id}  # type: ignore[method-assign]

    created = repository.create_approval(approval_create_payload, actor_id="user-admin")
    assert created.businessKey == "approval-1"
    assert created.ruleId == "rule-new"
    assert created.effectiveStatus == "activated"


def test_postgres_approvals_repository_serializes_gx_run_plan_identifiers(
    postgres_dsn: str,
) -> None:
    repository = PostgresApprovalsRepository(postgres_dsn)

    mapped = repository._to_approval_entity(
        {
            "id": "approval-1",
            "business_key": "approval-1",
            "ruleid": "",
            "effectivestatus": "deactivated",
            "gxrunplanid": "run-plan-1",
            "gxrunplanversionid": "run-plan-version-1",
            "status": "pending",
            "requesterid": "user-1",
            "workspace_id": "default",
        }
    )

    assert mapped.effectiveStatus == "deactivated"
    assert mapped.businessKey == "approval-1"
    assert mapped.gxRunPlanId == "run-plan-1"
    assert mapped.gxRunPlanVersionId == "run-plan-version-1"


def test_postgres_approvals_repository_update_records_effective_status_in_audit(
    monkeypatch,
    postgres_dsn: str,
    approval_pg_row: dict[str, object],
    approval_status_update_payload: dict[str, object],
) -> None:
    import app.infrastructure.repositories.postgres_approvals_repository as approvals_module

    repository = PostgresApprovalsRepository(postgres_dsn)
    audit_rows: list[object] = []

    class FakeResult:
        rowcount = 1

    class FakeSession:
        def execute(self, _statement):
            return FakeResult()

        def add(self, obj) -> None:
            audit_rows.append(obj)

        def commit(self) -> None:
            return None

        def rollback(self) -> None:
            return None

    @contextmanager
    def fake_scope(_database_url: str):
        yield FakeSession()

    fetch_rows = iter(
        [
            {**approval_pg_row, "id": "approval-1", "status": "pending", "effective_status": "activated"},
            {**approval_pg_row, "id": "approval-1", "status": "approved", "effective_status": "activated"},
        ]
    )
    monkeypatch.setattr(approvals_module, "session_scope", fake_scope)
    repository._fetch_one = lambda approval_id: next(fetch_rows)  # type: ignore[method-assign]

    updated = repository.update_approval("approval-1", approval_status_update_payload, actor_id="reviewer-1")

    assert updated is not None
    assert updated.status == "approved"
    assert len(audit_rows) == 1
    assert json.loads(audit_rows[0].details)["effective_status"] == "activated"


def test_postgres_approvals_repository_update_delete_return_none_for_missing(
    postgres_dsn: str,
    approval_status_update_payload: dict[str, object],
) -> None:
    repository = PostgresApprovalsRepository(postgres_dsn)
    repository._fetch_one = lambda approval_id: None  # type: ignore[method-assign]

    assert repository.update_approval("missing", approval_status_update_payload, actor_id="reviewer") is None
    assert repository.delete_approval("missing", actor_id="reviewer") is None
