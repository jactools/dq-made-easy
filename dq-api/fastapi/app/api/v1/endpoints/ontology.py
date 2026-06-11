from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from fastapi import Depends
from fastapi import HTTPException

from app.api.v1.schemas.ontology_view import CanonicalOntologyView
from app.api.v1.schemas.ontology_view import OntologyGraphQueryRequestView
from app.api.v1.schemas.ontology_view import OntologyGraphQueryResultView
from app.api.v1.schemas.ontology_view import OntologyGraphProjectionRequestView
from app.api.v1.schemas.ontology_view import OntologyGraphProjectionView
from app.api.v1.schemas.ontology_view import OntologyGraphTraversalRequestView
from app.api.v1.schemas.ontology_view import OntologyGraphTraversalResultView
from app.application.services.domain_ontology import build_canonical_ontology
from app.application.services.domain_ontology import build_canonical_ontology_jsonld
from app.application.services.ontology_graph_projection import build_ontology_graph_projection
from app.application.services.ontology_graph_read import OntologyGraphLookupError
from app.application.services.ontology_graph_read import query_ontology_graph
from app.application.services.ontology_graph_read import traverse_ontology_graph
from app.core.dependencies import get_data_catalog_repository
from app.core.dependencies import get_dq_result_event_repository
from app.core.dependencies import get_incident_repository
from app.core.dependencies import get_ontology_graph_repository
from app.core.dependencies import get_rules_repository
from app.core.dependencies import get_validation_run_plan_repository
from app.domain.interfaces.v1.data_catalog_repository import DataCatalogRepository
from app.domain.interfaces.v1.dq_result_event_repository import DqResultEventRepository
from app.domain.interfaces.v1.incident_repository import IncidentRepository
from app.domain.interfaces.v1.ontology_graph_repository import OntologyGraphRepository
from app.domain.interfaces.v1.rules_repository import RulesRepository
from app.domain.interfaces.v1.validation_run_plan_repository import ValidationRunPlanRepository



router = APIRouter(tags=["ontology"])


@router.get(
    "/ontology/canonical",
    response_model=CanonicalOntologyView,
    responses={
        200: {"description": "Canonical ontology scope and vocabulary for the metadata graph foundation."},
    },
)
async def get_canonical_ontology() -> CanonicalOntologyView:
    return build_canonical_ontology()


@router.get(
    "/ontology/canonical/json-ld",
    responses={
        200: {"description": "Canonical ontology exported as JSON-LD for open standards interoperability."},
    },
)
async def get_canonical_ontology_jsonld() -> dict[str, Any]:
    return build_canonical_ontology_jsonld()


def _build_ontology_graph_http_exception(exc: OntologyGraphLookupError) -> HTTPException:
    return HTTPException(
        status_code=exc.status_code,
        detail={
            "error": exc.error_code,
            "message": str(exc),
        },
    )


@router.post(
    "/ontology/graph/project",
    response_model=OntologyGraphProjectionView,
    responses={
        200: {"description": "Project and persist the current ontology graph from metadata, governance, and execution seams."},
    },
)
async def project_ontology_graph(
    request: OntologyGraphProjectionRequestView,
    data_catalog_repository: DataCatalogRepository = Depends(get_data_catalog_repository),
    rules_repository: RulesRepository = Depends(get_rules_repository),
    validation_run_plan_repository: ValidationRunPlanRepository = Depends(get_validation_run_plan_repository),
    dq_result_event_repository: DqResultEventRepository = Depends(get_dq_result_event_repository),
    incident_repository: IncidentRepository = Depends(get_incident_repository),
    ontology_graph_repository: OntologyGraphRepository = Depends(get_ontology_graph_repository),
) -> OntologyGraphProjectionView:
    return await build_ontology_graph_projection(
        request=request,
        data_catalog_repository=data_catalog_repository,
        rules_repository=rules_repository,
        validation_run_plan_repository=validation_run_plan_repository,
        dq_result_event_repository=dq_result_event_repository,
        incident_repository=incident_repository,
        ontology_graph_repository=ontology_graph_repository,
    )


@router.post(
    "/ontology/graph/query",
    response_model=OntologyGraphQueryResultView,
    responses={
        200: {"description": "Query the latest persisted ontology graph snapshot with backend-owned filters."},
        404: {"description": "No ontology graph snapshot exists for the requested scope."},
    },
)
async def query_graph(
    request: OntologyGraphQueryRequestView,
    ontology_graph_repository=Depends(get_ontology_graph_repository),
) -> OntologyGraphQueryResultView:
    try:
        return await query_ontology_graph(request=request, ontology_graph_repository=ontology_graph_repository)
    except OntologyGraphLookupError as exc:
        raise _build_ontology_graph_http_exception(exc) from exc


@router.post(
    "/ontology/graph/traverse",
    response_model=OntologyGraphTraversalResultView,
    responses={
        200: {"description": "Traverse the latest persisted ontology graph snapshot from a seed node."},
        404: {"description": "No ontology graph snapshot or seed node exists for the requested scope."},
    },
)
async def traverse_graph(
    request: OntologyGraphTraversalRequestView,
    ontology_graph_repository=Depends(get_ontology_graph_repository),
) -> OntologyGraphTraversalResultView:
    try:
        return await traverse_ontology_graph(request=request, ontology_graph_repository=ontology_graph_repository)
    except OntologyGraphLookupError as exc:
        raise _build_ontology_graph_http_exception(exc) from exc
