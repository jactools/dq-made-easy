from __future__ import annotations

from pydantic import Field

from app.domain.entities.base import EntityModel


class MasterRecordEntity(EntityModel):
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