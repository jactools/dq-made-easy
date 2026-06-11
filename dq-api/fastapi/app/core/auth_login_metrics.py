"""In-process successful-login metrics grouped by canonical role bucket."""
from __future__ import annotations

import threading
import time
from collections import deque
from dataclasses import dataclass
from math import ceil
from typing import Deque, Iterable

_ROLE_BUCKETS: tuple[str, ...] = ("admin", "auditor", "regulator", "other")
_ROLE_LABELS: dict[str, str] = {
    "admin": "Admin",
    "auditor": "Auditor",
    "regulator": "Regulator",
    "other": "Other",
}
_MAX_RECORDS = 5_000
_DEFAULT_RETENTION_DAYS = 90
_DEFAULT_TREND_WINDOW_HOURS = 24
_DEFAULT_BUCKET_MINUTES = 60


@dataclass
class AuthLoginRecord:
    role: str
    timestamp_ms: float


def resolve_login_role_bucket(role_sources: Iterable[str]) -> str:
    normalized_sources = " ".join(
        str(role_source).strip().lower()
        for role_source in role_sources
        if str(role_source).strip()
    )
    if not normalized_sources:
        return "other"
    if "admin" in normalized_sources:
        return "admin"
    if "auditor" in normalized_sources or "audit" in normalized_sources:
        return "auditor"
    if "regulator" in normalized_sources or "regulat" in normalized_sources:
        return "regulator"
    return "other"


class AuthLoginMetricsStore:
    """Thread-safe in-process store for successful login role metrics."""

    def __init__(self, max_records: int = _MAX_RECORDS) -> None:
        self._records: Deque[AuthLoginRecord] = deque(maxlen=max_records)
        self._lock = threading.Lock()

    def clear(self) -> None:
        with self._lock:
            self._records.clear()

    def record_login(self, role: str) -> None:
        bucket = resolve_login_role_bucket([role])
        record = AuthLoginRecord(role=bucket, timestamp_ms=time.time() * 1000)
        with self._lock:
            self._records.append(record)

    def get_summary(
        self,
        retention_days: int = _DEFAULT_RETENTION_DAYS,
        trend_window_hours: int = _DEFAULT_TREND_WINDOW_HOURS,
        bucket_minutes: int = _DEFAULT_BUCKET_MINUTES,
    ) -> dict:
        retention_days = max(1, int(retention_days or _DEFAULT_RETENTION_DAYS))
        trend_window_hours = max(1, int(trend_window_hours or _DEFAULT_TREND_WINDOW_HOURS))
        bucket_minutes = max(1, int(bucket_minutes or _DEFAULT_BUCKET_MINUTES))

        now_ms = time.time() * 1000
        retention_cutoff_ms = now_ms - (retention_days * 86_400 * 1000)
        with self._lock:
            records = [record for record in self._records if record.timestamp_ms >= retention_cutoff_ms]

        total = len(records)
        counts_by_role = {role: 0 for role in _ROLE_BUCKETS}
        for record in records:
            counts_by_role[record.role] += 1

        trend_window_minutes = trend_window_hours * 60
        bucket_count = max(1, ceil(trend_window_minutes / bucket_minutes))
        bucket_ms = bucket_minutes * 60_000
        window_start_ms = now_ms - (bucket_count * bucket_ms)

        bucket_template = [
            {
                "bucket_start_ms": int(window_start_ms + (index * bucket_ms)),
                "role_counts": {role: 0 for role in _ROLE_BUCKETS},
            }
            for index in range(bucket_count)
        ]

        for record in records:
            if record.timestamp_ms < window_start_ms:
                continue
            bucket_index = int((record.timestamp_ms - window_start_ms) // bucket_ms)
            if bucket_index >= bucket_count:
                bucket_index = bucket_count - 1
            if bucket_index < 0 or bucket_index >= bucket_count:
                continue
            bucket_template[bucket_index]["role_counts"][record.role] += 1

        role_counts = [
            {
                "role": role,
                "label": _ROLE_LABELS[role],
                "count": counts_by_role[role],
            }
            for role in _ROLE_BUCKETS
        ]
        trend_series = [
            {
                "bucket_start_ms": bucket["bucket_start_ms"],
                "role_counts": bucket["role_counts"],
            }
            for bucket in bucket_template
        ]

        return {
            "total": total,
            "retention_days": retention_days,
            "trend_window_hours": trend_window_hours,
            "bucket_minutes": bucket_minutes,
            "role_counts": role_counts,
            "trend_series": trend_series,
        }


def record_login_event(role_sources: Iterable[str]) -> str:
    bucket = resolve_login_role_bucket(role_sources)
    auth_login_metrics_store.record_login(bucket)
    return bucket


def render_prometheus_metrics(summary: dict) -> str:
    role_counts = {str(item.get("role") or "other"): int(item.get("count") or 0) for item in summary.get("role_counts", []) if isinstance(item, dict)}
    lines = [
        "# HELP dq_api_auth_login_total Successful login events grouped by canonical role bucket.",
        "# TYPE dq_api_auth_login_total counter",
    ]
    for role in _ROLE_BUCKETS:
        lines.append(f'dq_api_auth_login_total{{role="{role}"}} {role_counts.get(role, 0)}')
    return "\n".join(lines) + "\n"


auth_login_metrics_store = AuthLoginMetricsStore()