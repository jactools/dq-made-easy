from app.schemas.pagination import PaginationMeta, PaginatedResponse
from app.schemas.problem_details import ProblemDetails


def test_pagination_and_problem_details_models():
    meta = PaginationMeta(page=2, size=100, total=10)
    resp = PaginatedResponse(data=[{"id": 1}], pagination=meta)
    dumped = resp.model_dump(by_alias=True)
    assert dumped["pagination"]["page"] == 2

    pd = ProblemDetails(type="t", title="tt", status=400, correlation_id="cid")
    pd_dump = pd.model_dump(by_alias=True)
    assert pd_dump["correlation_id"] == "cid"
