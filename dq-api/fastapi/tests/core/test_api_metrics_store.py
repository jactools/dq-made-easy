import pytest

import app.core.api_metrics as api_metrics
from app.core.api_metrics import ApiMetricsStore, render_prometheus_metrics


pytestmark = pytest.mark.usefixtures("monkeypatch")


def test_get_summary_returns_empty_shape_when_no_records() -> None:
    store = ApiMetricsStore()

    summary = store.get_summary()

    assert summary["total"] == 0
    assert summary["errors"] == 0
    assert summary["recentErrors"] == []
    assert len(summary["requestSeries"]) == 60


def test_get_summary_filters_by_endpoint_method_and_recent_error_status() -> None:
    store = ApiMetricsStore()
    store.record("GET", "/rulebuilder/v1/rules", 200, 12.5)
    store.record("GET", "/rulebuilder/v1/rules", 404, 23.0, error_detail="missing")
    store.record("POST", "/rulebuilder/v1/rules", 500, 41.0, error_detail="boom")
    store.record("GET", "/rulebuilder/v1/workspaces", 503, 22.0, error_detail="down")

    summary = store.get_summary(
        log_level="warn",
        endpoint_filter="rules",
        method_filter="GET",
        recent_error_status_filter="4xx",
        recent_error_path_filter="/rulebuilder/v1/rules",
    )

    assert summary["total"] == 2
    assert summary["errors"] == 1
    assert len(summary["endpoints"]) == 1
    assert summary["endpoints"][0]["endpoint"] == "GET /rulebuilder/v1/rules"
    assert len(summary["recentErrors"]) == 1
    assert summary["recentErrors"][0]["statusCode"] == 404


def test_get_summary_supports_min_requests_and_health_exclusion() -> None:
    store = ApiMetricsStore()
    store.record("GET", "/system/v1/health", 200, 1.0)
    store.record("GET", "/v1/items", 200, 10.0)
    store.record("GET", "/v1/items", 201, 11.0)
    store.record("GET", "/v1/items", 500, 15.0)
    store.record("POST", "/v1/items", 500, 25.0)

    summary = store.get_summary(
        exclude_health_endpoints=True,
        min_requests=2,
        recent_error_status_filter="invalid-status-filter",
    )

    assert summary["total"] == 3
    assert summary["errors"] == 1
    endpoint_names = [item["endpoint"] for item in summary["endpoints"]]
    assert "GET /system/v1/health" not in endpoint_names
    assert "GET /v1/items" in endpoint_names
    assert "POST /v1/items" not in endpoint_names


def test_get_summary_prunes_records_older_than_retention(monkeypatch) -> None:
    store = ApiMetricsStore()
    base_time = 1_700_000_000
    monkeypatch.setattr("app.core.api_metrics.time.time", lambda: base_time)

    store.record("GET", "/v1/items", 200, 10.0)
    monkeypatch.setattr("app.core.api_metrics.time.time", lambda: base_time + 91 * 86400)

    summary = store.get_summary(retention_days=90)

    assert summary["total"] == 0
    assert summary["errors"] == 0


def test_render_prometheus_metrics_formats_all_metrics() -> None:
    summary = {
        "total": 10,
        "errors": 2,
        "errorRate": 0.2,
        "avgDurationMs": 25.5,
        "p95DurationMs": 40.0,
    }

    text = render_prometheus_metrics(summary)

    assert "dq_api_requests_total 10" in text
    assert "dq_api_requests_errors_total 2" in text
    assert "dq_api_requests_error_rate 0.2" in text
    assert "dq_api_requests_avg_duration_ms 25.5" in text
    assert "dq_api_requests_p95_duration_ms 40.0" in text
    assert text.endswith("\n")


def test_clear_removes_all_records() -> None:
    store = ApiMetricsStore()
    store.record("GET", "/rulebuilder/v1/rules", 200, 10.0)

    assert store.get_summary()["total"] == 1
    store.clear()
    assert store.get_summary()["total"] == 0


def test_get_summary_recent_errors_filter_5xx_only() -> None:
    store = ApiMetricsStore()
    store.record("GET", "/v1/items", 404, 10.0, error_detail="not found")
    store.record("GET", "/v1/items", 500, 15.0, error_detail="boom")

    summary = store.get_summary(recent_error_status_filter="5xx")

    assert len(summary["recentErrors"]) == 1
    assert summary["recentErrors"][0]["statusCode"] == 500


def test_get_summary_trend_series_skips_records_outside_window(monkeypatch) -> None:
    store = ApiMetricsStore()
    base_time = 1_700_000_000
    now_ms = base_time * 1000
    monkeypatch.setattr(api_metrics.time, "time", lambda: base_time)

    with store._lock:
        store._records.append(
            api_metrics.ApiRequestRecord(
                method="GET",
                path="/v1/items",
                status_code=200,
                duration_ms=5.0,
                timestamp_ms=now_ms - (2 * 60 * 60 * 1000),
            )
        )
        store._records.append(
            api_metrics.ApiRequestRecord(
                method="GET",
                path="/v1/items",
                status_code=200,
                duration_ms=6.0,
                timestamp_ms=now_ms + (2 * 60 * 60 * 1000),
            )
        )
        store._records.append(
            api_metrics.ApiRequestRecord(
                method="GET",
                path="/v1/items",
                status_code=200,
                duration_ms=7.0,
                timestamp_ms=now_ms - (10 * 60 * 1000),
            )
        )

    summary = store.get_summary()

    assert summary["total"] == 3
    assert sum(bucket["requestCount"] for bucket in summary["requestSeries"]) == 1