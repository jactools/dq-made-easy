from __future__ import annotations


def test_metrics_endpoint_requires_auth(client) -> None:
    response = client.get("/metrics")

    assert response.status_code == 401


def test_metrics_endpoint_returns_prometheus_text(client, auth_headers) -> None:
    response = client.get("/metrics", headers=auth_headers("dq:rules:read"))

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/plain")
    body = response.text
    assert "# TYPE dq_api_requests_total counter" in body
    assert "dq_api_requests_total " in body
    assert "dq_api_requests_errors_total " in body
    assert "# TYPE dq_api_auth_login_total counter" in body
    assert 'dq_api_auth_login_total{role="admin"} ' in body