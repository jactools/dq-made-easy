"""In-process API request metrics store.

Records are held in a fixed-size circular buffer.  Log-level and data-retention
filtering are applied at query time so we never need a database hit per request.
"""
from __future__ import annotations

import threading
import time
from collections import deque
from dataclasses import dataclass
from typing import Deque

# Paths excluded from metrics tracking
_SKIP_PATHS: frozenset[str] = frozenset(
    {"/health", "/metrics", "/docs", "/redoc", "/openapi.json", "/favicon.ico"}
)

# How many raw records to keep in memory (newest wins)
_MAX_RECORDS = 5_000

# Which HTTP status-code buckets are "interesting" at each log level.
# At query time we filter recent-errors list and summary accordingly.
_VISIBLE_ERROR_BUCKETS: dict[str, set[str]] = {
    "error": {"5xx"},
    "warn": {"4xx", "5xx"},
    "info": {"4xx", "5xx"},
    "debug": {"1xx", "2xx", "3xx", "4xx", "5xx"},
}


@dataclass
class ApiRequestRecord:
    method: str
    path: str
    status_code: int
    duration_ms: float
    timestamp_ms: float
    error_detail: str | None = None


class ApiMetricsStore:
    """Thread-safe in-process store for API request metrics."""

    def __init__(self, max_records: int = _MAX_RECORDS) -> None:
        self._records: Deque[ApiRequestRecord] = deque(maxlen=max_records)
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    # Write path
    # ------------------------------------------------------------------

    def record(
        self,
        method: str,
        path: str,
        status_code: int,
        duration_ms: float,
        error_detail: str | None = None,
    ) -> None:
        """Append one request record.  Call-site decides whether to call this."""
        rec = ApiRequestRecord(
            method=method,
            path=path,
            status_code=status_code,
            duration_ms=duration_ms,
            timestamp_ms=time.time() * 1000,
            error_detail=error_detail,
        )
        with self._lock:
            self._records.append(rec)

    # ------------------------------------------------------------------
    # Read path — filtering applied here, not at write time
    # ------------------------------------------------------------------

    def get_summary(
        self,
        retention_days: int = 90,
        log_level: str = "info",
        endpoint_filter: str | None = None,
        method_filter: str = "all",
        min_requests: int = 0,
        recent_error_status_filter: str = "all",
        recent_error_path_filter: str | None = None,
        exclude_health_endpoints: bool = False,
    ) -> dict:
        """Return aggregated summary.

        ``retention_days`` prunes records older than N days.
        ``log_level`` controls which errors appear in the *recentErrors* list:
          - error  → only 5xx
          - warn   → 4xx + 5xx
          - info   → 4xx + 5xx  (same visibility as warn for errors)
          - debug  → every response including 2xx
        Optional UI filters are also applied so the server can return a summary
        that already matches what is shown in the System Metrics page.
        """
        cutoff_ms = (time.time() - retention_days * 86400) * 1000
        visible_buckets = _VISIBLE_ERROR_BUCKETS.get(log_level.lower(), _VISIBLE_ERROR_BUCKETS["info"])
        endpoint_filter_normalized = (endpoint_filter or "").strip().lower()
        method_filter_normalized = (method_filter or "all").strip().upper()
        min_requests_normalized = max(0, int(min_requests or 0))
        recent_error_status_normalized = (recent_error_status_filter or "all").strip().lower()
        if recent_error_status_normalized not in {"all", "4xx", "5xx"}:
            recent_error_status_normalized = "all"
        recent_error_path_normalized = (recent_error_path_filter or "").strip().lower()

        def _matches_recent_error_status(status_code: int) -> bool:
            if recent_error_status_normalized == "4xx":
                return 400 <= status_code < 500
            if recent_error_status_normalized == "5xx":
                return status_code >= 500
            return status_code >= 400

        def _is_health_path(path: str) -> bool:
            path_l = path.lower()
            return (
                "/system/v" in path_l and "/health" in path_l
            ) or (
                "/system/v" in path_l and "/readiness" in path_l
            ) or (
                "/system/v" in path_l and path_l.endswith("/ready")
            )

        with self._lock:
            records: list[ApiRequestRecord] = [r for r in self._records if r.timestamp_ms >= cutoff_ms]

        if exclude_health_endpoints:
            records = [r for r in records if not _is_health_path(r.path)]

        # Aggregate by METHOD + path so endpoint-level filters can be applied first.
        endpoints: dict[str, dict] = {}
        for r in records:
            key = f"{r.method} {r.path}"
            ep = endpoints.setdefault(
                key,
                {
                    "endpoint": key,
                    "method": r.method,
                    "count": 0,
                    "errorCount": 0,
                    "totalDurationMs": 0.0,
                    "minDurationMs": float("inf"),
                    "maxDurationMs": 0.0,
                    "lastSeenMs": 0.0,
                },
            )
            ep["count"] += 1
            ep["totalDurationMs"] += r.duration_ms
            ep["minDurationMs"] = min(ep["minDurationMs"], r.duration_ms)
            ep["maxDurationMs"] = max(ep["maxDurationMs"], r.duration_ms)
            ep["lastSeenMs"] = max(ep["lastSeenMs"], r.timestamp_ms)
            if r.status_code >= 400:
                ep["errorCount"] += 1

        endpoint_list = []
        selected_endpoint_keys: set[str] = set()
        for ep in sorted(endpoints.values(), key=lambda e: e["count"], reverse=True):
            count = ep["count"]
            endpoint_name = str(ep["endpoint"])
            if endpoint_filter_normalized and endpoint_filter_normalized not in endpoint_name.lower():
                continue
            if method_filter_normalized not in {"", "ALL"} and str(ep["method"]).upper() != method_filter_normalized:
                continue
            if count < min_requests_normalized:
                continue

            selected_endpoint_keys.add(endpoint_name)
            endpoint_list.append(
                {
                    "endpoint": endpoint_name,
                    "count": count,
                    "errorCount": ep["errorCount"],
                    "errorRate": ep["errorCount"] / count if count else 0.0,
                    "avgDurationMs": ep["totalDurationMs"] / count if count else 0.0,
                    "minDurationMs": (
                        ep["minDurationMs"] if ep["minDurationMs"] != float("inf") else 0.0
                    ),
                    "maxDurationMs": ep["maxDurationMs"],
                    "lastSeenMs": ep["lastSeenMs"],
                }
            )

        filtered_records = [
            r for r in records
            if f"{r.method} {r.path}" in selected_endpoint_keys
        ]

        # Build a minute-level trend for the last hour.
        now_ms = time.time() * 1000
        window_minutes = 60
        bucket_ms = 60_000
        window_start_ms = now_ms - (window_minutes * bucket_ms)
        bucket_count = window_minutes
        bucket_template = [
            {
                "bucketStartMs": window_start_ms + (i * bucket_ms),
                "requestCount": 0,
                "errorCount": 0,
                "totalDurationMs": 0.0,
            }
            for i in range(bucket_count)
        ]

        for rec in filtered_records:
            if rec.timestamp_ms < window_start_ms:
                continue
            bucket_index = int((rec.timestamp_ms - window_start_ms) // bucket_ms)
            if bucket_index < 0 or bucket_index >= bucket_count:
                continue
            bucket = bucket_template[bucket_index]
            bucket["requestCount"] += 1
            bucket["totalDurationMs"] += rec.duration_ms
            if rec.status_code >= 400:
                bucket["errorCount"] += 1

        trend_series = [
            {
                "bucketStartMs": int(bucket["bucketStartMs"]),
                "requestCount": int(bucket["requestCount"]),
                "errorCount": int(bucket["errorCount"]),
                "avgDurationMs": (
                    float(bucket["totalDurationMs"]) / int(bucket["requestCount"])
                    if int(bucket["requestCount"]) > 0
                    else 0.0
                ),
            }
            for bucket in bucket_template
        ]

        if not filtered_records:
            return {
                "total": 0,
                "errors": 0,
                "errorRate": 0.0,
                "avgDurationMs": 0.0,
                "p95DurationMs": 0.0,
                "retentionDays": retention_days,
                "logLevel": log_level,
                "trendWindowMinutes": window_minutes,
                "requestSeries": trend_series,
                "endpoints": endpoint_list,
                "recentErrors": [],
            }

        total = len(filtered_records)
        errors = sum(1 for r in filtered_records if r.status_code >= 400)
        durations = sorted(r.duration_ms for r in filtered_records)
        avg_ms = sum(durations) / total
        p95_ms = durations[max(0, int(total * 0.95) - 1)]

        # Recent errors filtered by log level
        def _bucket(status: int) -> str:
            return f"{status // 100}xx"

        recent_errors = sorted(
            [
                r
                for r in filtered_records
                if _bucket(r.status_code) in visible_buckets
                and _matches_recent_error_status(r.status_code)
                and (
                    not recent_error_path_normalized
                    or recent_error_path_normalized in f"{r.method} {r.path}".lower()
                )
            ],
            key=lambda r: r.timestamp_ms,
            reverse=True,
        )[:50]

        return {
            "total": total,
            "errors": errors,
            "errorRate": errors / total if total else 0.0,
            "avgDurationMs": avg_ms,
            "p95DurationMs": p95_ms,
            "retentionDays": retention_days,
            "logLevel": log_level,
            "trendWindowMinutes": window_minutes,
            "requestSeries": trend_series,
            "endpoints": endpoint_list,
            "recentErrors": [
                {
                    "method": r.method,
                    "path": r.path,
                    "statusCode": r.status_code,
                    "durationMs": r.duration_ms,
                    "timestampMs": r.timestamp_ms,
                    "errorDetail": r.error_detail,
                }
                for r in recent_errors
            ],
        }

    def clear(self) -> None:
        with self._lock:
            self._records.clear()


def render_prometheus_metrics(summary: dict) -> str:
    """Render a small Prometheus exposition for the API request summary."""

    total = int(summary.get("total") or 0)
    errors = int(summary.get("errors") or 0)
    error_rate = float(summary.get("errorRate") or 0.0)
    avg_duration_ms = float(summary.get("avgDurationMs") or 0.0)
    p95_duration_ms = float(summary.get("p95DurationMs") or 0.0)

    lines = [
        "# HELP dq_api_requests_total Total API requests recorded by the in-process metrics store.",
        "# TYPE dq_api_requests_total counter",
        f"dq_api_requests_total {total}",
        "# HELP dq_api_requests_errors_total Total API requests with status >= 400.",
        "# TYPE dq_api_requests_errors_total counter",
        f"dq_api_requests_errors_total {errors}",
        "# HELP dq_api_requests_error_rate Ratio of failed requests to total requests.",
        "# TYPE dq_api_requests_error_rate gauge",
        f"dq_api_requests_error_rate {error_rate}",
        "# HELP dq_api_requests_avg_duration_ms Average request duration in milliseconds.",
        "# TYPE dq_api_requests_avg_duration_ms gauge",
        f"dq_api_requests_avg_duration_ms {avg_duration_ms}",
        "# HELP dq_api_requests_p95_duration_ms 95th percentile request duration in milliseconds.",
        "# TYPE dq_api_requests_p95_duration_ms gauge",
        f"dq_api_requests_p95_duration_ms {p95_duration_ms}",
    ]
    return "\n".join(lines) + "\n"


# Module-level singleton shared across the process
api_metrics_store = ApiMetricsStore()
