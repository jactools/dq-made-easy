from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

from app.domain.entities.ontology_graph import OntologyGraphSnapshotEntity


class OntologyGraphRepository(Protocol):
    async def record_ontology_graph_snapshot(self, snapshot: OntologyGraphSnapshotEntity) -> OntologyGraphSnapshotEntity:
        ...

    async def get_latest_ontology_graph_snapshot(
        self,
        *,
        graph_id: str,
        workspace_id: str | None = None,
        data_product_id: str | None = None,
    ) -> OntologyGraphSnapshotEntity | None:
        ...

    async def list_ontology_graph_snapshots(
        self,
        *,
        graph_id: str | None = None,
        workspace_id: str | None = None,
        data_product_id: str | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> Sequence[OntologyGraphSnapshotEntity]:
        ...
