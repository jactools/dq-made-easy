from app.core.jit_access_metrics import render_prometheus_metrics, summarize_jit_access_requests
from app.domain.entities.admin import ExceptionFactAccessRequestEntity


def _request(request_id: str, status: str) -> ExceptionFactAccessRequestEntity:
    return ExceptionFactAccessRequestEntity(
        id=request_id,
        requesterId="user-1",
        workspaceId="default",
        roleId="role-1",
        status=status,
    )


def test_summarize_jit_access_requests_normalizes_and_counts_statuses() -> None:
    summary = summarize_jit_access_requests(
        [
            _request("1", " pending "),
            _request("2", "APPROVED"),
            _request("3", "rejected"),
            _request("4", "revoked"),
            _request("5", "timed_out"),
            _request("6", "unknown_status"),
            _request("7", ""),
        ]
    )

    assert summary == {
        "total": 6,
        "pending": 1,
        "approved": 1,
        "declined": 2,
        "timed_out": 1,
    }


def test_summarize_jit_access_requests_ignores_missing_status_values() -> None:
    summary = summarize_jit_access_requests([_request("1", " "), _request("2", "")])

    assert summary == {
        "total": 0,
        "pending": 0,
        "approved": 0,
        "declined": 0,
        "timed_out": 0,
    }


def test_render_prometheus_metrics_renders_expected_lines_and_trailing_newline() -> None:
    metrics = render_prometheus_metrics(
        {
            "total": "7",
            "pending": 2,
            "approved": 3,
            "declined": 1,
            "timed_out": 1,
        }
    )

    assert "dq_exception_fact_jit_access_requests_total 7" in metrics
    assert 'dq_exception_fact_jit_access_requests_current{status="pending"} 2' in metrics
    assert 'dq_exception_fact_jit_access_requests_current{status="approved"} 3' in metrics
    assert 'dq_exception_fact_jit_access_requests_current{status="declined"} 1' in metrics
    assert 'dq_exception_fact_jit_access_requests_current{status="timed_out"} 1' in metrics
    assert metrics.endswith("\n")


def test_render_prometheus_metrics_defaults_missing_values_to_zero() -> None:
    metrics = render_prometheus_metrics({})

    assert "dq_exception_fact_jit_access_requests_total 0" in metrics
    assert 'dq_exception_fact_jit_access_requests_current{status="pending"} 0' in metrics
    assert 'dq_exception_fact_jit_access_requests_current{status="approved"} 0' in metrics
    assert 'dq_exception_fact_jit_access_requests_current{status="declined"} 0' in metrics
    assert 'dq_exception_fact_jit_access_requests_current{status="timed_out"} 0' in metrics