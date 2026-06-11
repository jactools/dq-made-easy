#!/usr/bin/env python3
from __future__ import annotations

import json
import threading
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

CORRELATION_HEADER = "X-Correlation-ID"


@dataclass
class State:
    api_seen_suite_get_cid: str | None = None
    api_seen_report_post_cid: str | None = None
    token_seen_cid: str | None = None


def _read_response_json(response) -> dict | list:
    return json.loads(response.read().decode("utf-8"))


def _worker_api_headers(token_provider, *, correlation_id: str) -> dict[str, str]:
    token_provider.get_token(correlation_id=correlation_id)
    return {
        "Accept": "application/json",
        CORRELATION_HEADER: correlation_id,
        "Authorization": "Bearer token-smoke-1",
    }


def _worker_get_suite_envelope(api_base: str, token_provider, *, suite_id: str, suite_version: int, correlation_id: str) -> dict:
    params = urllib.parse.urlencode({"suite_version": suite_version})
    request = urllib.request.Request(
        f"{api_base}/rulebuilder/v1/gx/suites/{suite_id}?{params}",
        method="GET",
        headers=_worker_api_headers(token_provider, correlation_id=correlation_id),
    )
    with urllib.request.urlopen(request, timeout=5) as response:
        payload = _read_response_json(response)
    if not isinstance(payload, dict):
        raise RuntimeError("suite envelope response must be a JSON object")
    return payload


def _worker_report_run(api_base: str, token_provider, *, run_id: str, correlation_id: str, result_summary: dict) -> dict:
    request = urllib.request.Request(
        f"{api_base}/rulebuilder/v1/gx/runs/{run_id}/report",
        method="POST",
        data=json.dumps(
            {
                "new_status": "succeeded",
                "changed_by": "worker-smoke",
                "reason": "GX worker completed smoke report",
                "details": {"source": "dq-engine-gx-worker"},
                "result_summary": result_summary,
                "diagnostics": [],
                "failure_code": None,
                "failure_message": None,
            }
        ).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            **_worker_api_headers(token_provider, correlation_id=correlation_id),
        },
    )
    with urllib.request.urlopen(request, timeout=5) as response:
        payload = _read_response_json(response)
    if not isinstance(payload, dict):
        raise RuntimeError("run report response must be a JSON object")
    return payload


def _read_json(handler: BaseHTTPRequestHandler) -> dict:
    length = int(handler.headers.get("Content-Length") or 0)
    raw = handler.rfile.read(length) if length > 0 else b"{}"
    if not raw:
        return {}
    return json.loads(raw.decode("utf-8"))


def _write_json(handler: BaseHTTPRequestHandler, status: int, payload: dict) -> None:
    body = json.dumps(payload).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def _api_handler_factory(state: State):
    class ApiHandler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            parsed = urllib.parse.urlparse(self.path)
            if parsed.path != "/rulebuilder/v1/gx/suites/suite-smoke-1":
                _write_json(self, 404, {"error": "not found"})
                return

            state.api_seen_suite_get_cid = self.headers.get(CORRELATION_HEADER)
            _write_json(
                self,
                200,
                {
                    "suite_id": "suite-smoke-1",
                    "suite_version": 1,
                    "expectations": [
                        {
                            "expectation_type": "expect_column_values_to_not_be_null",
                            "kwargs": {"column": "id"},
                        }
                    ],
                    "compiled_from": {"rule_ids": ["rule-smoke-1"]},
                    "resolved_execution_scope": {"data_object_version_ids": ["dov-smoke-1"]},
                },
            )

        def do_POST(self) -> None:  # noqa: N802
            if self.path != "/rulebuilder/v1/gx/runs/run-smoke-1/report":
                _write_json(self, 404, {"error": "not found"})
                return

            _read_json(self)
            state.api_seen_report_post_cid = self.headers.get(CORRELATION_HEADER)
            _write_json(self, 200, {"ok": True})

        def log_message(self, fmt: str, *args) -> None:  # noqa: A003
            return

    return ApiHandler

def _start_server(handler_cls: type[BaseHTTPRequestHandler]) -> ThreadingHTTPServer:
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler_cls)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server


class _TokenProvider:
    def __init__(self, state: State) -> None:
        self._state = state

    def get_token(self, *, correlation_id: str) -> str:
        self._state.token_seen_cid = correlation_id
        return "token-smoke-1"


def main() -> int:
    state = State()

    api_server = _start_server(_api_handler_factory(state))
    api_base = f"http://127.0.0.1:{api_server.server_port}"

    cid = "cid-smoke-001"
    token_provider = _TokenProvider(state)
    try:
        envelope = _worker_get_suite_envelope(
            api_base,
            token_provider,
            suite_id="suite-smoke-1",
            suite_version=1,
            correlation_id=cid,
        )
        _worker_report_run(
            api_base,
            token_provider,
            run_id="run-smoke-1",
            correlation_id=cid,
            result_summary={"suite_id": envelope.get("suite_id")},
        )
    except urllib.error.URLError as exc:
        print(f"ERROR: smoke request failed: {exc}")
        api_server.shutdown()
        return 1

    api_server.shutdown()

    errors: list[str] = []
    if state.api_seen_suite_get_cid != cid:
        errors.append("API suite lookup did not receive forwarded correlation header")
    if state.api_seen_report_post_cid != cid:
        errors.append("API run report did not receive forwarded correlation header")
    if state.token_seen_cid != cid:
        errors.append("token provider did not receive worker correlation id")

    if errors:
        print("ERROR: correlation smoke test failed")
        for issue in errors:
            print(f"- {issue}")
        return 1

    print("OK: correlation smoke chain passed (gx worker -> api lookup/report)")
    print(
        json.dumps(
            {
                "cid": cid,
                "apiSeenSuiteGetCid": state.api_seen_suite_get_cid,
                "apiSeenReportPostCid": state.api_seen_report_post_cid,
                "tokenSeenCid": state.token_seen_cid,
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())