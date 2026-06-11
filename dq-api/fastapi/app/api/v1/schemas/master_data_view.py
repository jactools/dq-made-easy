from pydantic import ConfigDict, Field

from app.api.v1.schemas.common_view import PaginationView
from app.schemas.pydantic_base import SnakeModel, to_snake_alias


class MasterRecordView(SnakeModel):
    model_config = ConfigDict(from_attributes=True, alias_generator=to_snake_alias, populate_by_name=True)

    id: str
    domain: str = ""
    display_name: str = ""
    business_key: str = ""
    golden_record_id: str = ""
    match_rule: str = ""
    survivorship_rule: str = ""
    resolution_status: str = "golden"
    source_count: int = 0
    source_systems: list[str] = Field(default_factory=list)
    merged_from_ids: list[str] = Field(default_factory=list)
    owner: str = ""
    workspace_id: str = ""
    created_at: str = ""
    updated_at: str = ""


class MasterRecordsPageView(SnakeModel):
    data: list[MasterRecordView]
    pagination: PaginationView