from __future__ import annotations

from collections.abc import Sequence
from copy import deepcopy

from app.domain.entities.ontology_graph import OntologyGraphSnapshotEntity
from app.domain.interfaces.v1.ontology_graph_repository import OntologyGraphRepository


class InMemoryOntologyGraphRepository(OntologyGraphRepository):
    def __init__(self) -> None:
        self._snapshots: list[dict] = []

    async def record_ontology_graph_snapshot(self, snapshot: OntologyGraphSnapshotEntity) -> OntologyGraphSnapshotEntity:
        stored = snapshot.model_dump(mode="python", by_alias=True, exclude_none=True)
        self._snapshots.append(deepcopy(stored))
        return OntologyGraphSnapshotEntity.model_validate(stored)

    async def get_latest_ontology_graph_snapshot(
        self,
        *,
        graph_id: str,
        workspace_id: str | None = None,
        data_product_id: str | None = None,
    ) -> OntologyGraphSnapshotEntity | None:
        rows = [row for row in self._snapshots if str(row.get("graph_id") or "") == str(graph_id)]
        if workspace_id is not None:
            rows = [row for row in rows if str(row.get("workspace_id") or "") == str(workspace_id)]
        if data_product_id is not None:
            rows = [row for row in rows if str(row.get("data_product_id") or "") == str(data_product_id)]
        if not rows:
            return None
        return OntologyGraphSnapshotEntity.model_validate(rows[-1])

    async def list_ontology_graph_snapshots(
        self,
        *,
        graph_id: str | None = None,
        workspace_id: str | None = None,
        data_product_id: str | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> Sequence[OntologyGraphSnapshotEntity]:
        rows = list(self._snapshots)
        if graph_id is not None:
            rows = [row for row in rows if str(row.get("graph_id") or "") == str(graph_id)]
        if workspace_id is not None:
            rows = [row for row in rows if str(row.get("workspace_id") or "") == str(workspace_id)]
        if data_product_id is not None:
            rows = [row for row in rows if str(row.get("data_product_id") or "") == str(data_product_id)]
        rows = rows[offset:offset + max(limit, 0)]
        return [OntologyGraphSnapshotEntity.model_validate(row) for row in rows]
