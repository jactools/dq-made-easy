from app.infrastructure.repositories.in_memory_workspaces_repository import InMemoryWorkspacesRepository


def test_in_memory_workspaces_repository_crud_and_limits(
    workspace_create_payload: dict[str, object],
    clone_payload,
) -> None:
    repository = InMemoryWorkspacesRepository()

    rows = repository.list_workspaces()
    assert len(rows) == 3

    created = repository.create_workspace(clone_payload(workspace_create_payload), max_workspaces=10)
    assert created.model_dump() == {"id": "workspace-unit-test", "name": "Unit Test Workspace", "description": "Created in unit test"}

    updated = repository.update_workspace("workspace-unit-test", {"name": "Unit Test Workspace Updated"})
    assert updated is not None
    assert updated.name == "Unit Test Workspace Updated"

    deleted = repository.delete_workspace("workspace-unit-test")
    assert deleted is True
    assert repository.delete_workspace("workspace-unit-test") is False


def test_in_memory_workspaces_repository_rejects_limit_and_duplicate(
    workspace_duplicate_payload: dict[str, object],
    workspace_overflow_payload: dict[str, object],
    clone_payload,
) -> None:
    repository = InMemoryWorkspacesRepository()

    try:
        repository.create_workspace(clone_payload(workspace_duplicate_payload), max_workspaces=10)
    except ValueError as error:
        assert str(error) == "Workspace already exists"
    else:
        raise AssertionError("Expected ValueError for duplicate workspace")

    try:
        repository.create_workspace(clone_payload(workspace_overflow_payload), max_workspaces=3)
    except ValueError as error:
        assert str(error) == "Workspace limit reached"
    else:
        raise AssertionError("Expected ValueError for workspace limit")
