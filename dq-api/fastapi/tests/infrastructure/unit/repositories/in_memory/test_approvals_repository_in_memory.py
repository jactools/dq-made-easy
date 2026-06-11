from app.infrastructure.repositories.in_memory_approvals_repository import InMemoryApprovalsRepository


def test_in_memory_approvals_repository_filters_workspace_and_audit() -> None:
    repository = InMemoryApprovalsRepository()

    all_rows = repository.list_approvals()
    filtered = repository.list_approvals("retail-banking")
    business_key_filtered = repository.list_approvals(business_key="approval-002")
    audit = repository.list_approval_audit()

    assert len(all_rows) == 6
    assert len(filtered) == 5
    assert len(business_key_filtered) == 1
    assert business_key_filtered[0].id == "approval-002"
    assert filtered[0].workspaceId == "retail-banking"
    assert audit[0].action == "created"


def test_in_memory_approvals_repository_mutation_paths(
    approval_create_payload: dict[str, object],
    approval_status_update_payload: dict[str, object],
    clone_payload,
) -> None:
    repository = InMemoryApprovalsRepository()

    created = repository.create_approval(
        clone_payload(approval_create_payload),
        actor_id="user-admin",
    )
    assert created.requesterId == "user-admin"
    assert created.businessKey == created.id
    assert created.effectiveStatus == "activated"

    try:
        repository.update_approval(created.id, approval_status_update_payload, actor_id="user-admin")
    except PermissionError as error:
        assert str(error) == "Requester cannot approve their own request"
    else:
        raise AssertionError("Expected PermissionError for self-approval")


def test_in_memory_approvals_repository_records_actor_timestamp_and_rationale(
    approval_create_payload: dict[str, object],
    approval_status_update_payload: dict[str, object],
    clone_payload,
) -> None:
    repository = InMemoryApprovalsRepository()

    created = repository.create_approval(
        clone_payload(approval_create_payload),
        actor_id="requester-1",
    )
    assert created.requesterId == "requester-1"

    approved_payload = dict(approval_status_update_payload)
    approved_payload["comments"] = "Reviewed and approved"

    updated = repository.update_approval(created.id, approved_payload, actor_id="reviewer-1")

    assert updated is not None
    audit_rows = repository.list_approval_audit()
    approval_audit = audit_rows[-1]
    assert approval_audit.action == "approved"
    assert approval_audit.actorId == "reviewer-1"
    assert approval_audit.timestamp
    assert approval_audit.details["comments"] == "Reviewed and approved"


def test_in_memory_approvals_repository_persists_effective_at(
    approval_create_payload: dict[str, object],
    clone_payload,
) -> None:
    repository = InMemoryApprovalsRepository()

    payload = clone_payload(approval_create_payload)
    payload["effective_at"] = "2026-04-07T13:15:00Z"

    created = repository.create_approval(payload, actor_id="user-admin")

    assert created.effectiveAt == "2026-04-07T13:15:00Z"
    assert created.effectiveStatus == "activated"


def test_in_memory_approvals_repository_persists_gx_run_plan_identifiers() -> None:
    repository = InMemoryApprovalsRepository()

    created = repository.create_approval(
        {
            "gx_run_plan_id": "run-plan-1",
            "gx_run_plan_version_id": "run-plan-version-1",
            "workspace_id": "default",
            "request_type": "activation",
        },
        actor_id="user-admin",
    )

    assert created.gxRunPlanId == "run-plan-1"
    assert created.gxRunPlanVersionId == "run-plan-version-1"
    assert created.businessKey == created.id
