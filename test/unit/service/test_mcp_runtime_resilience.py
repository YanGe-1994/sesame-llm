from types import SimpleNamespace
from uuid import uuid4

import pytest

from internal.service.mcp_resilience_service import McpCallPermit
from internal.service.mcp_runtime_service import McpRuntimeService


class FakeResilience:
    def __init__(self):
        self.successes = 0
        self.failures = 0

    def before_call(self, account_id, server_id, tool_name):
        return McpCallPermit(str(server_id))

    def record_success(self, permit):
        self.successes += 1

    def record_failure(self, permit):
        self.failures += 1


class FakeOAuth:
    def __init__(self):
        self.calls = 0

    def get_authorization_headers(self, server_id, account_id):
        self.calls += 1
        return {"Authorization": "Bearer token"}, "token"


class FakeClient:
    def __init__(self, fail=False):
        self.fail = fail
        self.headers = None

    def call_tool(self, endpoint_url, tool_name, arguments, headers=None):
        self.headers = headers
        if self.fail:
            raise RuntimeError("remote failed")
        return {"success": True, "structured_content": arguments}


def build_runtime_tool(auth_type="none", fail=False):
    resilience = FakeResilience()
    oauth = FakeOAuth()
    client = FakeClient(fail)
    service = McpRuntimeService(
        db=None,
        mcp_client=client,
        mcp_oauth_service=oauth,
        mcp_resilience_service=resilience,
    )
    server = SimpleNamespace(
        id=uuid4(),
        account_id=uuid4(),
        endpoint_url="https://mcp.example/mcp",
        auth_type=auth_type,
        encrypted_secret="",
        auth_header_name="",
        name="demo",
    )
    tool = SimpleNamespace(
        tool_name="echo",
        display_name="Echo",
        description="Echo input",
        input_schema={
            "type": "object",
            "properties": {"value": {"type": "string"}},
            "required": ["value"],
        },
    )
    return service._build_tool(server, tool, "mcp_demo_echo"), client, oauth, resilience


def test_runtime_records_success():
    tool, client, _, resilience = build_runtime_tool()
    result = tool.invoke({"value": "hello"})
    assert result["structured_content"] == {"value": "hello"}
    assert resilience.successes == 1
    assert resilience.failures == 0
    assert client.headers == {}


def test_runtime_uses_oauth_and_records_failure():
    tool, client, oauth, resilience = build_runtime_tool(auth_type="oauth2", fail=True)
    with pytest.raises(RuntimeError, match="remote failed"):
        tool.invoke({"value": "hello"})
    assert oauth.calls == 1
    assert client.headers == {"Authorization": "Bearer token"}
    assert resilience.successes == 0
    assert resilience.failures == 1
