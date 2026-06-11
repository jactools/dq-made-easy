from __future__ import annotations

from collections import deque

from app.api.v1.schemas.ontology_view import OntologyGraphProjectionEdgeView
from app.api.v1.schemas.ontology_view import OntologyGraphProjectionGraphView
from app.api.v1.schemas.ontology_view import OntologyGraphProjectionNodeView
from app.api.v1.schemas.ontology_view import OntologyGraphQueryRequestView
from app.api.v1.schemas.ontology_view import OntologyGraphQueryResultView
from app.api.v1.schemas.ontology_view import OntologyGraphSnapshotView
from app.api.v1.schemas.ontology_view import OntologyGraphTraversalRequestView
from app.api.v1.schemas.ontology_view import OntologyGraphTraversalResultView
from app.domain.entities.ontology_graph import OntologyGraphSnapshotEntity
from app.domain.interfaces.v1.ontology_graph_repository import OntologyGraphRepository


_GRAPH_ID = "dq-made-easy-domain-knowledge-graph"


class OntologyGraphLookupError(ValueError):
    def __init__(self, message: str, *, status_code: int = 400, error_code: str = "ontology_graph_lookup_failed") -> None:
        super().__init__(message)
        self.status_code = status_code
        self.error_code = error_code


def _normalized_text(value: object) -> str:
    return str(value or "").strip()


def _snapshot_view(snapshot: OntologyGraphSnapshotEntity) -> OntologyGraphSnapshotView:
    return OntologyGraphSnapshotView.model_validate(snapshot)


def _node_view(payload: object) -> OntologyGraphProjectionNodeView:
    if isinstance(payload, OntologyGraphProjectionNodeView):
        return payload
    if isinstance(payload, dict):
        return OntologyGraphProjectionNodeView.model_validate(payload)
    raise OntologyGraphLookupError("A graph node payload was invalid", error_code="ontology_graph_invalid_snapshot")


def _edge_view(payload: object) -> OntologyGraphProjectionEdgeView:
    if isinstance(payload, OntologyGraphProjectionEdgeView):
        return payload
    if isinstance(payload, dict):
        return OntologyGraphProjectionEdgeView.model_validate(payload)
    raise OntologyGraphLookupError("A graph edge payload was invalid", error_code="ontology_graph_invalid_snapshot")


def _graph_views_from_snapshot(snapshot: OntologyGraphSnapshotEntity) -> tuple[list[OntologyGraphProjectionNodeView], list[OntologyGraphProjectionEdgeView]]:
    graph_payload = snapshot.graph_json or {}
    node_payloads = graph_payload.get("nodes") if isinstance(graph_payload, dict) else []
    edge_payloads = graph_payload.get("edges") if isinstance(graph_payload, dict) else []
    nodes = [_node_view(payload) for payload in node_payloads if isinstance(payload, dict)]
    edges = [_edge_view(payload) for payload in edge_payloads if isinstance(payload, dict)]
    return nodes, edges


async def _load_latest_snapshot(
    ontology_graph_repository: OntologyGraphRepository,
    *,
    workspace_id: str | None,
    data_product_id: str | None,
) -> OntologyGraphSnapshotEntity:
    if workspace_id is not None or data_product_id is not None:
        snapshot = await ontology_graph_repository.get_latest_ontology_graph_snapshot(
            graph_id=_GRAPH_ID,
            workspace_id=workspace_id,
            data_product_id=data_product_id,
        )
    else:
        snapshot = await ontology_graph_repository.get_latest_ontology_graph_snapshot(graph_id=_GRAPH_ID)
    if snapshot is None:
        raise OntologyGraphLookupError(
            "No ontology graph snapshot is available for the requested scope",
            status_code=404,
            error_code="ontology_graph_snapshot_not_found",
        )
    return snapshot


def _build_induced_graph(
    nodes: list[OntologyGraphProjectionNodeView],
    edges: list[OntologyGraphProjectionEdgeView],
    *,
    node_ids: set[str],
    relation_types: set[str] | None = None,
) -> tuple[list[OntologyGraphProjectionNodeView], list[OntologyGraphProjectionEdgeView]]:
    selected_nodes = [node for node in nodes if node.node_id in node_ids]
    selected_node_ids = {node.node_id for node in selected_nodes}
    selected_edges = [
        edge
        for edge in edges
        if edge.source_node_id in selected_node_ids
        and edge.target_node_id in selected_node_ids
        and (relation_types is None or edge.relation_type in relation_types)
    ]
    return selected_nodes, selected_edges


async def query_ontology_graph(
    *,
    request: OntologyGraphQueryRequestView,
    ontology_graph_repository: OntologyGraphRepository,
) -> OntologyGraphQueryResultView:
    snapshot = await _load_latest_snapshot(
        ontology_graph_repository,
        workspace_id=request.workspace_id,
        data_product_id=request.data_product_id,
    )
    nodes, edges = _graph_views_from_snapshot(snapshot)
    label_filter = _normalized_text(request.label_contains).lower()
    node_type_filter = {str(value).strip() for value in request.node_types if str(value).strip()} or None
    node_id_filter = {str(value).strip() for value in request.node_ids if str(value).strip()}
    relation_filter = {str(value).strip() for value in request.relation_types if str(value).strip()} or None

    matched_nodes = [
        node
        for node in nodes
        if (
            not node_type_filter or node.node_type in node_type_filter
        )
        and (
            not node_id_filter or node.node_id in node_id_filter
        )
        and (
            not label_filter
            or label_filter in node.label.lower()
            or label_filter in node.description.lower()
        )
    ]
    selected_nodes = matched_nodes[request.offset : request.offset + request.limit]
    selected_node_ids = {node.node_id for node in selected_nodes}
    matched_edges = [
        edge
        for edge in edges
        if edge.source_node_id in selected_node_ids
        and edge.target_node_id in selected_node_ids
        and (relation_filter is None or edge.relation_type in relation_filter)
    ]

    graph_view = OntologyGraphProjectionGraphView(
        graph_id=snapshot.graph_id,
        graph_name=snapshot.graph_name,
        graph_description=snapshot.source_summary.get("graph_description", "Ontology graph query result") if isinstance(snapshot.source_summary, dict) else "Ontology graph query result",
        node_count=len(selected_nodes),
        edge_count=len(matched_edges),
        nodes=selected_nodes,
        edges=matched_edges,
    )
    return OntologyGraphQueryResultView(
        snapshot=_snapshot_view(snapshot),
        graph=graph_view,
        matched_node_ids=[node.node_id for node in selected_nodes],
        matched_edge_ids=[edge.edge_id for edge in matched_edges],
        query_summary={
            "requested_node_types": sorted(node_type_filter or []),
            "requested_relation_types": sorted(relation_filter or []),
            "label_contains": request.label_contains,
            "matched_node_count": len(matched_nodes),
            "returned_node_count": len(selected_nodes),
            "returned_edge_count": len(matched_edges),
        },
    )


async def traverse_ontology_graph(
    *,
    request: OntologyGraphTraversalRequestView,
    ontology_graph_repository: OntologyGraphRepository,
) -> OntologyGraphTraversalResultView:
    snapshot = await _load_latest_snapshot(
        ontology_graph_repository,
        workspace_id=request.workspace_id,
        data_product_id=request.data_product_id,
    )
    nodes, edges = _graph_views_from_snapshot(snapshot)
    node_by_id = {node.node_id: node for node in nodes}
    if request.start_node_id not in node_by_id:
        raise OntologyGraphLookupError(
            f"Start node '{request.start_node_id}' was not found in the ontology graph snapshot",
            status_code=404,
            error_code="ontology_graph_start_node_not_found",
        )

    relation_filter = {str(value).strip() for value in request.relation_types if str(value).strip()} or None
    outgoing: dict[str, list[OntologyGraphProjectionEdgeView]] = {}
    incoming: dict[str, list[OntologyGraphProjectionEdgeView]] = {}
    for edge in edges:
        if relation_filter is not None and edge.relation_type not in relation_filter:
            continue
        outgoing.setdefault(edge.source_node_id, []).append(edge)
        incoming.setdefault(edge.target_node_id, []).append(edge)

    queue = deque([(request.start_node_id, 0)])
    node_depths: dict[str, int] = {request.start_node_id: 0}
    visited_edge_ids: list[str] = []
    visited_edge_lookup: set[str] = set()
    while queue:
        current_node_id, depth = queue.popleft()
        if depth >= request.max_depth:
            continue
        candidate_edges: list[tuple[OntologyGraphProjectionEdgeView, str]] = []
        if request.direction in {"outbound", "both"}:
            candidate_edges.extend((edge, edge.target_node_id) for edge in outgoing.get(current_node_id, []))
        if request.direction in {"inbound", "both"}:
            candidate_edges.extend((edge, edge.source_node_id) for edge in incoming.get(current_node_id, []))

        for edge, next_node_id in candidate_edges:
            if edge.edge_id not in visited_edge_lookup:
                visited_edge_lookup.add(edge.edge_id)
                visited_edge_ids.append(edge.edge_id)
            if next_node_id not in node_by_id:
                continue
            next_depth = depth + 1
            previous_depth = node_depths.get(next_node_id)
            if previous_depth is None or next_depth < previous_depth:
                node_depths[next_node_id] = next_depth
                queue.append((next_node_id, next_depth))

    selected_node_ids = set(node_depths)
    selected_nodes = [node_by_id[node_id] for node_id in sorted(selected_node_ids, key=lambda item: (node_depths.get(item, 0), item))]
    selected_edges = [
        edge
        for edge in edges
        if edge.edge_id in visited_edge_lookup
        and edge.source_node_id in selected_node_ids
        and edge.target_node_id in selected_node_ids
    ]
    if len(selected_nodes) > request.limit:
        selected_nodes = selected_nodes[: request.limit]
        selected_node_ids = {node.node_id for node in selected_nodes}
        selected_edges = [edge for edge in selected_edges if edge.source_node_id in selected_node_ids and edge.target_node_id in selected_node_ids]

    graph_view = OntologyGraphProjectionGraphView(
        graph_id=snapshot.graph_id,
        graph_name=snapshot.graph_name,
        graph_description=snapshot.source_summary.get("graph_description", "Ontology graph traversal result") if isinstance(snapshot.source_summary, dict) else "Ontology graph traversal result",
        node_count=len(selected_nodes),
        edge_count=len(selected_edges),
        nodes=selected_nodes,
        edges=selected_edges,
    )
    return OntologyGraphTraversalResultView(
        snapshot=_snapshot_view(snapshot),
        graph=graph_view,
        start_node_id=request.start_node_id,
        visited_node_ids=[node.node_id for node in selected_nodes],
        visited_edge_ids=[edge.edge_id for edge in selected_edges],
        node_depths={node_id: depth for node_id, depth in node_depths.items() if node_id in selected_node_ids},
        traversal_summary={
            "max_depth": request.max_depth,
            "direction": request.direction,
            "relation_types": sorted(relation_filter or []),
            "visited_node_count": len(selected_nodes),
            "visited_edge_count": len(selected_edges),
        },
    )
