from __future__ import annotations

import csv
import io
import json
from typing import Any


def build_exception_summary_json_export(serialized_summary: dict[str, Any]) -> str:
    return json.dumps(serialized_summary, default=str, indent=2)


def build_exception_summary_csv_export(*, scope_kind: str, scope_id: str, serialized_summary: dict[str, Any]) -> str:
    output = io.StringIO()
    writer = csv.DictWriter(
        output,
        fieldnames=[
            "scope_kind",
            "scope_id",
            "reason_code",
            "reason_text",
            "total_failed_records",
            "runs_with_failures",
            "reason_total",
            "first_total",
            "latest_total",
            "net_change",
            "direction",
            "peak_total",
            "bucket_count",
        ],
        extrasaction="ignore",
    )
    writer.writeheader()

    analytics = dict(serialized_summary.get("analytics") or {})
    fluctuations = analytics.get("reason_fluctuations") if isinstance(analytics.get("reason_fluctuations"), list) else []
    reason_totals = analytics.get("top_reasons") if isinstance(analytics.get("top_reasons"), list) else []
    reason_total_by_code = {
        str(item.get("reason_code") or ""): int(item.get("total") or 0)
        for item in reason_totals
        if str(item.get("reason_code") or "").strip()
    }

    rows: list[dict[str, Any]] = []
    if fluctuations:
        for item in fluctuations:
            reason_code = str(item.get("reason_code") or "").strip()
            rows.append(
                {
                    "scope_kind": scope_kind,
                    "scope_id": scope_id,
                    "reason_code": reason_code,
                    "reason_text": str(item.get("reason_text") or ""),
                    "total_failed_records": int(analytics.get("total_failed_records") or 0),
                    "runs_with_failures": int(analytics.get("runs_with_failures") or 0),
                    "reason_total": reason_total_by_code.get(reason_code, int(item.get("latest_total") or 0)),
                    "first_total": int(item.get("first_total") or 0),
                    "latest_total": int(item.get("latest_total") or 0),
                    "net_change": int(item.get("net_change") or 0),
                    "direction": str(item.get("direction") or "flat"),
                    "peak_total": int(item.get("peak_total") or 0),
                    "bucket_count": int(item.get("bucket_count") or 0),
                }
            )
    else:
        for item in reason_totals:
            rows.append(
                {
                    "scope_kind": scope_kind,
                    "scope_id": scope_id,
                    "reason_code": str(item.get("reason_code") or ""),
                    "reason_text": str(item.get("reason_text") or ""),
                    "total_failed_records": int(analytics.get("total_failed_records") or 0),
                    "runs_with_failures": int(analytics.get("runs_with_failures") or 0),
                    "reason_total": int(item.get("total") or 0),
                    "first_total": 0,
                    "latest_total": 0,
                    "net_change": 0,
                    "direction": "flat",
                    "peak_total": 0,
                    "bucket_count": 0,
                }
            )

    for row in rows:
        writer.writerow(row)
    output.seek(0)
    return output.getvalue()


def build_exception_summary_markdown_report(*, scope_kind: str, scope_id: str, serialized_summary: dict[str, Any]) -> str:
    analytics = dict(serialized_summary.get("analytics") or {})
    top_reasons = analytics.get("top_reasons") if isinstance(analytics.get("top_reasons"), list) else []
    reason_fluctuations = analytics.get("reason_fluctuations") if isinstance(analytics.get("reason_fluctuations"), list) else []
    execution_run_ids = serialized_summary.get("execution_run_ids") if isinstance(serialized_summary.get("execution_run_ids"), list) else []
    data_object_version_ids = serialized_summary.get("data_object_version_ids") if isinstance(serialized_summary.get("data_object_version_ids"), list) else []

    lines = [
        f"# Exception Summary Report: {scope_kind} {scope_id}",
        "",
        "## Overview",
        f"- Total failed records: {int(analytics.get('total_failed_records') or 0)}",
        f"- Runs with failures: {int(analytics.get('runs_with_failures') or 0)}",
        f"- Execution runs: {', '.join(str(item) for item in execution_run_ids) if execution_run_ids else 'none'}",
        f"- Data object versions: {', '.join(str(item) for item in data_object_version_ids) if data_object_version_ids else 'none'}",
        "",
        "## Top Reasons",
    ]

    if top_reasons:
        for item in top_reasons:
            lines.append(
                f"- {str(item.get('reason_code') or '')}: {str(item.get('reason_text') or '')} ({int(item.get('total') or 0)})"
            )
    else:
        lines.append("- No failure reasons recorded in the selected window.")

    lines.extend(["", "## Reason Fluctuation"]) 
    if reason_fluctuations:
        for item in reason_fluctuations:
            lines.append(
                "- "
                f"{str(item.get('reason_code') or '')}: "
                f"net change {int(item.get('net_change') or 0)}, "
                f"direction {str(item.get('direction') or 'flat')}, "
                f"latest total {int(item.get('latest_total') or 0)}, "
                f"peak total {int(item.get('peak_total') or 0)}"
            )
    else:
        lines.append("- No fluctuation buckets recorded in the selected window.")

    return "\n".join(lines) + "\n"