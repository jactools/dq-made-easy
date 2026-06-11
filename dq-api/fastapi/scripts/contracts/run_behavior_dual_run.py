import argparse
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter
from typing import Any

import httpx


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _normalize_url(base_url: str, path: str) -> str:
    return f"{base_url.rstrip('/')}/{path.lstrip('/')}"


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _stable_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _coerce_json_payload(content_type: str | None, body_text: str) -> Any:
    if not content_type:
        return body_text
    if "application/json" not in content_type.lower():
        return body_text
    try:
        return json.loads(body_text)
    except json.JSONDecodeError:
        return body_text


def _drop_path(value: Any, parts: list[str]) -> None:
    if not parts:
        return

    head = parts[0]
    tail = parts[1:]

    if isinstance(value, dict):
        if head == "*":
            for nested in value.values():
                _drop_path(nested, tail)
            return
        if head in value:
            if tail:
                _drop_path(value[head], tail)
            else:
                value.pop(head, None)
        return

    if isinstance(value, list):
        if head == "*":
            for nested in value:
                _drop_path(nested, tail)
            return
        if head.isdigit():
            index = int(head)
            if 0 <= index < len(value):
                if tail:
                    _drop_path(value[index], tail)
                else:
                    value.pop(index)


def _drop_json_paths(payload: Any, paths: list[str]) -> Any:
    if not paths:
        return payload
    clone = json.loads(json.dumps(payload))
    for path in paths:
        parts = [part for part in path.split(".") if part]
        _drop_path(clone, parts)
    return clone


@dataclass
class RequestResult:
    url: str
    status: int
    duration_ms: float
    headers: dict[str, str]
    body: Any


@dataclass
class Difference:
    kind: str
    detail: str


@dataclass
class ScenarioResult:
    name: str
    method: str
    path: str
    passed: bool
    differences: list[Difference] = field(default_factory=list)
    legacy: RequestResult | None = None
    fastapi: RequestResult | None = None
    skipped: bool = False
    skip_reason: str = ""


def _request(
    client: httpx.Client,
    url: str,
    method: str,
    headers: dict[str, str],
    query: dict[str, Any],
    body: Any,
    timeout_seconds: float,
) -> RequestResult:
    start = perf_counter()
    response = client.request(
        method=method,
        url=url,
        headers=headers,
        params=query,
        json=body,
        timeout=timeout_seconds,
    )
    duration_ms = (perf_counter() - start) * 1000.0
    parsed_body = _coerce_json_payload(response.headers.get("content-type"), response.text)
    return RequestResult(
        url=url,
        status=response.status_code,
        duration_ms=round(duration_ms, 3),
        headers={key.lower(): value for key, value in response.headers.items()},
        body=parsed_body,
    )


def _compare(
    scenario: dict[str, Any],
    legacy: RequestResult,
    fastapi: RequestResult,
) -> list[Difference]:
    differences: list[Difference] = []

    if bool(scenario.get("compareStatus", True)) and legacy.status != fastapi.status:
        differences.append(Difference("status", f"legacy={legacy.status} fastapi={fastapi.status}"))

    compare_headers = scenario.get("compareHeaders", [])
    for header_name in compare_headers:
        header = str(header_name).lower()
        if legacy.headers.get(header) != fastapi.headers.get(header):
            differences.append(
                Difference(
                    "header",
                    f"{header}: legacy={legacy.headers.get(header)!r} fastapi={fastapi.headers.get(header)!r}",
                )
            )

    if bool(scenario.get("compareBody", True)):
        ignored_paths = [str(path) for path in scenario.get("ignoreJsonPaths", [])]
        legacy_body = _drop_json_paths(legacy.body, ignored_paths)
        fastapi_body = _drop_json_paths(fastapi.body, ignored_paths)
        if _stable_json(legacy_body) != _stable_json(fastapi_body):
            differences.append(
                Difference(
                    "body",
                    "Normalized response bodies differ",
                )
            )

    return differences


def _to_report_dict(result: ScenarioResult) -> dict[str, Any]:
    return {
        "name": result.name,
        "method": result.method,
        "path": result.path,
        "passed": result.passed,
        "skipped": result.skipped,
        "skipReason": result.skip_reason,
        "differences": [{"kind": d.kind, "detail": d.detail} for d in result.differences],
        "legacy": None
        if result.legacy is None
        else {
            "url": result.legacy.url,
            "status": result.legacy.status,
            "durationMs": result.legacy.duration_ms,
            "body": result.legacy.body,
        },
        "fastapi": None
        if result.fastapi is None
        else {
            "url": result.fastapi.url,
            "status": result.fastapi.status,
            "durationMs": result.fastapi.duration_ms,
            "body": result.fastapi.body,
        },
    }


def _write_markdown_report(output_path: Path, report: dict[str, Any]) -> None:
    lines = [
        "# API-6.9 Dual-Run Behavior Report",
        "",
        f"Generated: {report['generatedAt']}",
        f"Legacy base URL: {report['legacyBaseUrl']}",
        f"FastAPI base URL: {report['fastapiBaseUrl']}",
        "",
        "## Summary",
        "",
        f"- Total scenarios: {report['summary']['total']}",
        f"- Passed: {report['summary']['passed']}",
        f"- Failed: {report['summary']['failed']}",
        f"- Skipped: {report['summary']['skipped']}",
        "",
        "## Scenario Results",
        "",
    ]

    for item in report["results"]:
        state = "SKIPPED" if item["skipped"] else ("PASS" if item["passed"] else "FAIL")
        lines.append(f"### {state} {item['method']} {item['path']} ({item['name']})")
        if item["skipReason"]:
            lines.append(f"- Skip reason: {item['skipReason']}")
        if item["legacy"]:
            lines.append(f"- Legacy: status={item['legacy']['status']} durationMs={item['legacy']['durationMs']}")
        if item["fastapi"]:
            lines.append(f"- FastAPI: status={item['fastapi']['status']} durationMs={item['fastapi']['durationMs']}")
        if item["differences"]:
            for diff in item["differences"]:
                lines.append(f"- Difference [{diff['kind']}]: {diff['detail']}")
        lines.append("")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(lines).strip() + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Run API-6.9 dual-run behavior diff reporting")
    parser.add_argument("--legacy-base-url", required=True, help="Base URL for legacy API, for example http://localhost:4001")
    parser.add_argument("--fastapi-base-url", required=True, help="Base URL for FastAPI API, for example http://localhost:4010")
    parser.add_argument(
        "--scenarios",
        default="contracts/verification/api69-dual-run-smoke.json",
        help="Path to scenario JSON file",
    )
    parser.add_argument(
        "--output",
        default="contracts/current/api69-behavior-diff-report.json",
        help="Path to JSON report output",
    )
    parser.add_argument(
        "--markdown-output",
        default="contracts/current/api69-behavior-diff-report.md",
        help="Path to Markdown report output",
    )
    parser.add_argument(
        "--timeout-seconds",
        type=float,
        default=10.0,
        help="HTTP timeout per request",
    )
    parser.add_argument("--dry-run", action="store_true", help="Validate and print scenarios without making HTTP calls")
    args = parser.parse_args()

    scenario_path = Path(args.scenarios)
    if not scenario_path.exists():
        print(f"ERROR: scenarios file not found: {scenario_path}")
        return 2

    try:
        scenario_doc = _load_json(scenario_path)
    except json.JSONDecodeError as exc:
        print(f"ERROR: scenarios file is invalid JSON: {exc}")
        return 2

    scenarios = scenario_doc.get("scenarios", [])
    if not isinstance(scenarios, list) or not scenarios:
        print("ERROR: scenarios file must contain a non-empty 'scenarios' list")
        return 2

    if args.dry_run:
        print(f"Loaded {len(scenarios)} scenarios from {scenario_path}")
        for item in scenarios:
            name = str(item.get("name", "(unnamed)"))
            method = str(item.get("method", "GET")).upper()
            path = str(item.get("path", item.get("fastapiPath", item.get("legacyPath", "/"))))
            print(f"- {name}: {method} {path}")
            if bool(item.get("compareBody", True)) is False:
                print("  compareBody=false")
        return 0

    results: list[ScenarioResult] = []
    with httpx.Client() as client:
        for raw in scenarios:
            name = str(raw.get("name", "unnamed-scenario"))
            method = str(raw.get("method", "GET")).upper()
            path = str(raw.get("path", raw.get("fastapiPath", raw.get("legacyPath", "/"))))
            legacy_path = str(raw.get("legacyPath", path))
            fastapi_path = str(raw.get("fastapiPath", path))
            query = raw.get("query", {})
            headers = raw.get("headers", {})
            body = raw.get("body")

            if raw.get("skip", False):
                results.append(
                    ScenarioResult(
                        name=name,
                        method=method,
                        path=path,
                        passed=False,
                        skipped=True,
                        skip_reason=str(raw.get("skipReason", "scenario marked skip=true")),
                    )
                )
                continue

            legacy_url = _normalize_url(args.legacy_base_url, legacy_path)
            fastapi_url = _normalize_url(args.fastapi_base_url, fastapi_path)

            try:
                legacy_result = _request(client, legacy_url, method, headers, query, body, args.timeout_seconds)
                fastapi_result = _request(client, fastapi_url, method, headers, query, body, args.timeout_seconds)
            except httpx.HTTPError as exc:
                results.append(
                    ScenarioResult(
                        name=name,
                        method=method,
                        path=path,
                        passed=False,
                        differences=[Difference("http-error", str(exc))],
                    )
                )
                continue

            diffs = _compare(raw, legacy_result, fastapi_result)
            results.append(
                ScenarioResult(
                    name=name,
                    method=method,
                    path=path,
                    passed=len(diffs) == 0,
                    differences=diffs,
                    legacy=legacy_result,
                    fastapi=fastapi_result,
                )
            )

    failed = sum(1 for result in results if not result.passed and not result.skipped)
    skipped = sum(1 for result in results if result.skipped)
    passed = sum(1 for result in results if result.passed)
    report = {
        "generatedAt": _utc_now_iso(),
        "legacyBaseUrl": args.legacy_base_url,
        "fastapiBaseUrl": args.fastapi_base_url,
        "scenarioFile": str(scenario_path),
        "summary": {
            "total": len(results),
            "passed": passed,
            "failed": failed,
            "skipped": skipped,
        },
        "results": [_to_report_dict(result) for result in results],
    }

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, indent=2, sort_keys=False) + "\n", encoding="utf-8")

    markdown_path = Path(args.markdown_output)
    _write_markdown_report(markdown_path, report)

    print(f"Dual-run scenarios: {len(results)}")
    print(f"Passed: {passed} Failed: {failed} Skipped: {skipped}")
    print(f"JSON report: {output_path}")
    print(f"Markdown report: {markdown_path}")

    if failed > 0:
        print("BEHAVIOR DIFF FAILED: see report for mismatch details")
        return 1

    print("BEHAVIOR DIFF OK: no mismatches found")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
