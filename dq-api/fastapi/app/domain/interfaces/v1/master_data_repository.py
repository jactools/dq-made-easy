from app.domain.entities.master_data import MasterRecordEntity


class MasterDataRepository:
    def list_master_records(self, domain: str | None = None, workspace_id: str | None = None) -> list[MasterRecordEntity]: ...