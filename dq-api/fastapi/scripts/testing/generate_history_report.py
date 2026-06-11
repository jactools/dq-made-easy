#!/usr/bin/env python3
"""Generate a markdown report from recorded test history."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HISTORY_FILE = ROOT / "test-results" / "history" / "test-runs.jsonl"
REPORT_FILE = ROOT / "test-results" / "history" / "report.md"


def _load_history() -> list[dict]:
    if not HISTORY_FILE.exists():
        return []

    records: list[dict] = []
    for line in HISTORY_FILE.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return records


def _avg(values: list[float]) -> float | None:
    if not values:
        return None
    return round(sum(values) / len(values), 2)


def _fmt(value: object, default: str = "n/a") -> str:
    if value is None:
        return default
    if isinstance(value, float):
        return f"{value:.2f}"
    return str(value)


def _build_markdown(records: list[dict], limit: int) -> str:
    selected = records[-limit:] if limit > 0 else records
    if not selected:
        return "# Test History Report\n\nNo historical test data found.\n"

    passed_runs = sum(1 for row in selected if row.get("exit_code") == 0)
    coverage_values = [float(row["coverage_percent"]) for row in selected if isinstance(row.get("coverage_percent"), (int, float))]
    duration_values = [float(row["duration_seconds"]) for row in selected if isinstance(row.get("duration_seconds"), (int, float))]

    latest = selected[-1]

    lines = [
        "# Test History Report",
        "",
        f"Data points: {len(selected)}",
        f"Pass rate: {passed_runs}/{len(selected)} ({(passed_runs / len(selected)) * 100:.1f}%)",
        f"Avg coverage: {_fmt(_avg(coverage_values))}%",
        f"Avg duration: {_fmt(_avg(duration_values))}s",
        "",
        "## Latest Run",
        "",
        f"- Timestamp (UTC): {_fmt(latest.get('timestamp_utc'))}",
        f"- Exit code: {_fmt(latest.get('exit_code'))}",
        f"- Tests: {_fmt(latest.get('tests'))}",
        f"- Passed: {_fmt(latest.get('passed'))}",
        f"- Failures: {_fmt(latest.get('failures'))}",
        f"- Errors: {_fmt(latest.get('errors'))}",
        f"- Skipped: {_fmt(latest.get('skipped'))}",
        f"- Duration: {_fmt(latest.get('duration_seconds'))}s",
        f"- Coverage: {_fmt(latest.get('coverage_percent'))}%",
        f"- Branch: {_fmt(latest.get('git_branch'))}",
        f"- Commit: {_fmt(latest.get('git_commit'))}",
        "",
        "## Recent Runs",
        "",
        "| timestamp_utc | exit | tests | passed | failures | errors | skipped | duration_s | coverage_pct | branch | commit |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---|---|",
    ]

    for row in reversed(selected):
        lines.append(
            "| "
            + " | ".join(
                [
                    _fmt(row.get("timestamp_utc")),
                    _fmt(row.get("exit_code")),
                    _fmt(row.get("tests")),
                    _fmt(row.get("passed")),
                    _fmt(row.get("failures")),
                    _fmt(row.get("errors")),
                    _fmt(row.get("skipped")),
                    _fmt(row.get("duration_seconds")),
                    _fmt(row.get("coverage_percent")),
                    _fmt(row.get("git_branch")),
                    _fmt(row.get("git_commit")),
                ]
            )
            + " |"
        )

    lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate test history markdown report.")
    parser.add_argument("--limit", type=int, default=30, help="Number of latest runs to include.")
    args = parser.parse_args()

    records = _load_history()
    markdown = _build_markdown(records, args.limit)

    REPORT_FILE.parent.mkdir(parents=True, exist_ok=True)
    REPORT_FILE.write_text(markdown, encoding="utf-8")

    print(f"Report written: {REPORT_FILE}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
