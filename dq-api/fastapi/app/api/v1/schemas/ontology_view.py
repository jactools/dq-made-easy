from __future__ import annotations

from typing import Literal

from pydantic import Field

from app.schemas.pydantic_base import SnakeModel


class OntologyScopeView(SnakeModel):
    description: str
    in_scope_entities: list[str] = Field(default_factory=list)
    out_of_scope_entities: list[str] = Field(default_factory=list)


class OntologyEntityTypeView(SnakeModel):
    entity_type: str
    label: str
    description: str
    standard_mappings: list[str] = Field(default_factory=list)


class OntologyRelationTypeView(SnakeModel):
    relation_type: str
    label: str
    description: str
    source_entity_types: list[str] = Field(default_factory=list)
    target_entity_types: list[str] = Field(default_factory=list)
    standard_mappings: list[str] = Field(default_factory=list)


class OntologyStandardAlignmentView(SnakeModel):
    standard_name: str
    standard_uri: str
    usage: str
    alignment_scope: list[str] = Field(default_factory=list)


class OntologyGraphNodeView(SnakeModel):
    node_id: str
    node_type: str
    label: str
    description: str
    standard_mappings: list[str] = Field(default_factory=list)


class OntologyGraphEdgeView(SnakeModel):
    edge_type: str
    label: str
    description: str
    source_node_types: list[str] = Field(default_factory=list)
    target_node_types: list[str] = Field(default_factory=list)
    standard_mappings: list[str] = Field(default_factory=list)


class OntologyGraphView(SnakeModel):
    graph_id: str
    graph_name: str
    graph_description: str
    node_count: int = 0
    edge_count: int = 0
    nodes: list[OntologyGraphNodeView] = Field(default_factory=list)
    edges: list[OntologyGraphEdgeView] = Field(default_factory=list)


class CanonicalOntologyView(SnakeModel):
    ontology_id: str
    ontology_name: str
    version: str
    scope: OntologyScopeView
    entity_types: list[OntologyEntityTypeView] = Field(default_factory=list)
    relation_types: list[OntologyRelationTypeView] = Field(default_factory=list)
    standard_alignments: list[OntologyStandardAlignmentView] = Field(default_factory=list)
    graph: OntologyGraphView = Field(default_factory=lambda: OntologyGraphView(
        graph_id="dq-made-easy-domain-knowledge-graph",
        graph_name="dq-made-easy Domain Knowledge Graph",
        graph_description="Canonical graph projection of the ontology scope, entity vocabulary, and relation vocabulary.",
    ))

class OntologyGraphProjectionRequestView(SnakeModel):
    workspace_id: str | None = None
    data_product_id: str | None = None
    captured_by: str | None = None


class OntologyGraphProjectionNodeView(SnakeModel):
    node_id: str
    node_type: str
    label: str
    description: str
    standard_mappings: list[str] = Field(default_factory=list)


class OntologyGraphProjectionEdgeView(SnakeModel):
    edge_id: str
    relation_type: str
    source_node_id: str
    target_node_id: str
    source_node_type: str
    target_node_type: str
    label: str
    description: str
    standard_mappings: list[str] = Field(default_factory=list)


class OntologyGraphProjectionGraphView(SnakeModel):
    graph_id: str
    graph_name: str
    graph_description: str
    node_count: int = 0
    edge_count: int = 0
    nodes: list[OntologyGraphProjectionNodeView] = Field(default_factory=list)
    edges: list[OntologyGraphProjectionEdgeView] = Field(default_factory=list)


class OntologyGraphSnapshotView(SnakeModel):
    id: str
    graph_id: str
    graph_name: str
    workspace_id: str | None = None
    data_product_id: str | None = None
    captured_at: str
    captured_by: str | None = None
    node_count: int = 0
    edge_count: int = 0
    source_summary: dict[str, object] = Field(default_factory=dict)


class OntologyGraphProjectionView(SnakeModel):
    snapshot: OntologyGraphSnapshotView
    graph: OntologyGraphProjectionGraphView
    source_summary: dict[str, object] = Field(default_factory=dict)


class OntologyGraphQueryRequestView(SnakeModel):
    workspace_id: str | None = None
    data_product_id: str | None = None
    label_contains: str | None = None
    node_ids: list[str] = Field(default_factory=list)
    node_types: list[str] = Field(default_factory=list)
    relation_types: list[str] = Field(default_factory=list)
    limit: int = Field(default=100, ge=1, le=500)
    offset: int = Field(default=0, ge=0)


class OntologyGraphTraversalRequestView(SnakeModel):
    workspace_id: str | None = None
    data_product_id: str | None = None
    start_node_id: str
    max_depth: int = Field(default=2, ge=0, le=8)
    direction: Literal["outbound", "inbound", "both"] = "outbound"
    relation_types: list[str] = Field(default_factory=list)
    limit: int = Field(default=200, ge=1, le=1000)


class OntologyGraphQueryResultView(SnakeModel):
    snapshot: OntologyGraphSnapshotView
    graph: OntologyGraphProjectionGraphView
    matched_node_ids: list[str] = Field(default_factory=list)
    matched_edge_ids: list[str] = Field(default_factory=list)
    query_summary: dict[str, object] = Field(default_factory=dict)


class OntologyGraphTraversalResultView(SnakeModel):
    snapshot: OntologyGraphSnapshotView
    graph: OntologyGraphProjectionGraphView
    start_node_id: str
    visited_node_ids: list[str] = Field(default_factory=list)
    visited_edge_ids: list[str] = Field(default_factory=list)
    node_depths: dict[str, int] = Field(default_factory=dict)
    traversal_summary: dict[str, object] = Field(default_factory=dict)


OntologyGraphProjectionNodeView.model_rebuild()
OntologyGraphProjectionEdgeView.model_rebuild()
OntologyGraphProjectionGraphView.model_rebuild()
OntologyGraphSnapshotView.model_rebuild()
OntologyGraphProjectionView.model_rebuild()
OntologyGraphQueryRequestView.model_rebuild()
OntologyGraphTraversalRequestView.model_rebuild()
OntologyGraphQueryResultView.model_rebuild()
OntologyGraphTraversalResultView.model_rebuild()
