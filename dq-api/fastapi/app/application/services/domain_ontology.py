from __future__ import annotations

from typing import Any

from app.api.v1.schemas.ontology_view import CanonicalOntologyView
from app.api.v1.schemas.ontology_view import OntologyEntityTypeView
from app.api.v1.schemas.ontology_view import OntologyGraphEdgeView
from app.api.v1.schemas.ontology_view import OntologyGraphNodeView
from app.api.v1.schemas.ontology_view import OntologyGraphView
from app.api.v1.schemas.ontology_view import OntologyRelationTypeView
from app.api.v1.schemas.ontology_view import OntologyScopeView
from app.api.v1.schemas.ontology_view import OntologyStandardAlignmentView


_ONTOLOGY_ID = "dq-made-easy-domain-ontology"
_ONTOLOGY_NAME = "dq-made-easy Domain Ontology"
_ONTOLOGY_VERSION = "1.0"


def _build_graph_nodes(entity_types: list[OntologyEntityTypeView]) -> list[OntologyGraphNodeView]:
    return [
        OntologyGraphNodeView(
            node_id=entity_type.entity_type,
            node_type=entity_type.entity_type,
            label=entity_type.label,
            description=entity_type.description,
            standard_mappings=list(entity_type.standard_mappings),
        )
        for entity_type in entity_types
    ]


def _build_graph_edges(relation_types: list[OntologyRelationTypeView]) -> list[OntologyGraphEdgeView]:
    return [
        OntologyGraphEdgeView(
            edge_type=relation_type.relation_type,
            label=relation_type.label,
            description=relation_type.description,
            source_node_types=list(relation_type.source_entity_types),
            target_node_types=list(relation_type.target_entity_types),
            standard_mappings=list(relation_type.standard_mappings),
        )
        for relation_type in relation_types
    ]


def build_canonical_ontology() -> CanonicalOntologyView:
    entity_types = [
        OntologyEntityTypeView(
            entity_type="domain",
            label="Domain",
            description="A governed business or organizational domain that groups related assets and quality signals.",
            standard_mappings=["skos:ConceptScheme"],
        ),
        OntologyEntityTypeView(
            entity_type="data_product",
            label="Data Product",
            description="A governed delivery unit exposed to the platform as a product-level metadata object.",
            standard_mappings=["dcat:Dataset", "prov:Entity"],
        ),
        OntologyEntityTypeView(
            entity_type="dataset",
            label="Dataset",
            description="A logical dataset or collection of data objects that participates in quality governance.",
            standard_mappings=["dcat:Dataset", "prov:Entity"],
        ),
        OntologyEntityTypeView(
            entity_type="data_object",
            label="Data Object",
            description="A cataloged object within a dataset, such as a table, file, view, or API-backed object.",
            standard_mappings=["prov:Entity"],
        ),
        OntologyEntityTypeView(
            entity_type="data_object_version",
            label="Data Object Version",
            description="A versioned snapshot of a data object used for lineage and attribute-level relationships.",
            standard_mappings=["prov:Entity", "prov:Revision"],
        ),
        OntologyEntityTypeView(
            entity_type="attribute",
            label="Attribute",
            description="A governed field or property attached to a versioned data object.",
            standard_mappings=["rdf:Property"],
        ),
        OntologyEntityTypeView(
            entity_type="business_concept",
            label="Business Concept",
            description="A governed glossary concept, business definition, or semantic term used to describe the platform.",
            standard_mappings=["skos:Concept"],
        ),
        OntologyEntityTypeView(
            entity_type="rule",
            label="Rule",
            description="A governed validation or assurance rule that can be attached to datasets and domains.",
            standard_mappings=["prov:Entity"],
        ),
        OntologyEntityTypeView(
            entity_type="validation_suite",
            label="Validation Suite",
            description="A governed grouping of validation plans or test families that validate a domain or asset.",
            standard_mappings=["prov:Entity"],
        ),
        OntologyEntityTypeView(
            entity_type="validation_plan",
            label="Validation Plan",
            description="A governed plan that defines how validation suites are executed or scheduled.",
            standard_mappings=["prov:Plan"],
        ),
        OntologyEntityTypeView(
            entity_type="dq_outcome",
            label="DQ Outcome",
            description="A measured data-quality result, score, breach, drift signal, or incident-linked outcome.",
            standard_mappings=["prov:Entity", "prov:Activity"],
        ),
        OntologyEntityTypeView(
            entity_type="incident",
            label="Incident",
            description="A governed incident or alert that can be correlated to quality outcomes and impacted assets.",
            standard_mappings=["prov:Activity"],
        ),
        OntologyEntityTypeView(
            entity_type="external_party",
            label="External Party",
            description="A collaborating workspace, tenant, or organization that exchanges governed metadata packages.",
            standard_mappings=["prov:Agent"],
        ),
        OntologyEntityTypeView(
            entity_type="workspace",
            label="Workspace",
            description="A governed workspace boundary used to scope ownership, metadata exchange, and graph projections.",
            standard_mappings=["prov:Agent"],
        ),
        OntologyEntityTypeView(
            entity_type="time_point",
            label="Time Point",
            description="A canonical temporal anchor used to relate events and DQ outcomes to a specific moment in time.",
            standard_mappings=["prov:InstantaneousEvent", "xsd:dateTime"],
        ),
        OntologyEntityTypeView(
            entity_type="event",
            label="Event",
            description="A governed occurrence that can drive, summarize, or explain quality and metadata activity.",
            standard_mappings=["prov:Activity"],
        ),
        OntologyEntityTypeView(
            entity_type="organizational_hierarchy",
            label="Organizational Hierarchy",
            description="A governed hierarchy of organizational units used to scope accountability and ownership.",
            standard_mappings=["skos:ConceptScheme", "prov:Agent"],
        ),
        OntologyEntityTypeView(
            entity_type="organizational_unit",
            label="Organizational Unit",
            description="A team, department, or business function within the organizational hierarchy.",
            standard_mappings=["prov:Agent", "skos:Concept"],
        ),
    ]

    relation_types = [
        OntologyRelationTypeView(
            relation_type="belongs_to_domain",
            label="Belongs To Domain",
            description="Connects a dataset, data product, rule, or business concept to its governing domain.",
            source_entity_types=["dataset", "data_product", "rule", "business_concept"],
            target_entity_types=["domain"],
            standard_mappings=["dcterms:isPartOf", "skos:inScheme"],
        ),
        OntologyRelationTypeView(
            relation_type="contains_data_product",
            label="Contains Data Product",
            description="Connects a domain or workspace to the data products it governs.",
            source_entity_types=["domain", "workspace"],
            target_entity_types=["data_product"],
            standard_mappings=["dcterms:hasPart"],
        ),
        OntologyRelationTypeView(
            relation_type="contains_dataset",
            label="Contains Dataset",
            description="Connects a data product to the datasets it contains or exposes.",
            source_entity_types=["data_product"],
            target_entity_types=["dataset"],
            standard_mappings=["dcterms:hasPart", "dcat:dataset"],
        ),
        OntologyRelationTypeView(
            relation_type="contains_data_object",
            label="Contains Data Object",
            description="Connects a dataset to the data objects that belong to it.",
            source_entity_types=["dataset"],
            target_entity_types=["data_object"],
            standard_mappings=["dcterms:hasPart"],
        ),
        OntologyRelationTypeView(
            relation_type="has_version",
            label="Has Version",
            description="Connects a data object to its versioned snapshots.",
            source_entity_types=["data_object"],
            target_entity_types=["data_object_version"],
            standard_mappings=["prov:hadRevision"],
        ),
        OntologyRelationTypeView(
            relation_type="has_attribute",
            label="Has Attribute",
            description="Connects a versioned data object to a governed attribute.",
            source_entity_types=["data_object_version"],
            target_entity_types=["attribute"],
            standard_mappings=["rdf:predicate"],
        ),
        OntologyRelationTypeView(
            relation_type="describes_business_concept",
            label="Describes Business Concept",
            description="Connects an attribute to the business concept or glossary term that defines it.",
            source_entity_types=["attribute"],
            target_entity_types=["business_concept"],
            standard_mappings=["skos:related"],
        ),
        OntologyRelationTypeView(
            relation_type="governs_rule",
            label="Governs Rule",
            description="Connects a domain or dataset to the rules that validate it.",
            source_entity_types=["domain", "dataset", "data_product"],
            target_entity_types=["rule"],
            standard_mappings=["prov:wasAssociatedWith"],
        ),
        OntologyRelationTypeView(
            relation_type="supports_validation_suite",
            label="Supports Validation Suite",
            description="Connects a dataset or data product to the validation suites that cover it.",
            source_entity_types=["dataset", "data_product"],
            target_entity_types=["validation_suite"],
            standard_mappings=["prov:wasGeneratedBy"],
        ),
        OntologyRelationTypeView(
            relation_type="supports_validation_plan",
            label="Supports Validation Plan",
            description="Connects a validation suite to the plans that schedule or execute it.",
            source_entity_types=["validation_suite"],
            target_entity_types=["validation_plan"],
            standard_mappings=["prov:hadPlan"],
        ),
        OntologyRelationTypeView(
            relation_type="produces_dq_outcome",
            label="Produces DQ Outcome",
            description="Connects a validation plan or rule execution to its measured DQ outcomes.",
            source_entity_types=["validation_plan", "rule"],
            target_entity_types=["dq_outcome"],
            standard_mappings=["prov:generated", "prov:wasGeneratedBy"],
        ),
        OntologyRelationTypeView(
            relation_type="impacts_incident",
            label="Impacts Incident",
            description="Connects a DQ outcome to an incident or alert that was raised from it.",
            source_entity_types=["dq_outcome"],
            target_entity_types=["incident"],
            standard_mappings=["prov:wasInfluencedBy"],
        ),
        OntologyRelationTypeView(
            relation_type="published_by_external_party",
            label="Published By External Party",
            description="Connects a governed metadata package or workspace scope to the external party that published it.",
            source_entity_types=["workspace"],
            target_entity_types=["external_party"],
            standard_mappings=["prov:wasAttributedTo"],
        ),
        OntologyRelationTypeView(
            relation_type="scoped_to_workspace",
            label="Scoped To Workspace",
            description="Connects an external party to the workspace boundary it can exchange metadata for.",
            source_entity_types=["external_party"],
            target_entity_types=["workspace"],
            standard_mappings=["prov:atLocation"],
        ),
        OntologyRelationTypeView(
            relation_type="belongs_to_organizational_unit",
            label="Belongs To Organizational Unit",
            description="Connects a domain, data product, dataset, or rule to its accountable organizational unit.",
            source_entity_types=["domain", "data_product", "dataset", "rule"],
            target_entity_types=["organizational_unit"],
            standard_mappings=["prov:wasAttributedTo"],
        ),
        OntologyRelationTypeView(
            relation_type="contains_organizational_unit",
            label="Contains Organizational Unit",
            description="Connects an organizational hierarchy to the units it contains.",
            source_entity_types=["organizational_hierarchy"],
            target_entity_types=["organizational_unit"],
            standard_mappings=["dcterms:hasPart"],
        ),
        OntologyRelationTypeView(
            relation_type="parent_organizational_unit",
            label="Parent Organizational Unit",
            description="Connects a child organizational unit to its parent unit in the hierarchy.",
            source_entity_types=["organizational_unit"],
            target_entity_types=["organizational_unit"],
            standard_mappings=["dcterms:isPartOf"],
        ),
        OntologyRelationTypeView(
            relation_type="occurs_at_time_point",
            label="Occurs At Time Point",
            description="Connects an event or DQ outcome to the time point at which it is anchored.",
            source_entity_types=["event", "dq_outcome"],
            target_entity_types=["time_point"],
            standard_mappings=["prov:atTime"],
        ),
        OntologyRelationTypeView(
            relation_type="emits_event",
            label="Emits Event",
            description="Connects a DQ outcome to the event that emitted or summarized it.",
            source_entity_types=["dq_outcome"],
            target_entity_types=["event"],
            standard_mappings=["prov:wasGeneratedBy"],
        ),
    ]

    return CanonicalOntologyView(
        ontology_id=_ONTOLOGY_ID,
        ontology_name=_ONTOLOGY_NAME,
        version=_ONTOLOGY_VERSION,
        scope=OntologyScopeView(
            description=(
                "Canonical vocabulary for the metadata foundation across domains, datasets, data products, "
                "rules, validation plans, validation suites, business concepts, DQ outcomes, temporal anchors, "
                "events, and organizational hierarchy. The ontology describes the graph boundary only; source "
                "systems remain the system of record for their own data."
            ),
            in_scope_entities=[
                "domain",
                "data_product",
                "dataset",
                "data_object",
                "data_object_version",
                "attribute",
                "business_concept",
                "rule",
                "validation_suite",
                "validation_plan",
                "dq_outcome",
                "incident",
                "external_party",
                "workspace",
                "time_point",
                "event",
                "organizational_hierarchy",
                "organizational_unit",
            ],
            out_of_scope_entities=[
                "raw_fact_payload",
                "restricted_record_values",
                "execution_engine_internal_state",
            ],
        ),
        entity_types=entity_types,
        relation_types=relation_types,
        standard_alignments=[
            OntologyStandardAlignmentView(
                standard_name="RDF 1.1 Concepts and Abstract Syntax",
                standard_uri="https://www.w3.org/TR/rdf11-concepts/",
                usage="Canonical triple-style graph representation and URI-based identifiers.",
                alignment_scope=["all_entities", "all_relations"],
            ),
            OntologyStandardAlignmentView(
                standard_name="RDFS and OWL 2",
                standard_uri="https://www.w3.org/TR/owl2-overview/",
                usage="Class and relation vocabulary for the ontology model and its subclasses.",
                alignment_scope=["entity_types", "relation_types"],
            ),
            OntologyStandardAlignmentView(
                standard_name="SKOS Reference",
                standard_uri="https://www.w3.org/TR/skos-reference/",
                usage="Controlled vocabularies and governed business-concept labels.",
                alignment_scope=["domain", "business_concept"],
            ),
            OntologyStandardAlignmentView(
                standard_name="DCAT Version 3",
                standard_uri="https://www.w3.org/TR/vocab-dcat-3/",
                usage="Dataset and catalog alignment for data products and datasets.",
                alignment_scope=["data_product", "dataset"],
            ),
            OntologyStandardAlignmentView(
                standard_name="Dublin Core Metadata Terms",
                standard_uri="https://www.dublincore.org/specifications/dublin-core/dcmi-terms/",
                usage="Descriptive relationships and collection-style metadata boundaries.",
                alignment_scope=["domain", "dataset", "data_object"],
            ),
            OntologyStandardAlignmentView(
                standard_name="PROV-O",
                standard_uri="https://www.w3.org/TR/prov-o/",
                usage="Provenance, derivation, and execution-result relationships for DQ outcomes.",
                alignment_scope=["rule", "validation_plan", "dq_outcome", "incident", "external_party", "event", "time_point"],
            ),
            OntologyStandardAlignmentView(
                standard_name="W3C ORG Ontology",
                standard_uri="https://www.w3.org/TR/vocab-org/",
                usage="Organizational hierarchy and unit membership alignment for governance and ownership.",
                alignment_scope=["organizational_hierarchy", "organizational_unit"],
            ),
            OntologyStandardAlignmentView(
                standard_name="SHACL",
                standard_uri="https://www.w3.org/TR/shacl/",
                usage="Shape constraints for canonical graph validation and completeness checks.",
                alignment_scope=["scope", "entity_types", "relation_types"],
            ),
        ],
        graph=OntologyGraphView(
            graph_id="dq-made-easy-domain-knowledge-graph",
            graph_name="dq-made-easy Domain Knowledge Graph",
            graph_description="Canonical graph projection of the ontology scope, entity vocabulary, relation vocabulary, temporal anchors, and organizational hierarchy.",
            node_count=len(entity_types),
            edge_count=len(relation_types),
            nodes=_build_graph_nodes(entity_types),
            edges=_build_graph_edges(relation_types),
        ),
    )


def build_canonical_ontology_jsonld() -> dict[str, Any]:
    ontology = build_canonical_ontology()
    ontology_payload = ontology.model_dump(mode="python", by_alias=True, exclude_none=True)

    def _iri(entity_type: str, value: str) -> str:
        return f"urn:dq:ontology:{entity_type}:{value}"

    classes = [
        {
            "@id": _iri("entity_type", entity_type["entity_type"]),
            "@type": "rdfs:Class",
            "rdfs:label": entity_type["label"],
            "rdfs:comment": entity_type["description"],
            "standard_mappings": list(entity_type.get("standard_mappings") or []),
        }
        for entity_type in ontology_payload.get("entity_types", [])
    ]

    relations = [
        {
            "@id": _iri("relation_type", relation_type["relation_type"]),
            "@type": "rdf:Property",
            "rdfs:label": relation_type["label"],
            "rdfs:comment": relation_type["description"],
            "source_entity_types": list(relation_type.get("source_entity_types") or []),
            "target_entity_types": list(relation_type.get("target_entity_types") or []),
            "standard_mappings": list(relation_type.get("standard_mappings") or []),
        }
        for relation_type in ontology_payload.get("relation_types", [])
    ]

    graph_payload = ontology_payload.get("graph", {})
    jsonld_nodes = [
        {
            "@id": _iri("graph_node", node["node_id"]),
            "@type": "rdfs:Class",
            "node_type": node["node_type"],
            "label": node["label"],
            "description": node["description"],
            "standard_mappings": list(node.get("standard_mappings") or []),
        }
        for node in graph_payload.get("nodes", [])
    ]
    jsonld_edges = [
        {
            "@id": _iri("graph_edge", edge["edge_type"]),
            "@type": "rdf:Property",
            "edge_type": edge["edge_type"],
            "label": edge["label"],
            "description": edge["description"],
            "source_node_types": list(edge.get("source_node_types") or []),
            "target_node_types": list(edge.get("target_node_types") or []),
            "standard_mappings": list(edge.get("standard_mappings") or []),
        }
        for edge in graph_payload.get("edges", [])
    ]

    return {
        "@context": {
            "rdf": "http://www.w3.org/1999/02/22-rdf-syntax-ns#",
            "rdfs": "http://www.w3.org/2000/01/rdf-schema#",
            "owl": "http://www.w3.org/2002/07/owl#",
            "skos": "http://www.w3.org/2004/02/skos/core#",
            "dcat": "http://www.w3.org/ns/dcat#",
            "prov": "http://www.w3.org/ns/prov#",
            "dq": "urn:dq:ontology:",
        },
        "@id": _iri("ontology", ontology_payload["ontology_id"]),
        "@type": "owl:Ontology",
        "ontology_id": ontology_payload["ontology_id"],
        "ontology_name": ontology_payload["ontology_name"],
        "version": ontology_payload["version"],
        "scope": ontology_payload["scope"],
        "entity_types": classes,
        "relation_types": relations,
        "standard_alignments": ontology_payload.get("standard_alignments", []),
        "graph": {
            "@id": _iri("graph", graph_payload.get("graph_id", "")),
            "@type": "rdf:Bag",
            "graph_id": graph_payload.get("graph_id", ""),
            "graph_name": graph_payload.get("graph_name", ""),
            "graph_description": graph_payload.get("graph_description", ""),
            "node_count": graph_payload.get("node_count", 0),
            "edge_count": graph_payload.get("edge_count", 0),
            "nodes": jsonld_nodes,
            "edges": jsonld_edges,
        },
    }
