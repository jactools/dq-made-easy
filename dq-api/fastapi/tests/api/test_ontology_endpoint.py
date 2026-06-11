from __future__ import annotations


def test_get_canonical_ontology(client, auth_headers) -> None:
    response = client.get(
        "/api/data-catalog/v1/ontology/canonical",
        headers=auth_headers("dq:data_catalog:read"),
    )

    assert response.status_code == 200
    payload = response.json()

    assert payload["ontology_id"] == "dq-made-easy-domain-ontology"
    assert payload["ontology_name"] == "dq-made-easy Domain Ontology"
    assert payload["version"] == "1.0"

    graph = payload["graph"]
    assert graph["graph_id"] == "dq-made-easy-domain-knowledge-graph"
    assert graph["graph_name"] == "dq-made-easy Domain Knowledge Graph"
    assert graph["node_count"] == len(graph["nodes"])
    assert graph["edge_count"] == len(graph["edges"])

    scope = payload["scope"]
    assert "domain" in scope["in_scope_entities"]
    assert "dq_outcome" in scope["in_scope_entities"]
    assert "time_point" in scope["in_scope_entities"]
    assert "event" in scope["in_scope_entities"]
    assert "organizational_hierarchy" in scope["in_scope_entities"]
    assert "raw_fact_payload" in scope["out_of_scope_entities"]

    entity_types = {item["entity_type"] for item in payload["entity_types"]}
    assert {
        "domain",
        "data_product",
        "dataset",
        "rule",
        "validation_suite",
        "validation_plan",
        "dq_outcome",
    }.issubset(entity_types)

    graph_node_types = {item["node_type"] for item in graph["nodes"]}
    assert {
        "domain",
        "data_product",
        "dataset",
        "rule",
        "validation_suite",
        "validation_plan",
        "dq_outcome",
        "time_point",
        "event",
        "organizational_hierarchy",
        "organizational_unit",
    }.issubset(graph_node_types)

    relation_types = {item["relation_type"] for item in payload["relation_types"]}
    assert {
        "belongs_to_domain",
        "contains_dataset",
        "governs_rule",
        "produces_dq_outcome",
    }.issubset(relation_types)

    graph_edge_types = {item["edge_type"] for item in graph["edges"]}
    assert {
        "belongs_to_domain",
        "contains_dataset",
        "governs_rule",
        "supports_validation_suite",
        "supports_validation_plan",
        "produces_dq_outcome",
        "belongs_to_organizational_unit",
        "contains_organizational_unit",
        "parent_organizational_unit",
        "occurs_at_time_point",
        "emits_event",
    }.issubset(graph_edge_types)

    standard_names = {item["standard_name"] for item in payload["standard_alignments"]}
    assert {
        "RDF 1.1 Concepts and Abstract Syntax",
        "DCAT Version 3",
        "PROV-O",
        "SHACL",
    }.issubset(standard_names)


def test_get_canonical_ontology_jsonld(client, auth_headers) -> None:
    response = client.get(
        "/api/data-catalog/v1/ontology/canonical/json-ld",
        headers=auth_headers("dq:data_catalog:read"),
    )

    assert response.status_code == 200
    payload = response.json()

    assert payload["@type"] == "owl:Ontology"
    assert payload["ontology_id"] == "dq-made-easy-domain-ontology"
    assert payload["graph"]["graph_id"] == "dq-made-easy-domain-knowledge-graph"
    assert payload["graph"]["node_count"] == len(payload["graph"]["nodes"])
    assert payload["graph"]["edge_count"] == len(payload["graph"]["edges"])
    assert "rdf" in payload["@context"]
    assert "prov" in payload["@context"]

    class_ids = {entry["@id"] for entry in payload["entity_types"]}
    relation_ids = {entry["@id"] for entry in payload["relation_types"]}
    assert "urn:dq:ontology:entity_type:domain" in class_ids
    assert "urn:dq:ontology:relation_type:belongs_to_domain" in relation_ids
