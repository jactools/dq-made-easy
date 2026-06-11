from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
from uuid import uuid4

from app.api.v1.schemas.ontology_view import OntologyGraphProjectionEdgeView
from app.api.v1.schemas.ontology_view import OntologyGraphProjectionGraphView
from app.api.v1.schemas.ontology_view import OntologyGraphProjectionNodeView
from app.api.v1.schemas.ontology_view import OntologyGraphProjectionRequestView
from app.api.v1.schemas.ontology_view import OntologyGraphProjectionView
from app.api.v1.schemas.ontology_view import OntologyGraphSnapshotView
from app.domain.entities import DataObjectCatalogEntity
from app.domain.entities import DataObjectVersionEntity
from app.domain.entities import DataProductEntity
from app.domain.entities import DataSetEntity
from app.domain.entities import DomainEntity
from app.domain.entities import DqResultEventEntity
from app.domain.entities import IncidentEntity
from app.domain.entities import OntologyGraphSnapshotEntity
from app.domain.entities import RuleRecordEntity
from app.domain.entities import ValidationRunPlanEntity
from app.domain.entities import ValidationRunPlanScopeSelectorEntity
from app.domain.interfaces.v1.data_catalog_repository import DataCatalogRepository
from app.domain.interfaces.v1.dq_result_event_repository import DqResultEventRepository
from app.domain.interfaces.v1.incident_repository import IncidentRepository
from app.domain.interfaces.v1.ontology_graph_repository import OntologyGraphRepository
from app.domain.interfaces.v1.rules_repository import RulesRepository
from app.domain.interfaces.v1.validation_run_plan_repository import ValidationRunPlanRepository


_GRAPH_ID = "dq-made-easy-domain-knowledge-graph"
_GRAPH_NAME = "dq-made-easy Domain Knowledge Graph"
_GRAPH_DESCRIPTION = (
    "Persisted projection of metadata, governance, and execution seams into the canonical ontology graph."
)

_NODE_STANDARD_MAPPINGS: dict[str, list[str]] = {
    "workspace": ["prov:Agent"],
    "domain": ["skos:ConceptScheme"],
    "data_product": ["dcat:Dataset", "prov:Entity"],
    "dataset": ["dcat:Dataset", "prov:Entity"],
    "data_object": ["prov:Entity"],
    "data_object_version": ["prov:Entity", "prov:Revision"],
    "attribute": ["rdf:Property"],
    "business_concept": ["skos:Concept"],
    "rule": ["prov:Entity"],
    "validation_suite": ["prov:Entity"],
    "validation_plan": ["prov:Plan"],
    "dq_outcome": ["prov:Entity", "prov:Activity"],
    "event": ["prov:Activity"],
    "incident": ["prov:Activity"],
    "time_point": ["prov:InstantaneousEvent", "xsd:dateTime"],
}

_RELATION_STANDARD_MAPPINGS: dict[str, list[str]] = {
    "contains_data_product": ["dcterms:hasPart"],
    "contains_dataset": ["dcterms:hasPart", "dcat:dataset"],
    "contains_domain": ["dcterms:hasPart"],
    "contains_data_object": ["dcterms:hasPart"],
    "has_version": ["prov:hadRevision"],
    "has_attribute": ["rdf:predicate"],
    "describes_business_concept": ["skos:related"],
    "belongs_to_domain": ["dcterms:isPartOf", "skos:inScheme"],
    "governs_domain": ["prov:wasAssociatedWith"],
    "governs_rule": ["prov:wasAssociatedWith"],
    "supports_validation_suite": ["prov:wasGeneratedBy"],
    "supports_validation_plan": ["prov:hadPlan"],
    "produces_dq_outcome": ["prov:generated", "prov:wasGeneratedBy"],
    "impacts_incident": ["prov:wasInfluencedBy"],
    "occurs_at_time_point": ["prov:atTime"],
    "emits_event": ["prov:wasGeneratedBy"],
}


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _normalized_text(value: object) -> str:
    return str(value or "").strip()


def _node_standard_mappings(node_type: str) -> list[str]:
    return list(_NODE_STANDARD_MAPPINGS.get(node_type, []))


def _relation_standard_mappings(relation_type: str) -> list[str]:
    return list(_RELATION_STANDARD_MAPPINGS.get(relation_type, []))


def _node_id(node_type: str, value: str) -> str:
    return f"{node_type}:{value}"


def _edge_id(source_node_id: str, relation_type: str, target_node_id: str) -> str:
    return f"{source_node_id}::{relation_type}::{target_node_id}"


def _add_node(nodes: dict[str, OntologyGraphProjectionNodeView], *, node_type: str, raw_id: str, label: str, description: str) -> str:
    normalized_raw_id = _normalized_text(raw_id)
    if not normalized_raw_id:
        raise ValueError(f"{node_type} node id is required")
    node_id = _node_id(node_type, normalized_raw_id)
    if node_id not in nodes:
        nodes[node_id] = OntologyGraphProjectionNodeView(
            node_id=node_id,
            node_type=node_type,
            label=label or normalized_raw_id,
            description=description or label or normalized_raw_id,
            standard_mappings=_node_standard_mappings(node_type),
        )
    return node_id


def _add_edge(
    edges: dict[str, OntologyGraphProjectionEdgeView],
    *,
    relation_type: str,
    source_node_id: str,
    source_node_type: str,
    target_node_id: str,
    target_node_type: str,
    label: str,
    description: str,
) -> None:
    edge_id = _edge_id(source_node_id, relation_type, target_node_id)
    if edge_id not in edges:
        edges[edge_id] = OntologyGraphProjectionEdgeView(
            edge_id=edge_id,
            relation_type=relation_type,
            source_node_id=source_node_id,
            target_node_id=target_node_id,
            source_node_type=source_node_type,
            target_node_type=target_node_type,
            label=label,
            description=description,
            standard_mappings=_relation_standard_mappings(relation_type),
        )


def _matches_scope_tags(entity_tags: Sequence[str], scope_tag_ids: Sequence[str]) -> bool:
    normalized_entity_tags = {str(tag).strip() for tag in entity_tags if str(tag).strip()}
    normalized_scope_tags = {str(tag).strip() for tag in scope_tag_ids if str(tag).strip()}
    return bool(normalized_entity_tags and normalized_scope_tags and normalized_entity_tags.intersection(normalized_scope_tags))


def _scope_matches_asset(
    *,
    scope: ValidationRunPlanScopeSelectorEntity,
    product: DataProductEntity | None = None,
    data_set: DataSetEntity | None = None,
    data_object: DataObjectCatalogEntity | None = None,
) -> bool:
    if scope.dataProductId and product is not None and _normalized_text(scope.dataProductId) == _normalized_text(product.id):
        return True
    if scope.datasetId and data_set is not None and _normalized_text(scope.datasetId) == _normalized_text(data_set.id):
        return True
    if scope.dataObjectId and data_object is not None and _normalized_text(scope.dataObjectId) == _normalized_text(data_object.id):
        return True
    if scope.tagIds:
        if product is not None and _matches_scope_tags(product.tags, scope.tagIds):
            return True
        if data_set is not None and _matches_scope_tags(data_set.tags, scope.tagIds):
            return True
        if data_object is not None and _matches_scope_tags(data_object.tags, scope.tagIds):
            return True
    return False


def _build_graph_nodes_and_edges(
    *,
    workspace_id: str | None,
    data_product_id: str | None,
    data_products: list[DataProductEntity],
    data_sets: list[DataSetEntity],
    domains: list[DomainEntity],
    data_objects_by_set_id: dict[str, list[DataObjectCatalogEntity]],
    data_object_versions_by_object_id: dict[str, list[DataObjectVersionEntity]],
    attributes_by_version_id: dict[str, list],
    rules: list[RuleRecordEntity],
    validation_run_plans: list[ValidationRunPlanEntity],
    dq_result_events: list[DqResultEventEntity],
    incidents: list[IncidentEntity],
) -> tuple[OntologyGraphProjectionGraphView, dict[str, object]]:
    nodes: dict[str, OntologyGraphProjectionNodeView] = {}
    edges: dict[str, OntologyGraphProjectionEdgeView] = {}
    summary: dict[str, object] = {
        "data_products": len(data_products),
        "data_sets": len(data_sets),
        "domains": len(domains),
        "data_objects": sum(len(items) for items in data_objects_by_set_id.values()),
        "data_object_versions": sum(len(items) for items in data_object_versions_by_object_id.values()),
        "attributes": sum(len(items) for items in attributes_by_version_id.values()),
        "rules": len(rules),
        "validation_run_plans": len(validation_run_plans),
        "dq_result_events": len(dq_result_events),
        "incidents": len(incidents),
    }

    workspace_node_id: str | None = None
    if workspace_id:
        workspace_node_id = _add_node(
            nodes,
            node_type="workspace",
            raw_id=workspace_id,
            label=workspace_id,
            description=f"Workspace {workspace_id}",
        )

    # Create domain nodes and connect them to workspace if applicable
    domains_by_id: dict[str, DomainEntity] = {}
    domain_node_ids: dict[str, str] = {}
    for domain in domains:
        domain_id = _normalized_text(domain.id)
        if not domain_id:
            continue
        domains_by_id[domain_id] = domain
        domain_node_id = _add_node(
            nodes,
            node_type="domain",
            raw_id=domain_id,
            label=domain.name or domain_id,
            description=domain.description or f"Domain {domain.name or domain_id}",
        )
        domain_node_ids[domain_id] = domain_node_id
        
        # Connect domain to workspace if both exist
        if workspace_node_id and domain.workspace_id and _normalized_text(domain.workspace_id) == _normalized_text(workspace_id or domain.workspace_id):
            _add_edge(
                edges,
                relation_type="contains_domain",
                source_node_id=workspace_node_id,
                source_node_type="workspace",
                target_node_id=domain_node_id,
                target_node_type="domain",
                label="contains domain",
                description=f"Workspace {workspace_id} contains domain {domain.name or domain_id}",
            )

    products_by_id = {str(product.id): product for product in data_products}
    datasets_by_id = {str(data_set.id): data_set for data_set in data_sets}

    for product in data_products:
        product_node_id = _add_node(
            nodes,
            node_type="data_product",
            raw_id=product.id,
            label=product.name or product.id,
            description=f"Data product {product.name or product.id} in workspace {product.workspace_id or workspace_id or ''}".strip(),
        )
        if product.workspace_id:
            workspace_node_id = workspace_node_id or _add_node(
                nodes,
                node_type="workspace",
                raw_id=product.workspace_id,
                label=product.workspace_id,
                description=f"Workspace {product.workspace_id}",
            )
            _add_edge(
                edges,
                relation_type="contains_data_product",
                source_node_id=workspace_node_id,
                source_node_type="workspace",
                target_node_id=product_node_id,
                target_node_type="data_product",
                label="contains data product",
                description=f"Workspace {product.workspace_id} contains data product {product.name or product.id}",
            )
            
            # Connect data product to domain if tags or other metadata indicate domain association
            product_domain_candidates = set()
            # Check if product tags contain domain references
            for tag in product.tags:
                normalized_tag = _normalized_text(tag)
                if normalized_tag in domain_node_ids:
                    product_domain_candidates.add(normalized_tag)
            
            # Also check if product business_key matches any domain
            product_business_key = _normalized_text(product.business_key)
            if product_business_key in domain_node_ids:
                product_domain_candidates.add(product_business_key)
            
            # Connect product to domains
            for domain_id in product_domain_candidates:
                _add_edge(
                    edges,
                    relation_type="belongs_to_domain",
                    source_node_id=product_node_id,
                    source_node_type="data_product",
                    target_node_id=domain_node_ids[domain_id],
                    target_node_type="domain",
                    label="belongs to domain",
                    description=f"Data product {product.name or product.id} belongs to domain {domain_id}",
                )

    for data_set in data_sets:
        data_set_node_id = _add_node(
            nodes,
            node_type="dataset",
            raw_id=data_set.id,
            label=data_set.name or data_set.id,
            description=f"Dataset {data_set.name or data_set.id} in workspace {data_set.workspace_id or workspace_id or ''}".strip(),
        )
        if data_set.product_id and data_set.product_id in products_by_id:
            product = products_by_id[data_set.product_id]
            product_node_id = _node_id("data_product", product.id)
            _add_edge(
                edges,
                relation_type="contains_dataset",
                source_node_id=product_node_id,
                source_node_type="data_product",
                target_node_id=data_set_node_id,
                target_node_type="dataset",
                label="contains dataset",
                description=f"Data product {product.name or product.id} contains dataset {data_set.name or data_set.id}",
            )
            
            # Connect dataset to domain if tags or other metadata indicate domain association
            dataset_domain_candidates = set()
            # Check if dataset tags contain domain references
            for tag in data_set.tags:
                normalized_tag = _normalized_text(tag)
                if normalized_tag in domain_node_ids:
                    dataset_domain_candidates.add(normalized_tag)
            
            # Also check if dataset business_key matches any domain
            dataset_business_key = _normalized_text(data_set.business_key)
            if dataset_business_key in domain_node_ids:
                dataset_domain_candidates.add(dataset_business_key)
            
            # Connect dataset to domains
            for domain_id in dataset_domain_candidates:
                _add_edge(
                    edges,
                    relation_type="belongs_to_domain",
                    source_node_id=data_set_node_id,
                    source_node_type="dataset",
                    target_node_id=domain_node_ids[domain_id],
                    target_node_type="domain",
                    label="belongs to domain",
                    description=f"Dataset {data_set.name or data_set.id} belongs to domain {domain_id}",
                )

    for data_set_id, data_objects in data_objects_by_set_id.items():
        data_set = datasets_by_id.get(data_set_id)
        if data_set is None:
            continue
        data_set_node_id = _node_id("dataset", data_set.id)
        for data_object in data_objects:
            data_object_node_id = _add_node(
                nodes,
                node_type="data_object",
                raw_id=data_object.id,
                label=data_object.name or data_object.id,
                description=f"Data object {data_object.name or data_object.id} in dataset {data_set.name or data_set.id}",
            )
            _add_edge(
                edges,
                relation_type="contains_data_object",
                source_node_id=data_set_node_id,
                source_node_type="dataset",
                target_node_id=data_object_node_id,
                target_node_type="data_object",
                label="contains data object",
                description=f"Dataset {data_set.name or data_set.id} contains data object {data_object.name or data_object.id}",
            )

            for data_object_version in data_object_versions_by_object_id.get(str(data_object.id), []):
                data_object_version_node_id = _add_node(
                    nodes,
                    node_type="data_object_version",
                    raw_id=data_object_version.id,
                    label=f"Version {data_object_version.version}",
                    description=f"Version {data_object_version.version} of data object {data_object.name or data_object.id}",
                )
                _add_edge(
                    edges,
                    relation_type="has_version",
                    source_node_id=data_object_node_id,
                    source_node_type="data_object",
                    target_node_id=data_object_version_node_id,
                    target_node_type="data_object_version",
                    label="has version",
                    description=f"Data object {data_object.name or data_object.id} has version {data_object_version.version}",
                )

                for attribute in attributes_by_version_id.get(str(data_object_version.id), []):
                    attribute_node_id = _add_node(
                        nodes,
                        node_type="attribute",
                        raw_id=attribute.id,
                        label=attribute.name or attribute.id,
                        description=f"Attribute {attribute.name or attribute.id} on version {data_object_version.version}",
                    )
                    _add_edge(
                        edges,
                        relation_type="has_attribute",
                        source_node_id=data_object_version_node_id,
                        source_node_type="data_object_version",
                        target_node_id=attribute_node_id,
                        target_node_type="attribute",
                        label="has attribute",
                        description=f"Version {data_object_version.version} exposes attribute {attribute.name or attribute.id}",
                    )

                    definition_id = _normalized_text(getattr(attribute, "definition_id", None))
                    if definition_id:
                        business_concept_node_id = _add_node(
                            nodes,
                            node_type="business_concept",
                            raw_id=definition_id,
                            label=definition_id,
                            description=f"Business concept {definition_id}",
                        )
                        _add_edge(
                            edges,
                            relation_type="describes_business_concept",
                            source_node_id=attribute_node_id,
                            source_node_type="attribute",
                            target_node_id=business_concept_node_id,
                            target_node_type="business_concept",
                            label="describes business concept",
                            description=f"Attribute {attribute.name or attribute.id} describes business concept {definition_id}",
                        )

    for rule in rules:
        rule_node_id = _add_node(
            nodes,
            node_type="rule",
            raw_id=rule.id,
            label=rule.name,
            description=rule.description or f"Rule {rule.name}",
        )

        rule_scope_candidates = {
            _normalized_text(rule.workspace),
            _normalized_text(getattr(getattr(rule, "taxonomy", None), "domain", None)),
            _normalized_text(getattr(getattr(rule, "taxonomy", None), "owner", None)),
        }
        
        # Extract domain from rule taxonomy and connect to domain node
        rule_domain_id = _normalized_text(getattr(getattr(rule, "taxonomy", None), "domain", None))
        if rule_domain_id and rule_domain_id in domain_node_ids:
            _add_edge(
                edges,
                relation_type="belongs_to_domain",
                source_node_id=rule_node_id,
                source_node_type="rule",
                target_node_id=domain_node_ids[rule_domain_id],
                target_node_type="domain",
                label="belongs to domain",
                description=f"Rule {rule.name} belongs to domain {rule_domain_id}",
            )
            # Also connect domain to rule (reverse relation)
            _add_edge(
                edges,
                relation_type="governs_rule",
                source_node_id=domain_node_ids[rule_domain_id],
                source_node_type="domain",
                target_node_id=rule_node_id,
                target_node_type="rule",
                label="governs rule",
                description=f"Domain {rule_domain_id} governs rule {rule.name}",
            )
        
        for product in data_products:
            if rule_scope_candidates.intersection({_normalized_text(product.id), _normalized_text(product.business_key), _normalized_text(product.workspace_id)}):
                _add_edge(
                    edges,
                    relation_type="governs_rule",
                    source_node_id=_node_id("data_product", product.id),
                    source_node_type="data_product",
                    target_node_id=rule_node_id,
                    target_node_type="rule",
                    label="governs rule",
                    description=f"Data product {product.name or product.id} governs rule {rule.name}",
                )
        for data_set in data_sets:
            if rule_scope_candidates.intersection({_normalized_text(data_set.id), _normalized_text(data_set.business_key), _normalized_text(data_set.workspace_id)}):
                _add_edge(
                    edges,
                    relation_type="governs_rule",
                    source_node_id=_node_id("dataset", data_set.id),
                    source_node_type="dataset",
                    target_node_id=rule_node_id,
                    target_node_type="rule",
                    label="governs rule",
                    description=f"Dataset {data_set.name or data_set.id} governs rule {rule.name}",
                )

    for plan in validation_run_plans:
        plan_node_id = _add_node(
            nodes,
            node_type="validation_plan",
            raw_id=plan.runPlanId,
            label=plan.businessKey or plan.runPlanId,
            description=f"Validation plan {plan.runPlanId} in {plan.workspaceId}",
        )
        suite_node_id = _add_node(
            nodes,
            node_type="validation_suite",
            raw_id=plan.runPlanId,
            label=plan.businessKey or plan.runPlanId,
            description=f"Validation suite projected from plan {plan.runPlanId}",
        )
        _add_edge(
            edges,
            relation_type="supports_validation_plan",
            source_node_id=suite_node_id,
            source_node_type="validation_suite",
            target_node_id=plan_node_id,
            target_node_type="validation_plan",
            label="supports validation plan",
            description=f"Validation suite for plan {plan.runPlanId}",
        )

        scope = plan.scopeSelector
        if workspace_node_id is not None and scope.workspaceId and _normalized_text(scope.workspaceId) == _normalized_text(workspace_id or scope.workspaceId):
            _add_edge(
                edges,
                relation_type="contains_dataset",
                source_node_id=workspace_node_id,
                source_node_type="workspace",
                target_node_id=suite_node_id,
                target_node_type="validation_suite",
                label="contains validation suite",
                description=f"Workspace {scope.workspaceId} contains validation suite for plan {plan.runPlanId}",
            )

        for product in data_products:
            if _scope_matches_asset(scope=scope, product=product):
                _add_edge(
                    edges,
                    relation_type="supports_validation_suite",
                    source_node_id=_node_id("data_product", product.id),
                    source_node_type="data_product",
                    target_node_id=suite_node_id,
                    target_node_type="validation_suite",
                    label="supports validation suite",
                    description=f"Data product {product.name or product.id} supports validation suite for plan {plan.runPlanId}",
                )
        for data_set in data_sets:
            if _scope_matches_asset(scope=scope, data_set=data_set):
                _add_edge(
                    edges,
                    relation_type="supports_validation_suite",
                    source_node_id=_node_id("dataset", data_set.id),
                    source_node_type="dataset",
                    target_node_id=suite_node_id,
                    target_node_type="validation_suite",
                    label="supports validation suite",
                    description=f"Dataset {data_set.name or data_set.id} supports validation suite for plan {plan.runPlanId}",
                )
        for data_objects in data_objects_by_set_id.values():
            for data_object in data_objects:
                if _scope_matches_asset(scope=scope, data_object=data_object):
                    _add_edge(
                        edges,
                        relation_type="supports_validation_suite",
                        source_node_id=_node_id("data_object", data_object.id),
                        source_node_type="data_object",
                        target_node_id=suite_node_id,
                        target_node_type="validation_suite",
                        label="supports validation suite",
                        description=f"Data object {data_object.name or data_object.id} supports validation suite for plan {plan.runPlanId}",
                    )

    dq_outcome_nodes_by_rule_id: dict[str, str] = {}
    for event in dq_result_events:
        event_id = _normalized_text(getattr(event.correlation, "correlationId", None) or event.correlation.correlationId)
        if not event_id:
            event_id = _normalized_text(getattr(event.correlation, "runId", None) or event.runOutcome.observedAt or event.emittedAt)
        event_node_id = _add_node(
            nodes,
            node_type="event",
            raw_id=event_id,
            label=event.eventType,
            description=f"DQ result event emitted at {event.emittedAt}",
        )

        outcome_id = _normalized_text(event.correlation.correlationId or event.correlation.runId or event.emittedAt)
        dq_outcome_node_id = _add_node(
            nodes,
            node_type="dq_outcome",
            raw_id=outcome_id,
            label=event.runOutcome.status,
            description=f"DQ outcome {event.runOutcome.status} for rule {event.rule.id} and dataset {event.dataset.id}",
        )
        dq_outcome_nodes_by_rule_id[str(event.rule.id)] = dq_outcome_node_id
        
        # Connect DQ outcome to domain if available in the event
        if event.domain and event.domain.id:
            event_domain_id = _normalized_text(event.domain.id)
            if event_domain_id and event_domain_id not in domain_node_ids:
                # Create domain node from DQ result event if it doesn't exist yet
                domain_node_id = _add_node(
                    nodes,
                    node_type="domain",
                    raw_id=event_domain_id,
                    label=event.domain.name or event_domain_id,
                    description=f"Domain {event.domain.name or event_domain_id} from DQ result event",
                )
                domain_node_ids[event_domain_id] = domain_node_id
                domains_by_id[event_domain_id] = DomainEntity(id=event_domain_id, name=event.domain.name or event_domain_id)
            
            if event_domain_id in domain_node_ids:
                _add_edge(
                    edges,
                    relation_type="belongs_to_domain",
                    source_node_id=dq_outcome_node_id,
                    source_node_type="dq_outcome",
                    target_node_id=domain_node_ids[event_domain_id],
                    target_node_type="domain",
                    label="belongs to domain",
                    description=f"DQ outcome {event.runOutcome.status} belongs to domain {event.domain.name or event_domain_id}",
                )

        _add_edge(
            edges,
            relation_type="emits_event",
            source_node_id=dq_outcome_node_id,
            source_node_type="dq_outcome",
            target_node_id=event_node_id,
            target_node_type="event",
            label="emits event",
            description=f"DQ outcome {event.runOutcome.status} emits event {event.eventType}",
        )

        time_point_node_id = _add_node(
            nodes,
            node_type="time_point",
            raw_id=event.emittedAt,
            label=event.emittedAt,
            description=f"Time point for DQ event {event.eventType}",
        )
        _add_edge(
            edges,
            relation_type="occurs_at_time_point",
            source_node_id=event_node_id,
            source_node_type="event",
            target_node_id=time_point_node_id,
            target_node_type="time_point",
            label="occurs at time point",
            description=f"Event {event.eventType} occurred at {event.emittedAt}",
        )
        _add_edge(
            edges,
            relation_type="occurs_at_time_point",
            source_node_id=dq_outcome_node_id,
            source_node_type="dq_outcome",
            target_node_id=time_point_node_id,
            target_node_type="time_point",
            label="occurs at time point",
            description=f"DQ outcome {event.runOutcome.status} occurred at {event.emittedAt}",
        )

        rule_node_id = _node_id("rule", event.rule.id)
        if rule_node_id in nodes:
            _add_edge(
                edges,
                relation_type="produces_dq_outcome",
                source_node_id=rule_node_id,
                source_node_type="rule",
                target_node_id=dq_outcome_node_id,
                target_node_type="dq_outcome",
                label="produces DQ outcome",
                description=f"Rule {event.rule.name or event.rule.id} produces outcome {event.runOutcome.status}",
            )

        if event.runOutcome.observedAt:
            observed_time_point_node_id = _add_node(
                nodes,
                node_type="time_point",
                raw_id=event.runOutcome.observedAt,
                label=event.runOutcome.observedAt,
                description=f"Observed time point for DQ outcome {event.runOutcome.status}",
            )
            _add_edge(
                edges,
                relation_type="occurs_at_time_point",
                source_node_id=dq_outcome_node_id,
                source_node_type="dq_outcome",
                target_node_id=observed_time_point_node_id,
                target_node_type="time_point",
                label="occurs at time point",
                description=f"DQ outcome {event.runOutcome.status} observed at {event.runOutcome.observedAt}",
            )

    for incident in incidents:
        incident_node_id = _add_node(
            nodes,
            node_type="incident",
            raw_id=incident.id,
            label=incident.title,
            description=incident.description or f"Incident {incident.id}",
        )

        incident_time = _normalized_text(incident.created_at or incident.updated_at or incident.resolved_at)
        if incident_time:
            time_point_node_id = _add_node(
                nodes,
                node_type="time_point",
                raw_id=incident_time,
                label=incident_time,
                description=f"Time point for incident {incident.id}",
            )
            _add_edge(
                edges,
                relation_type="occurs_at_time_point",
                source_node_id=incident_node_id,
                source_node_type="incident",
                target_node_id=time_point_node_id,
                target_node_type="time_point",
                label="occurs at time point",
                description=f"Incident {incident.title} occurred at {incident_time}",
            )

        correlation_id = _normalized_text(incident.source_correlation_id or incident.run_id or incident.source_request_id)
        if correlation_id:
            for event in dq_result_events:
                if _normalized_text(event.correlation.correlationId) == correlation_id or _normalized_text(event.correlation.runId) == _normalized_text(incident.run_id):
                    dq_outcome_node_id = dq_outcome_nodes_by_rule_id.get(str(event.rule.id))
                    if dq_outcome_node_id:
                        _add_edge(
                            edges,
                            relation_type="impacts_incident",
                            source_node_id=dq_outcome_node_id,
                            source_node_type="dq_outcome",
                            target_node_id=incident_node_id,
                            target_node_type="incident",
                            label="impacts incident",
                            description=f"DQ outcome for rule {event.rule.id} impacts incident {incident.id}",
                        )

    graph_view = OntologyGraphProjectionGraphView(
        graph_id=_GRAPH_ID,
        graph_name=_GRAPH_NAME,
        graph_description=_GRAPH_DESCRIPTION,
        node_count=len(nodes),
        edge_count=len(edges),
        nodes=list(nodes.values()),
        edges=list(edges.values()),
    )
    summary["projection_id"] = f"ontology-graph-snapshot-{uuid4().hex}"
    summary["workspace_id"] = workspace_id
    summary["data_product_id"] = data_product_id
    return graph_view, summary


async def build_ontology_graph_projection(
    *,
    request: OntologyGraphProjectionRequestView,
    data_catalog_repository: DataCatalogRepository,
    rules_repository: RulesRepository,
    validation_run_plan_repository: ValidationRunPlanRepository,
    dq_result_event_repository: DqResultEventRepository,
    incident_repository: IncidentRepository,
    ontology_graph_repository: OntologyGraphRepository,
) -> OntologyGraphProjectionView:
    workspace_id = request.workspace_id
    data_product_id = request.data_product_id

    data_products = data_catalog_repository.list_data_products(workspace=workspace_id)
    if data_product_id:
        data_products = [product for product in data_products if _normalized_text(product.id) == _normalized_text(data_product_id)]
    data_sets = data_catalog_repository.list_data_sets(workspace=workspace_id, product_id=data_product_id)
    
    # Extract domains from existing data sources
    domains: list[DomainEntity] = []
    
    # Try to get domains from data catalog if available
    if hasattr(data_catalog_repository, 'list_domains'):
        try:
            domains = data_catalog_repository.list_domains(workspace=workspace_id)
        except Exception:
            # Fall back to extracting from other sources
            pass
    
    # If no domains from repository, extract from rules and DQ result events
    if not domains:
        domain_ids_from_rules: set[str] = set()
        domain_ids_from_events: set[str] = set()
        
        rules = await rules_repository.list_rule_records(workspace=workspace_id, limit=500, offset=0)
        for rule in rules:
            rule_domain = _normalized_text(getattr(getattr(rule, "taxonomy", None), "domain", None))
            if rule_domain:
                domain_ids_from_rules.add(rule_domain)
        
        dq_result_events = await dq_result_event_repository.list_result_events(
            data_product_id=data_product_id,
            limit=500,
        )
        for event in dq_result_events:
            if event.domain and event.domain.id:
                event_domain_id = _normalized_text(event.domain.id)
                if event_domain_id:
                    domain_ids_from_events.add(event_domain_id)
        
        # Create domain entities from extracted domain IDs
        all_domain_ids = domain_ids_from_rules.union(domain_ids_from_events)
        for domain_id in all_domain_ids:
            domains.append(DomainEntity(id=domain_id, name=domain_id))
    
    data_objects_by_set_id: dict[str, list[DataObjectCatalogEntity]] = {
        data_set.id: data_catalog_repository.list_data_objects_catalog(data_set_id=data_set.id)
        for data_set in data_sets
    }
    data_object_versions_by_object_id: dict[str, list[DataObjectVersionEntity]] = {}
    attributes_by_version_id: dict[str, list] = {}
    for data_objects in data_objects_by_set_id.values():
        for data_object in data_objects:
            data_object_versions = data_catalog_repository.list_data_object_versions(object_id=data_object.id)
            data_object_versions_by_object_id[data_object.id] = data_object_versions
            for data_object_version in data_object_versions:
                attributes_by_version_id[data_object_version.id] = data_catalog_repository.list_attributes_catalog(version_id=data_object_version.id)

    if not rules:
        rules = await rules_repository.list_rule_records(workspace=workspace_id, limit=500, offset=0)
    validation_run_plans = await validation_run_plan_repository.list_plans(workspace_id=workspace_id)
    if not dq_result_events:
        dq_result_events = await dq_result_event_repository.list_result_events(
            data_product_id=data_product_id,
            limit=500,
        )
    incidents = incident_repository.list_incidents(workspace_id=workspace_id, limit=500, offset=0)

    graph_view, source_summary = _build_graph_nodes_and_edges(
        workspace_id=workspace_id,
        data_product_id=data_product_id,
        data_products=data_products,
        data_sets=data_sets,
        domains=domains,
        data_objects_by_set_id=data_objects_by_set_id,
        data_object_versions_by_object_id=data_object_versions_by_object_id,
        attributes_by_version_id=attributes_by_version_id,
        rules=list(rules),
        validation_run_plans=list(validation_run_plans),
        dq_result_events=list(dq_result_events),
        incidents=list(incidents),
    )

    snapshot_entity = OntologyGraphSnapshotEntity(
        id=str(source_summary["projection_id"]),
        graph_id=graph_view.graph_id,
        graph_name=graph_view.graph_name,
        workspace_id=workspace_id,
        data_product_id=data_product_id,
        captured_at=_now_iso(),
        captured_by=request.captured_by,
        node_count=graph_view.node_count,
        edge_count=graph_view.edge_count,
        graph_json=graph_view.model_dump(mode="python", by_alias=True, exclude_none=True),
        source_summary=source_summary,
    )
    stored_snapshot = await ontology_graph_repository.record_ontology_graph_snapshot(snapshot_entity)
    snapshot_view = OntologyGraphSnapshotView.model_validate(stored_snapshot)
    return OntologyGraphProjectionView(snapshot=snapshot_view, graph=graph_view, source_summary=source_summary)
