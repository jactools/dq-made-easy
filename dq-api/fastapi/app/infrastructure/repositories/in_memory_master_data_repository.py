from app.domain.entities.master_data import MasterRecordEntity
from app.domain.interfaces.v1.master_data_repository import MasterDataRepository
from app.infrastructure.repositories.in_memory_test_data import master_data_seed_data


class InMemoryMasterDataRepository(MasterDataRepository):
    def __init__(self) -> None:
        seed = master_data_seed_data()
        self._master_records = seed["master_records"]

    def list_master_records(self, domain: str | None = None, workspace_id: str | None = None) -> list[MasterRecordEntity]:
        rows = self._master_records
        if domain is not None:
            rows = [row for row in rows if str(row.get("domain") or "") == domain]
        if workspace_id is not None:
            rows = [row for row in rows if str(row.get("workspace_id") or "") == workspace_id]
        sorted_rows = sorted(rows, key=lambda row: (str(row.get("display_name") or ""), str(row.get("id") or "")))
        return [MasterRecordEntity(**row) for row in sorted_rows]