from fastapi import APIRouter, Depends, Query

from app.api.presenters.data_catalog import build_data_catalog_page_payload
from app.api.v1.schemas import MasterRecordsPageView
from app.core.dependencies import get_master_data_repository
from app.domain.interfaces import MasterDataRepository


router = APIRouter(tags=["master-data"])


@router.get("/master-records", response_model=MasterRecordsPageView)
async def get_master_records(
    domain: str | None = Query(default=None),
    workspace_id: str | None = Query(default=None),
    business_key: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=100),
    repository: MasterDataRepository = Depends(get_master_data_repository),
) -> MasterRecordsPageView:
    rows = repository.list_master_records(domain=domain, workspace_id=workspace_id)
    if business_key is not None:
        rows = [row for row in rows if str(getattr(row, "business_key", "") or "") == business_key]
    return MasterRecordsPageView.model_validate(build_data_catalog_page_payload([row.model_dump() for row in rows], page, limit))