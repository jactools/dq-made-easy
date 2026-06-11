import pytest

from app.schemas.pagination import PaginatedResponse, PaginationMeta, PaginationParams
from app.schemas.problem_details import ProblemDetails

pytestmark = pytest.mark.usefixtures("clone_payload")


def test_pagination_models_validate() -> None:
    params = PaginationParams(page=2, size=25)
    meta = PaginationMeta(page=params.page, size=params.size, total=250)
    payload = PaginatedResponse(data=[{"id": "rule-1"}], pagination=meta)

    assert payload.pagination.page == 2
    assert payload.pagination.size == 25
    assert payload.pagination.total == 250


def test_problem_details_model_validate() -> None:
    problem = ProblemDetails(
        type="about:blank",
        title="HTTP Error",
        status=404,
        detail="Not found",
        instance="/api/rulebuilder/v1/rules/missing-rule",
        correlation_id="cid-123",
    )

    assert problem.status == 404
    assert problem.correlation_id == "cid-123"
