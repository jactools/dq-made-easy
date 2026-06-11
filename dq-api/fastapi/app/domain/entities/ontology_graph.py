from __future__ import annotations

from typing import Any

from pydantic import Field

from app.domain.entities.base import EntityModel


class OntologyGraphSnapshotEntity(EntityModel):
    id: str
    graph_id: str
    graph_name: str = ""
    workspace_id: str | None = None
    data_product_id: str | None = None
    captured_at: str
    captured_by: str | None = None
    node_count: int = 0
    edge_count: int = 0
    graph_json: dict[str, Any] = Field(default_factory=dict)
    source_summary: dict[str, Any] = Field(default_factory=dict)
