from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

from dq_cli.run_plan import CliConfig
from dq_cli.run_plan import execute
from dq_cli.run_plan import main


def _client(handler):
    return httpx.Client(transport=httpx.MockTransport(handler), base_url="https://kong.example")


def test_run_plan_list_uses_password_grant_and_prints_json(capsys: pytest.CaptureFixture[str]) -> None:
    requests: list[tuple[str, str, dict[str, str], dict[str, str] | None]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = request.read().decode("utf-8")
        form = dict(item.split("=", 1) for item in body.split("&") if item)
        requests.append((request.method, str(request.url), dict(request.headers), form))
        if request.url.path.endswith("/protocol/openid-connect/token"):
            return httpx.Response(200, json={"access_token": "token-123"})
        return httpx.Response(
            200,
            json={
                "validation_run_plans": [
                    {
                        "run_plan_id": "run-plan-1",
                        "status": "active",
                        "workspace_id": "workspace-1",
                        "business_key": "run-plan-1",
                        "current_active_version_id": "run-plan-version-1",
                    }
                ],
                "validation_suites": [],
                "validation_summary": {"run_plan_count": 1, "suite_count": 0, "engine_types": ["gx"]},
            },
        )

    original_create_client = None
    from dq_cli import run_plan as module

    original_create_client = module._create_client
    module._create_client = lambda _: _client(handler)  # type: ignore[assignment]
    try:
        exit_code = main(
            [
                "--base-url",
                "https://kong.example",
                "--issuer-url",
                "https://keycloak.example/realms/jaccloud",
                "--client-id",
                "dq-rules-ui",
                "--username",
                "alice@example.com",
                "--password",
                "secret",
                "--json",
                "list",
                "--workspace-id",
                "workspace-1",
            ]
        )
        assert exit_code == 0
        out = capsys.readouterr().out
        assert '"run_plan_id": "run-plan-1"' in out
        assert requests[0][0] == "POST"
        assert requests[0][1] == "https://keycloak.example/realms/jaccloud/protocol/openid-connect/token"
        assert requests[1][0] == "GET"
        assert requests[1][1].startswith("https://kong.example/rulebuilder/v1/run-plan")
        assert dict(httpx.QueryParams(requests[1][1].split("?", 1)[1])) == {"workspaceId": "workspace-1"}
    finally:
        module._create_client = original_create_client  # type: ignore[assignment]


def test_run_plan_invoke_requires_matching_run_plan_id() -> None:
    requests: list[tuple[str, str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append((request.method, str(request.url)))
        if request.url.path.endswith("/protocol/openid-connect/token"):
            return httpx.Response(200, json={"access_token": "token-123"})
        return httpx.Response(
            202,
            json={
                "run_id": "run-1",
                "queue_message_id": "run-1",
                "run_plan_id": "run-plan-1",
                "run_plan_version_id": "run-plan-version-1",
                "scheduled_at": "2026-05-17T00:00:00Z",
            },
        )

    config = CliConfig(
        base_url="https://kong.example",
        token=None,
        issuer_url="https://keycloak.example/realms/jaccloud",
        client_id="dq-rules-ui",
        username="alice@example.com",
        password="secret",
        ca_cert=None,
        insecure=False,
        timeout=30.0,
        json_output=False,
        request_id="request-1",
        correlation_id="correlation-1",
        command="invoke",
        run_plan_id="run-plan-1",
    )

    from dq_cli import run_plan as module

    original_create_client = module._create_client
    module._create_client = lambda _: _client(handler)  # type: ignore[assignment]
    try:
        payload = execute(config)
        assert payload["run_plan_id"] == "run-plan-1"
        assert payload["queue_message_id"] == "run-1"
        assert requests[0] == ("POST", "https://keycloak.example/realms/jaccloud/protocol/openid-connect/token")
        assert requests[1] == ("POST", "https://kong.example/api/rulebuilder/v1/validation-run-plans/run-plan-1/replay")
    finally:
        module._create_client = original_create_client  # type: ignore[assignment]


def test_run_plan_invoke_accepts_run_plan_name_and_resolves_business_key(capsys: pytest.CaptureFixture[str]) -> None:
    requests: list[tuple[str, str, dict[str, str], dict[str, object] | None]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/protocol/openid-connect/token"):
            requests.append((request.method, str(request.url), dict(request.url.params), None))
            return httpx.Response(200, json={"access_token": "token-123"})

        if request.url.path.endswith("/run-plan"):
            requests.append((request.method, str(request.url), dict(request.url.params), None))
            return httpx.Response(
                200,
                json={
                    "validation_run_plans": [
                        {
                            "run_plan_id": "run-plan-1",
                            "workspace_id": "workspace-1",
                            "business_key": "sales-plan",
                            "planning_mode": "single_suite",
                            "status": "active",
                            "current_active_version_id": "run-plan-version-1",
                            "created_at": "2026-05-17T00:00:00Z",
                            "updated_at": "2026-05-17T00:00:00Z",
                            "versions": [],
                        }
                    ],
                    "validation_suites": [],
                    "validation_summary": {"run_plan_count": 1, "suite_count": 0, "engine_types": ["gx"]},
                },
            )

        requests.append((request.method, str(request.url), dict(request.url.params), None))
        return httpx.Response(
            202,
            json={
                "run_id": "run-1",
                "queue_message_id": "msg-1",
                "run_plan_id": "run-plan-1",
                "run_plan_version_id": "run-plan-version-1",
                "scheduled_at": "2026-05-17T00:00:00Z",
            },
        )

    from dq_cli import run_plan as module

    original_create_client = module._create_client
    module._create_client = lambda _: _client(handler)  # type: ignore[assignment]
    try:
        exit_code = main(
            [
                "--base-url",
                "https://kong.example",
                "--issuer-url",
                "https://keycloak.example/realms/jaccloud",
                "--client-id",
                "dq-rules-ui",
                "--username",
                "alice@example.com",
                "--password",
                "secret",
                "--json",
                "invoke",
                "--run-plan-name",
                "sales-plan",
            ]
        )
        assert exit_code == 0
        out = capsys.readouterr().out
        assert '"run_plan_id": "run-plan-1"' in out
        assert requests[0][0] == "POST"
        assert requests[1][0] == "GET"
        assert dict(httpx.QueryParams(requests[1][1].split("?", 1)[1])) == {"businessKey": "sales-plan"}
        assert requests[2][0] == "POST"
        assert requests[2][1] == "https://kong.example/api/rulebuilder/v1/validation-run-plans/run-plan-1/replay"
    finally:
        module._create_client = original_create_client  # type: ignore[assignment]


@pytest.mark.parametrize(
    ("filename", "content"),
    [
        (
            "validation-run-plan.json",
            json.dumps(
                {
                    "run_plan_id": "run-plan-file-1",
                    "business_key": "sales-plan-file",
                    "workspace_id": "workspace-1",
                    "planning_mode": "single_suite",
                }
            ),
        ),
        (
            "validation-run-plan.yml",
            "run_plan_id: run-plan-file-1\nbusiness_key: sales-plan-file\nworkspace_id: workspace-1\nplanning_mode: single_suite\n",
        ),
    ],
)
def test_run_plan_invoke_accepts_run_plan_file_json_and_yaml(
    tmp_path: Path,
    filename: str,
    content: str,
    capsys: pytest.CaptureFixture[str],
) -> None:
    requests: list[tuple[str, str, dict[str, str], dict[str, object] | None]] = []
    plan_file = tmp_path / filename
    plan_file.write_text(content, encoding="utf-8")

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/protocol/openid-connect/token"):
            requests.append((request.method, str(request.url), dict(request.url.params), None))
            return httpx.Response(200, json={"access_token": "token-123"})

        requests.append((request.method, str(request.url), dict(request.url.params), None))
        return httpx.Response(
            202,
            json={
                "run_id": "run-1",
                "queue_message_id": "msg-1",
                "run_plan_id": "run-plan-file-1",
                "run_plan_version_id": "run-plan-version-1",
                "scheduled_at": "2026-05-17T00:00:00Z",
            },
        )

    from dq_cli import run_plan as module

    original_create_client = module._create_client
    module._create_client = lambda _: _client(handler)  # type: ignore[assignment]
    try:
        exit_code = main(
            [
                "--base-url",
                "https://kong.example",
                "--issuer-url",
                "https://keycloak.example/realms/jaccloud",
                "--client-id",
                "dq-rules-ui",
                "--username",
                "alice@example.com",
                "--password",
                "secret",
                "--json",
                "invoke",
                "--run-plan-file",
                str(plan_file),
            ]
        )
        assert exit_code == 0
        out = capsys.readouterr().out
        assert '"run_plan_id": "run-plan-file-1"' in out
        assert len(requests) == 2
        assert requests[0][0] == "POST"
        assert requests[1][0] == "POST"
        assert requests[1][1] == "https://kong.example/api/rulebuilder/v1/validation-run-plans/run-plan-file-1/replay"
    finally:
        module._create_client = original_create_client  # type: ignore[assignment]


def test_run_plan_invoke_accepts_gx_suite_file_and_resolves_run_plan_id(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    requests: list[tuple[str, str, dict[str, str], dict[str, object] | None]] = []
    plan_file = tmp_path / "example_gx_suite.yml"
    plan_file.write_text(
        """assignmentScope:
  dataObjectId: do-1
  datasetId: ds-1
  dataProductId: dp-1
executionContract:
  traceability:
    gxSuiteId: suite-1
    gxSuiteVersion: 1
gxSuite:
  expectation_suite_name: suite-1
""",
        encoding="utf-8",
    )

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/protocol/openid-connect/token"):
            requests.append((request.method, str(request.url), dict(request.url.params), None))
            return httpx.Response(200, json={"access_token": "token-123"})

        if request.url.path.endswith("/run-plan"):
            requests.append((request.method, str(request.url), dict(request.url.params), None))
            return httpx.Response(
                200,
                json={
                    "validation_run_plans": [
                        {
                            "run_plan_id": "run-plan-1",
                            "workspace_id": "workspace-1",
                            "business_key": "sales-plan",
                            "planning_mode": "single_suite",
                            "status": "active",
                            "current_active_version_id": "run-plan-version-1",
                            "created_at": "2026-05-17T00:00:00Z",
                            "updated_at": "2026-05-17T00:00:00Z",
                            "versions": [],
                        }
                    ],
                    "validation_suites": [
                        {
                            "run_plan_id": "run-plan-1",
                            "run_plan_version_id": "run-plan-version-1",
                            "governance_state": "approved",
                            "artifact_id": "suite-1",
                            "artifact_version": 1,
                            "engine_type": "gx",
                            "schedule_definition": {"scheduledAt": "2026-05-17T00:00:00Z"},
                            "created_at": "2026-05-17T00:00:00Z",
                        }
                    ],
                    "validation_summary": {"run_plan_count": 1, "suite_count": 1, "engine_types": ["gx"]},
                },
            )

        requests.append((request.method, str(request.url), dict(request.url.params), None))
        return httpx.Response(
            202,
            json={
                "run_id": "run-1",
                "queue_message_id": "msg-1",
                "run_plan_id": "run-plan-1",
                "run_plan_version_id": "run-plan-version-1",
                "scheduled_at": "2026-05-17T00:00:00Z",
            },
        )

    from dq_cli import run_plan as module

    original_create_client = module._create_client
    module._create_client = lambda _: _client(handler)  # type: ignore[assignment]
    try:
        exit_code = main(
            [
                "--base-url",
                "https://kong.example",
                "--issuer-url",
                "https://keycloak.example/realms/jaccloud",
                "--client-id",
                "dq-rules-ui",
                "--username",
                "alice@example.com",
                "--password",
                "secret",
                "--json",
                "invoke",
                "--run-plan-file",
                str(plan_file),
            ]
        )
        assert exit_code == 0
        out = capsys.readouterr().out
        assert '"run_plan_id": "run-plan-1"' in out
        assert len(requests) == 3
        assert requests[0][0] == "POST"
        assert requests[1][0] == "GET"
        assert requests[1][1].startswith("https://kong.example/rulebuilder/v1/run-plan")
        assert requests[2][0] == "POST"
        assert requests[2][1] == "https://kong.example/api/rulebuilder/v1/validation-run-plans/run-plan-1/replay"
    finally:
        module._create_client = original_create_client  # type: ignore[assignment]


def test_run_plan_initiate_posts_create_payload_and_prints_text(capsys: pytest.CaptureFixture[str]) -> None:
    requests: list[tuple[str, str, dict[str, str], dict[str, object] | None]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/protocol/openid-connect/token"):
            body_text = request.read().decode("utf-8")
            payload = dict(item.split("=", 1) for item in body_text.split("&") if item)
            requests.append((request.method, str(request.url), dict(request.headers), payload))
            return httpx.Response(200, json={"access_token": "token-123"})
        body_text = request.read().decode("utf-8")
        payload = json.loads(body_text) if body_text else None
        requests.append((request.method, str(request.url), dict(request.headers), payload))
        return httpx.Response(
            201,
            json={
                "run_plan_id": "run-plan-1",
                "workspace_id": "workspace-1",
                "planning_mode": "single_suite",
                "status": "draft",
                "created_at": "2026-05-22T20:00:00+00:00",
                "updated_at": "2026-05-22T20:00:00+00:00",
                "versions": [],
                "transition_events": [],
            },
        )

    from dq_cli import run_plan as module

    original_create_client = module._create_client
    module._create_client = lambda _: _client(handler)  # type: ignore[assignment]
    try:
        exit_code = main(
            [
                "--base-url",
                "https://kong.example",
                "--issuer-url",
                "https://keycloak.example/realms/jaccloud",
                "--client-id",
                "dq-rules-ui",
                "--username",
                "alice@example.com",
                "--password",
                "secret",
                "initiate",
                "--workspace-id",
                "workspace-1",
                "--scheduled-at",
                "2026-05-22T20:00:00Z",
                "--suite-id",
                "gx_suite_1",
                "--suite-version",
                "1",
            ]
        )
        assert exit_code == 0
        out = capsys.readouterr().out
        assert "DQ run plan initiation accepted" in out
        assert "run_plan_id: run-plan-1" in out
        assert requests[0][0] == "POST"
        assert requests[0][1] == "https://keycloak.example/realms/jaccloud/protocol/openid-connect/token"
        assert requests[1][0] == "POST"
        assert requests[1][1].endswith("/rulebuilder/v1/gx/run-plans/initiate")
        assert requests[1][3] == {
            "workspace_id": "workspace-1",
            "planning_mode": "single_suite",
            "suite_id": "gx_suite_1",
            "suite_version": 1,
            "scheduled_at": "2026-05-22T20:00:00Z",
        }
    finally:
        module._create_client = original_create_client  # type: ignore[assignment]


def test_run_plan_initiate_accepts_name_aliases_and_resolves_ids(capsys: pytest.CaptureFixture[str]) -> None:
    requests: list[tuple[str, str, dict[str, str], dict[str, object] | None]] = []

    def _page_response(*, item: dict[str, object]) -> dict[str, object]:
        return {
            "data": [item],
            "pagination": {
                "total": 1,
                "page": 1,
                "limit": 100,
                "total_pages": 1,
                "has_next": False,
                "has_previous": False,
            },
        }

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/protocol/openid-connect/token"):
            body_text = request.read().decode("utf-8")
            payload = dict(item.split("=", 1) for item in body_text.split("&") if item)
            requests.append((request.method, str(request.url), dict(request.url.params), payload))
            return httpx.Response(200, json={"access_token": "token-123"})

        if request.url.path.endswith("/gx/run-plans/initiate"):
            payload = json.loads(request.read().decode("utf-8"))
            requests.append((request.method, str(request.url), dict(request.url.params), payload))
            return httpx.Response(
                201,
                json={
                    "run_plan_id": "run-plan-1",
                    "workspace_id": "workspace-1",
                    "planning_mode": "grouped_scope",
                    "status": "draft",
                    "created_at": "2026-05-22T20:00:00+00:00",
                    "updated_at": "2026-05-22T20:00:00+00:00",
                    "versions": [],
                    "transition_events": [],
                },
            )

        requests.append((request.method, str(request.url), dict(request.url.params), None))
        if request.url.path.endswith("/workspaces"):
            return httpx.Response(
                200,
                json=_page_response(
                    item={
                        "id": "workspace-1",
                        "name": "Sales Workspace",
                        "description": "",
                    }
                ),
            )
        if request.url.path.endswith("/data-products"):
            return httpx.Response(
                200,
                json=_page_response(
                    item={
                        "id": "product-1",
                        "name": "Sales Product",
                        "workspace_id": "workspace-1",
                    }
                ),
            )
        if request.url.path.endswith("/data-sets"):
            return httpx.Response(
                200,
                json=_page_response(
                    item={
                        "id": "dataset-1",
                        "product_id": "product-1",
                        "name": "Orders Dataset",
                        "workspace_id": "workspace-1",
                    }
                ),
            )
        if request.url.path.endswith("/data-objects-catalog"):
            return httpx.Response(
                200,
                json=_page_response(
                    item={
                        "id": "object-1",
                        "dataset_id": "dataset-1",
                        "name": "Orders Table",
                    }
                ),
            )

    from dq_cli import run_plan as module

    original_create_client = module._create_client
    module._create_client = lambda _: _client(handler)  # type: ignore[assignment]
    try:
        exit_code = main(
            [
                "--base-url",
                "https://kong.example",
                "--issuer-url",
                "https://keycloak.example/realms/jaccloud",
                "--client-id",
                "dq-rules-ui",
                "--username",
                "alice@example.com",
                "--password",
                "secret",
                "initiate",
                "--workspace-name",
                "Sales Workspace",
                "--scheduled-at",
                "2026-05-22T20:00:00Z",
                "--planning-mode",
                "grouped_scope",
                "--data-product-name",
                "Sales Product",
                "--dataset-name",
                "Orders Dataset",
                "--data-object-name",
                "Orders Table",
            ]
        )
        assert exit_code == 0
        out = capsys.readouterr().out
        assert "DQ run plan initiation accepted" in out
        assert "run_plan_id: run-plan-1" in out
        assert requests[0][0] == "POST"
        assert requests[1][1].startswith("https://kong.example/rulebuilder/v1/workspaces")
        assert requests[1][2] == {"page": "1", "limit": "100"}
        assert requests[2][1].startswith("https://kong.example/rulebuilder/v1/data-catalog/v1/data-products")
        assert requests[2][2] == {"workspace": "workspace-1", "page": "1", "limit": "100"}
        assert requests[3][1].startswith("https://kong.example/rulebuilder/v1/data-catalog/v1/data-sets")
        assert requests[3][2] == {"workspace": "workspace-1", "productId": "product-1", "page": "1", "limit": "100"}
        assert requests[4][1].startswith("https://kong.example/rulebuilder/v1/data-catalog/v1/data-objects-catalog")
        assert requests[4][2] == {"dataSetId": "dataset-1", "page": "1", "limit": "100"}
        assert requests[5][0] == "POST"
        assert requests[5][1].endswith("/rulebuilder/v1/gx/run-plans/initiate")
        assert requests[5][3] == {
            "workspace_id": "workspace-1",
            "planning_mode": "grouped_scope",
            "scheduled_at": "2026-05-22T20:00:00Z",
            "data_object_id": "object-1",
            "dataset_id": "dataset-1",
            "data_product_id": "product-1",
        }
    finally:
        module._create_client = original_create_client  # type: ignore[assignment]


def test_run_plan_export_writes_gx_and_neutral_files(tmp_path: Path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/protocol/openid-connect/token"):
            return httpx.Response(200, json={"access_token": "token-123"})
        if request.url.path.endswith("/gx/run-plans/run-plan-1"):
            return httpx.Response(
                200,
                json={
                    "run_plan_id": "run-plan-1",
                    "business_key": "run-plan-1",
                    "workspace_id": "workspace-1",
                    "planning_mode": "single_suite",
                    "status": "active",
                    "created_at": "2026-05-17T00:00:00Z",
                    "updated_at": "2026-05-17T00:00:00Z",
                    "versions": [],
                    "transition_events": [],
                },
            )
        return httpx.Response(
            200,
            json={
                "validation_run_plans": [
                    {
                        "run_plan_id": "run-plan-1",
                        "workspace_id": "workspace-1",
                        "planning_mode": "single_suite",
                        "status": "active",
                        "created_at": "2026-05-17T00:00:00Z",
                        "updated_at": "2026-05-17T00:00:00Z",
                        "versions": [
                            {
                                "run_plan_version_id": "run-plan-version-1",
                                "run_plan_id": "run-plan-1",
                                "governance_state": "approved",
                                "artifact_id": "suite-1",
                                "artifact_version": 1,
                                "artifact_snapshot": {
                                    "suiteId": "suite-1",
                                    "suiteVersion": 1,
                                    "engineType": "gx",
                                    "gxSuite": {"name": "suite-1"},
                                },
                                "validation_artifact_selection": {
                                    "selection_mode": "single_suite",
                                    "artifactRefs": [
                                        {"artifactId": "suite-1", "artifactVersion": 1, "engineType": "gx"}
                                    ],
                                },
                                "schedule_definition": {"scheduledAt": "2026-05-17T00:00:00Z"},
                                "created_at": "2026-05-17T00:00:00Z",
                            }
                        ],
                    }
                ],
                "validation_suites": [
                    {
                        "run_plan_id": "run-plan-1",
                        "run_plan_version_id": "run-plan-version-1",
                        "governance_state": "approved",
                        "artifact_id": "suite-1",
                        "artifact_version": 1,
                        "engine_type": "gx",
                        "schedule_definition": {"scheduledAt": "2026-05-17T00:00:00Z"},
                        "created_at": "2026-05-17T00:00:00Z",
                    }
                ],
                "validation_summary": {"run_plan_count": 1, "suite_count": 1, "engine_types": ["gx"]},
            },
        )

    output_dir = tmp_path / "run-plan-export"

    from dq_cli import run_plan as module

    original_create_client = module._create_client
    module._create_client = lambda _: _client(handler)  # type: ignore[assignment]
    try:
        exit_code = main(
            [
                "--base-url",
                "https://kong.example",
                "--issuer-url",
                "https://keycloak.example/realms/jaccloud",
                "--client-id",
                "dq-rules-ui",
                "--username",
                "alice@example.com",
                "--password",
                "secret",
                "export",
                "--run-plan-id",
                "run-plan-1",
                "--output-dir",
                str(output_dir),
            ]
        )
        assert exit_code == 0
        neutral_file = output_dir / "validation-run-plan.json"
        gx_file = output_dir / "gx-run-plan.json"
        assert neutral_file.exists()
        assert gx_file.exists()
        neutral_payload = neutral_file.read_text(encoding="utf-8")
        gx_payload = gx_file.read_text(encoding="utf-8")
        assert '"run_plan_id": "run-plan-1"' in neutral_payload
        assert '"run_plan_id": "run-plan-1"' in gx_payload
    finally:
        module._create_client = original_create_client  # type: ignore[assignment]


def test_run_plan_export_skips_gx_file_for_mixed_engine_types(tmp_path: Path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/protocol/openid-connect/token"):
            return httpx.Response(200, json={"access_token": "token-123"})
        if request.url.path.endswith("/gx/run-plans/run-plan-2"):
            raise AssertionError("GX export should not be requested for mixed-engine plans")
        return httpx.Response(
            200,
            json={
                "validation_run_plans": [
                    {
                        "run_plan_id": "run-plan-2",
                        "workspace_id": "workspace-1",
                        "planning_mode": "single_suite",
                        "status": "active",
                        "created_at": "2026-05-17T00:00:00Z",
                        "updated_at": "2026-05-17T00:00:00Z",
                        "versions": [
                            {
                                "run_plan_version_id": "run-plan-version-2",
                                "run_plan_id": "run-plan-2",
                                "governance_state": "approved",
                                "artifact_id": "suite-2",
                                "artifact_version": 1,
                                "artifact_snapshot": {
                                    "suiteId": "suite-2",
                                    "suiteVersion": 1,
                                    "engineType": "gx",
                                    "gxSuite": {"name": "suite-2"},
                                },
                                "validation_artifact_selection": {
                                    "selection_mode": "single_suite",
                                    "artifactRefs": [
                                        {"artifactId": "suite-2", "artifactVersion": 1, "engineType": "gx"}
                                    ],
                                },
                                "schedule_definition": {"scheduledAt": "2026-05-17T00:00:00Z"},
                                "created_at": "2026-05-17T00:00:00Z",
                            }
                        ],
                    }
                ],
                "validation_suites": [
                    {
                        "run_plan_id": "run-plan-2",
                        "run_plan_version_id": "run-plan-version-2",
                        "governance_state": "approved",
                        "artifact_id": "suite-2",
                        "artifact_version": 1,
                        "engine_type": "gx",
                        "schedule_definition": {"scheduledAt": "2026-05-17T00:00:00Z"},
                        "created_at": "2026-05-17T00:00:00Z",
                    },
                    {
                        "run_plan_id": "run-plan-2",
                        "run_plan_version_id": "run-plan-version-2",
                        "governance_state": "approved",
                        "artifact_id": "suite-3",
                        "artifact_version": 1,
                        "engine_type": "soda",
                        "schedule_definition": {"scheduledAt": "2026-05-17T00:00:00Z"},
                        "created_at": "2026-05-17T00:00:00Z",
                    },
                ],
                "validation_summary": {"run_plan_count": 1, "suite_count": 2, "engine_types": ["gx", "soda"]},
            },
        )

    output_dir = tmp_path / "mixed-run-plan-export"

    from dq_cli import run_plan as module

    original_create_client = module._create_client
    module._create_client = lambda _: _client(handler)  # type: ignore[assignment]
    try:
        exit_code = main(
            [
                "--base-url",
                "https://kong.example",
                "--issuer-url",
                "https://keycloak.example/realms/jaccloud",
                "--client-id",
                "dq-rules-ui",
                "--username",
                "alice@example.com",
                "--password",
                "secret",
                "export",
                "--run-plan-id",
                "run-plan-2",
                "--output-dir",
                str(output_dir),
            ]
        )
        assert exit_code == 0
        assert (output_dir / "validation-run-plan.json").exists()
        assert not (output_dir / "gx-run-plan.json").exists()
    finally:
        module._create_client = original_create_client  # type: ignore[assignment]
