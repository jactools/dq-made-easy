from types import SimpleNamespace

import app.infrastructure.repositories.postgres_workspaces_repository as workspaces_mod
from app.infrastructure.repositories.postgres_workspaces_repository import PostgresWorkspacesRepository


class _Ctx:
    def __init__(self, session) -> None:
        self.session = session

    def __enter__(self):
        return self.session

    def __exit__(self, exc_type, exc, tb):
        return False


def test_postgres_workspaces_repository_crud_mapping_and_limit(
    postgres_dsn: str,
    workspace_pg_default_row: dict[str, object],
    workspace_pg_create_payload: dict[str, object],
    workspace_pg_update_payload: dict[str, object],
    clone_payload,
) -> None:
    repository = PostgresWorkspacesRepository(postgres_dsn)

    called: list[str] = []

    repository._fetch_all = lambda: [clone_payload(workspace_pg_default_row)]  # type: ignore[method-assign]
    repository._count_workspaces = lambda: {"count": 1}  # type: ignore[method-assign]
    repository._fetch_one = lambda workspace_id: {**clone_payload(workspace_pg_default_row), "id": workspace_id} if workspace_id == "default" else None  # type: ignore[method-assign]
    repository._insert_workspace = lambda workspace_id, name, description: called.append("insert") or True  # type: ignore[method-assign]
    repository._update_workspace = lambda workspace_id, name, description: called.append("update") or True  # type: ignore[method-assign]
    repository._delete_workspace = lambda workspace_id: called.append("delete") or True  # type: ignore[method-assign]

    rows = repository.list_workspaces()
    created = repository.create_workspace(clone_payload(workspace_pg_create_payload), max_workspaces=5)
    updated = repository.update_workspace("default", clone_payload(workspace_pg_update_payload))
    deleted = repository.delete_workspace("workspace-pg")

    assert [row.model_dump() for row in rows] == [workspace_pg_default_row]
    assert created.model_dump() == {**workspace_pg_create_payload, "description": ""}
    assert updated is not None
    assert updated.model_dump() == {"id": "default", "name": "Default Updated", "description": "Default workspace"}
    assert deleted is True
    assert "insert" in called
    assert "update" in called
    assert "delete" in called


def test_postgres_workspaces_repository_enforces_limit(
    postgres_dsn: str,
    workspace_overflow_payload: dict[str, object],
    clone_payload,
) -> None:
    repository = PostgresWorkspacesRepository(postgres_dsn)
    repository._count_workspaces = lambda: {"count": 5}  # type: ignore[method-assign]

    try:
        repository.create_workspace(clone_payload(workspace_overflow_payload), max_workspaces=5)
    except ValueError as error:
        assert str(error) == "Workspace limit reached"
    else:
        raise AssertionError("Expected ValueError for workspace limit")


def test_postgres_workspaces_repository_update_raises_when_write_fails(
    postgres_dsn: str,
    workspace_pg_desc_row: dict[str, object],
    clone_payload,
) -> None:
    repository = PostgresWorkspacesRepository(postgres_dsn)
    repository._fetch_one = lambda workspace_id: clone_payload(workspace_pg_desc_row)  # type: ignore[method-assign]
    repository._update_workspace = lambda workspace_id, name, description: False  # type: ignore[method-assign]

    try:
        repository.update_workspace("default", {"name": "Updated"})
    except RuntimeError as error:
        assert str(error) == "Failed to update workspace"
    else:
        raise AssertionError("Expected RuntimeError when workspace update is not persisted")


def test_postgres_workspaces_repository_create_raises_when_insert_fails_with_generated_defaults(
    postgres_dsn: str,
) -> None:
    repository = PostgresWorkspacesRepository(postgres_dsn)
    repository._count_workspaces = lambda: None  # type: ignore[method-assign]
    repository._generated_id = staticmethod(lambda: "generated-workspace")  # type: ignore[method-assign]
    captured: list[tuple[str, str, str]] = []
    repository._insert_workspace = lambda workspace_id, name, description: captured.append((workspace_id, name, description)) or False  # type: ignore[method-assign]

    try:
        repository.create_workspace({}, max_workspaces=0)
    except RuntimeError as error:
        assert str(error) == "Failed to create workspace"
    else:
        raise AssertionError("Expected RuntimeError when workspace create is not persisted")

    assert captured == [("generated-workspace", "generated-workspace", "")]


def test_postgres_workspaces_repository_update_returns_none_when_missing(postgres_dsn: str) -> None:
    repository = PostgresWorkspacesRepository(postgres_dsn)
    repository._fetch_one = lambda workspace_id: None  # type: ignore[method-assign]

    assert repository.update_workspace("missing-workspace", {"name": "Updated"}) is None


def test_postgres_workspaces_repository_generated_id_uses_timestamp_and_random(monkeypatch) -> None:
    monkeypatch.setattr(workspaces_mod.time, "time", lambda: 1712345678.901)
    monkeypatch.setattr(workspaces_mod.random, "randint", lambda start, end: 4321)

    assert PostgresWorkspacesRepository._generated_id() == "1712345678901-4321"


def test_postgres_workspaces_repository_session_read_helpers(monkeypatch, postgres_dsn: str) -> None:
    repository = PostgresWorkspacesRepository(postgres_dsn)
    row = SimpleNamespace(id="default", name="Default", description="Default workspace")

    class _ListSession:
        def execute(self, _stmt):
            return SimpleNamespace(scalars=lambda: SimpleNamespace(all=lambda: [row]))

    class _GetPresentSession:
        def get(self, _model, workspace_id):
            assert workspace_id == "default"
            return row

    class _GetMissingSession:
        def get(self, _model, workspace_id):
            assert workspace_id == "missing"
            return None

    class _CountSession:
        def execute(self, _stmt):
            return SimpleNamespace(scalar_one=lambda: 3)

    sessions = iter([_ListSession(), _GetPresentSession(), _GetMissingSession(), _CountSession()])
    monkeypatch.setattr(workspaces_mod, "session_scope", lambda _dsn: _Ctx(next(sessions)))

    assert repository._fetch_all() == [{"id": "default", "name": "Default", "description": "Default workspace"}]
    assert repository._fetch_one("default") == {"id": "default", "name": "Default", "description": "Default workspace"}
    assert repository._fetch_one("missing") is None
    assert repository._count_workspaces() == {"count": 3}


def test_postgres_workspaces_repository_session_write_helpers_cover_rowcount_paths(
    monkeypatch,
    postgres_dsn: str,
) -> None:
    repository = PostgresWorkspacesRepository(postgres_dsn)
    added_rows: list[object] = []
    commits: list[str] = []

    class _InsertSession:
        def add(self, row) -> None:
            added_rows.append(row)

        def commit(self) -> None:
            commits.append("insert")

    class _UpdateSession:
        def __init__(self, rowcount: int) -> None:
            self._rowcount = rowcount

        def execute(self, _stmt):
            return SimpleNamespace(rowcount=self._rowcount)

        def commit(self) -> None:
            commits.append(f"update:{self._rowcount}")

    class _DeleteSession:
        def __init__(self, rowcount: int) -> None:
            self._rowcount = rowcount

        def execute(self, _stmt):
            return SimpleNamespace(rowcount=self._rowcount)

        def commit(self) -> None:
            commits.append(f"delete:{self._rowcount}")

    sessions = iter([
        _InsertSession(),
        _UpdateSession(1),
        _UpdateSession(0),
        _DeleteSession(1),
        _DeleteSession(0),
    ])
    monkeypatch.setattr(workspaces_mod, "session_scope", lambda _dsn: _Ctx(next(sessions)))

    assert repository._insert_workspace("workspace-pg", "PG Workspace", "Description") is True
    assert added_rows[0].id == "workspace-pg"
    assert added_rows[0].name == "PG Workspace"
    assert added_rows[0].description == "Description"
    assert repository._update_workspace("workspace-pg", "Renamed", "Updated") is True
    assert repository._update_workspace("missing", "Renamed", "Updated") is False
    assert repository._delete_workspace("workspace-pg") is True
    assert repository._delete_workspace("missing") is False
    assert commits == ["insert", "update:1", "update:0", "delete:1", "delete:0"]
