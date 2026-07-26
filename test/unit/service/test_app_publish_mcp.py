from types import SimpleNamespace
from uuid import uuid4

from internal.service.app_service import AppService


class FakeQuery:
    def __init__(self, result):
        self.result = result

    def filter(self, *args):
        return self

    def one_or_none(self):
        return self.result

    def all(self):
        return self.result


class FakeSession:
    def __init__(self, results):
        self.results = list(results)

    def query(self, *args):
        return FakeQuery(self.results.pop(0))


class FakeDb:
    def __init__(self, results):
        self.session = FakeSession(results)


def build_binding(server_id, schema_hash="hash-v1"):
    return [{
        "server_id": str(server_id),
        "enabled_tools": ["search"],
        "tool_versions": {"search": schema_hash},
        "approval_policy": "always_ask",
    }]


def test_validate_mcp_snapshot_accepts_matching_tool_schema():
    account_id = uuid4()
    server_id = uuid4()
    server = SimpleNamespace(
        id=server_id,
        account_id=account_id,
        name="Search MCP",
        status="active",
        auth_type="none",
        encrypted_access_token="",
    )
    tool = SimpleNamespace(
        tool_name="search",
        enabled=True,
        is_available=True,
        schema_hash="hash-v1",
    )
    service = AppService(db=FakeDb([server, [tool]]), builtin_provider_manager=None)
    assert service.validate_mcp_snapshot(
        build_binding(server_id),
        SimpleNamespace(id=account_id),
    ) == []


def test_validate_mcp_snapshot_rejects_changed_schema():
    account_id = uuid4()
    server_id = uuid4()
    server = SimpleNamespace(
        id=server_id,
        account_id=account_id,
        name="Search MCP",
        status="active",
        auth_type="none",
        encrypted_access_token="",
    )
    tool = SimpleNamespace(
        tool_name="search",
        enabled=True,
        is_available=True,
        schema_hash="hash-v2",
    )
    service = AppService(db=FakeDb([server, [tool]]), builtin_provider_manager=None)
    issues = service.validate_mcp_snapshot(
        build_binding(server_id),
        SimpleNamespace(id=account_id),
    )
    assert len(issues) == 1
    assert "Schema 已变化" in issues[0]


def test_published_snapshot_contains_display_names_without_credentials():
    account_id = uuid4()
    server_id = uuid4()
    server = SimpleNamespace(
        id=server_id,
        account_id=account_id,
        name="Search MCP",
        transport="streamable_http",
        auth_type="bearer",
    )
    tool = SimpleNamespace(
        tool_name="search",
        display_name="实时搜索",
        schema_hash="hash-v1",
        risk_level="normal",
        approval_mode="auto",
    )
    service = AppService(db=FakeDb([server, [tool]]), builtin_provider_manager=None)
    snapshots = service._build_mcp_publish_snapshot(
        build_binding(server_id),
        SimpleNamespace(id=account_id),
    )
    assert snapshots[0]["server_name"] == "Search MCP"
    assert snapshots[0]["tool_snapshots"][0]["display_name"] == "实时搜索"
    assert "encrypted_secret" not in snapshots[0]
