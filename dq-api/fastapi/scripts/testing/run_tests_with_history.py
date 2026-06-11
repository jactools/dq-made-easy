#!/usr/bin/env python3
"""Run pytest and append test/coverage metrics to a local history store.

This keeps historical run data without requiring git history traversal.
"""

from __future__ import annotations

import json
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[2]
TEST_RESULTS_DIR = ROOT / "test-results"
HISTORY_DIR = TEST_RESULTS_DIR / "history"
HISTORY_FILE = HISTORY_DIR / "test-runs.jsonl"
JUNIT_FILE = TEST_RESULTS_DIR / "junit.xml"
DQ_API_ROOT = ROOT.parent
COVERAGE_JSON = DQ_API_ROOT / "test-results/coverage.json"


def _run_pytest() -> int:
    cmd = [
        sys.executable,
        "-m",
        "pytest",
        "-q",
        "--junitxml",
        str(JUNIT_FILE),
    ]
    completed = subprocess.run(cmd, cwd=ROOT)
    return completed.returncode


def _read_coverage_percent() -> float | None:
    if not COVERAGE_JSON.exists():
        return None

    try:
        payload = json.loads(COVERAGE_JSON.read_text(encoding="utf-8"))
        totals = payload.get("totals", {})
        value = totals.get("percent_covered")
        return float(value) if value is not None else None
    except (ValueError, OSError, TypeError):
        return None


def _read_junit_metrics() -> dict[str, int | float] | None:
    if not JUNIT_FILE.exists():
        return None

    try:
        root = ET.parse(JUNIT_FILE).getroot()
    except ET.ParseError:
        return None

    suites = [root] if root.tag == "testsuite" else [node for node in root if node.tag == "testsuite"]
    if not suites:
        return None

    tests = failures = errors = skipped = 0
    duration = 0.0
    for suite in suites:
        tests += int(float(suite.attrib.get("tests", 0)))
        failures += int(float(suite.attrib.get("failures", 0)))
        errors += int(float(suite.attrib.get("errors", 0)))
        skipped += int(float(suite.attrib.get("skipped", 0)))
        duration += float(suite.attrib.get("time", 0.0))

    passed = max(0, tests - failures - errors - skipped)
    return {
        "tests": tests,
        "passed": passed,
        "failures": failures,
        "errors": errors,
        "skipped": skipped,
        "duration_seconds": round(duration, 3),
    }


def _safe_git_value(*args: str) -> str | None:
    try:
        completed = subprocess.run(
            ["git", *args],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
        value = completed.stdout.strip()
        return value or None
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None


def _append_history(exit_code: int) -> None:
    HISTORY_DIR.mkdir(parents=True, exist_ok=True)

    junit = _read_junit_metrics() or {}
    coverage_percent = _read_coverage_percent()
    record = {
        "timestamp_utc": datetime.now(UTC).isoformat(),
        "exit_code": exit_code,
        "tests": junit.get("tests"),
        "passed": junit.get("passed"),
        "failures": junit.get("failures"),
        "errors": junit.get("errors"),
        "skipped": junit.get("skipped"),
        "duration_seconds": junit.get("duration_seconds"),
        "coverage_percent": coverage_percent,
        "git_branch": _safe_git_value("rev-parse", "--abbrev-ref", "HEAD"),
        "git_commit": _safe_git_value("rev-parse", "--short", "HEAD"),
    }

    with HISTORY_FILE.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, separators=(",", ":")) + "\n")

    print(f"History updated: {HISTORY_FILE}")


def main() -> int:
    TEST_RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    exit_code = _run_pytest()
    _append_history(exit_code)
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
