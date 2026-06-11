from __future__ import annotations

from collections.abc import Iterable

from app.domain.entities.admin import ExceptionFactAccessRequestEntity


def summarize_jit_access_requests(requests: Iterable[ExceptionFactAccessRequestEntity]) -> dict[str, int]:
    counts = {
        "total": 0,
        "pending": 0,
        "approved": 0,
        "declined": 0,
        "timed_out": 0,
    }

    for request in requests:
        status = str(getattr(request, "status", "") or "").strip().lower()
        if not status:
            continue
        counts["total"] += 1
        if status == "pending":
            counts["pending"] += 1
        elif status == "approved":
            counts["approved"] += 1
        elif status in {"rejected", "revoked"}:
            counts["declined"] += 1
        elif status == "timed_out":
            counts["timed_out"] += 1

    return counts


def render_prometheus_metrics(summary: dict[str, int]) -> str:
    total = int(summary.get("total") or 0)
    pending = int(summary.get("pending") or 0)
    approved = int(summary.get("approved") or 0)
    declined = int(summary.get("declined") or 0)
    timed_out = int(summary.get("timed_out") or 0)

    lines = [
        "# HELP dq_exception_fact_jit_access_requests_total Current number of JIT access requests.",
        "# TYPE dq_exception_fact_jit_access_requests_total gauge",
        f"dq_exception_fact_jit_access_requests_total {total}",
        "# HELP dq_exception_fact_jit_access_requests_current Current number of JIT access requests by status.",
        "# TYPE dq_exception_fact_jit_access_requests_current gauge",
        f'dq_exception_fact_jit_access_requests_current{{status="pending"}} {pending}',
        f'dq_exception_fact_jit_access_requests_current{{status="approved"}} {approved}',
        f'dq_exception_fact_jit_access_requests_current{{status="declined"}} {declined}',
        f'dq_exception_fact_jit_access_requests_current{{status="timed_out"}} {timed_out}',
    ]
    return "\n".join(lines) + "\n"
