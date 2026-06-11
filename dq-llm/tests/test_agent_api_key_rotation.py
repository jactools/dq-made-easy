import asyncio

from agents.config import DQAgentConfig
from agents.tools.connector_tools import ConnectorTool
from agents.tools.definition_tools import DefinitionTool
from agents.tools.rule_tools import RuleTool


class _FakeResponse:
    status_code = 200

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict[str, bool]:
        return {"ok": True}


class _FakeAsyncClient:
    def __init__(self) -> None:
        self.requests: list[dict[str, object]] = []

    async def request(self, method: str, url: str, headers: dict[str, str] | None = None, **kwargs):
        self.requests.append(
            {
                "method": method,
                "url": url,
                "headers": dict(headers or {}),
                "kwargs": kwargs,
            }
        )
        return _FakeResponse()


def _tool_factories():
    return [
        (
            ConnectorTool,
            lambda provider: ConnectorTool(
                api_base_url="http://dq-api.test",
                api_key_provider=provider,
            ),
            lambda client: client._request("GET", "/health"),
        ),
        (
            RuleTool,
            lambda provider: RuleTool(
                api_base_url="http://dq-api.test",
                llm_base_url="http://dq-llm.test",
                api_key_provider=provider,
            ),
            lambda client: client._request(client.api_base_url, "GET", "/health"),
        ),
        (
            DefinitionTool,
            lambda provider: DefinitionTool(
                api_base_url="http://dq-api.test",
                llm_base_url="http://dq-llm.test",
                api_key_provider=provider,
            ),
            lambda client: client._request(client.api_base_url, "GET", "/health"),
        ),
    ]


def test_file_backed_api_key_rotates_for_agent_tool_clients(tmp_path):
    key_file = tmp_path / "agent_api_key"
    key_file.write_text("first-key\n", encoding="utf-8")

    config = DQAgentConfig(api_key_file=key_file)
    provider = config.get_api_key_provider()

    for _, client_factory, request_factory in _tool_factories():
        tool = client_factory(provider)
        fake_client = _FakeAsyncClient()
        tool.client._client = fake_client

        asyncio.run(request_factory(tool.client))
        key_file.write_text("second-key\n", encoding="utf-8")
        asyncio.run(request_factory(tool.client))

        assert fake_client.requests[0]["headers"]["Authorization"] == "Bearer first-key"
        assert fake_client.requests[1]["headers"]["Authorization"] == "Bearer second-key"

        # Keep the request log isolated between tool implementations.
        key_file.write_text("first-key\n", encoding="utf-8")
