from __future__ import annotations

from app.core import auth_login_metrics
from app.core.auth_login_metrics import AuthLoginMetricsStore
from app.core.auth_login_metrics import render_prometheus_metrics
from app.core.auth_login_metrics import resolve_login_role_bucket


def test_resolve_login_role_bucket_prioritizes_canonical_roles() -> None:
    assert resolve_login_role_bucket(["workspace-admin", "auditor"]) == "admin"
    assert resolve_login_role_bucket(["team auditor", "viewer"]) == "auditor"
    assert resolve_login_role_bucket(["regulator", "viewer"]) == "regulator"
    assert resolve_login_role_bucket([""]) == "other"


def test_get_summary_returns_role_counts_and_trend_series(monkeypatch) -> None:
    store = AuthLoginMetricsStore()
    base_time = 1_700_000_000
    monkeypatch.setattr(auth_login_metrics.time, "time", lambda: base_time)

    store.record_login("admin")
    store.record_login("auditor")
    store.record_login("regulator")

    summary = store.get_summary()

    assert summary["total"] == 3
    assert summary["retention_days"] == 90
    assert summary["trend_window_hours"] == 24
    assert len(summary["role_counts"]) == 4
    role_counts = {entry["role"]: entry["count"] for entry in summary["role_counts"]}
    assert role_counts["admin"] == 1
    assert role_counts["auditor"] == 1
    assert role_counts["regulator"] == 1
    assert role_counts["other"] == 0
    assert len(summary["trend_series"]) == 24
    assert sum(bucket["role_counts"]["admin"] for bucket in summary["trend_series"]) == 1
    assert sum(bucket["role_counts"]["auditor"] for bucket in summary["trend_series"]) == 1
    assert sum(bucket["role_counts"]["regulator"] for bucket in summary["trend_series"]) == 1


def test_render_prometheus_metrics_formats_role_lines() -> None:
    text = render_prometheus_metrics(
        {
            "role_counts": [
                {"role": "admin", "count": 4},
                {"role": "auditor", "count": 2},
                {"role": "regulator", "count": 1},
                {"role": "other", "count": 0},
            ]
        }
    )

    assert "# TYPE dq_api_auth_login_total counter" in text
    assert 'dq_api_auth_login_total{role="admin"} 4' in text
    assert 'dq_api_auth_login_total{role="auditor"} 2' in text
    assert 'dq_api_auth_login_total{role="regulator"} 1' in text
    assert text.endswith("\n")


def test_resolve_login_role_bucket_returns_other_for_unmatched_roles() -> None:
    assert resolve_login_role_bucket(["viewer", "operator"]) == "other"


def test_store_clear_removes_recorded_logins(monkeypatch) -> None:
    store = AuthLoginMetricsStore()
    monkeypatch.setattr(auth_login_metrics.time, "time", lambda: 1_700_000_000)

    store.record_login("admin")
    assert store.get_summary()["total"] == 1

    store.clear()
    assert store.get_summary()["total"] == 0


def test_get_summary_normalizes_zero_inputs_and_skips_records_older_than_window(monkeypatch) -> None:
    store = AuthLoginMetricsStore()
    base_time = 1_700_000_000
    now_ms = base_time * 1000
    monkeypatch.setattr(auth_login_metrics.time, "time", lambda: base_time)

    with store._lock:  # intentional direct setup for edge-case timestamps
        store._records.append(
            auth_login_metrics.AuthLoginRecord(
                role="admin",
                timestamp_ms=now_ms - (2 * 60 * 60 * 1000),
            )
        )
        store._records.append(
            auth_login_metrics.AuthLoginRecord(
                role="auditor",
                timestamp_ms=now_ms,
            )
        )

    summary = store.get_summary(retention_days=-1, trend_window_hours=-1, bucket_minutes=-1)

    assert summary["retention_days"] == 1
    assert summary["trend_window_hours"] == 1
    assert summary["bucket_minutes"] == 1
    assert summary["total"] == 2
    assert sum(bucket["role_counts"]["admin"] for bucket in summary["trend_series"]) == 0
    assert sum(bucket["role_counts"]["auditor"] for bucket in summary["trend_series"]) == 1


def test_record_login_event_records_bucket_and_returns_it(monkeypatch) -> None:
    store = AuthLoginMetricsStore()
    monkeypatch.setattr(auth_login_metrics, "auth_login_metrics_store", store)
    monkeypatch.setattr(auth_login_metrics.time, "time", lambda: 1_700_000_000)

    bucket = auth_login_metrics.record_login_event(["internal-auditor"])
    summary = store.get_summary()
    role_counts = {entry["role"]: entry["count"] for entry in summary["role_counts"]}

    assert bucket == "auditor"
    assert role_counts["auditor"] == 1
