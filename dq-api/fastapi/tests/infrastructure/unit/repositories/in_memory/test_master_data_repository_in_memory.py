from app.infrastructure.repositories.in_memory_master_data_repository import InMemoryMasterDataRepository


def test_list_master_records_sorts_and_filters() -> None:
    repository = InMemoryMasterDataRepository()

    rows = repository.list_master_records(domain="customer", workspace_id="retail-banking")

    assert [row.id for row in rows] == ["mr-001", "mr-002"]
    assert rows[0].source_systems == ["crm", "core-banking", "support"]
    assert rows[1].resolution_status == "candidate"
