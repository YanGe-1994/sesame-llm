from internal.service.mcp_audit_service import McpAuditService


def test_redact_masks_nested_credentials():
    value = {
        "query": "hello",
        "headers": {
            "Authorization": "Bearer secret",
            "X-API-Key": "secret-key",
        },
        "nested": [{"password": "123456", "safe": "visible"}],
    }
    redacted = McpAuditService.redact(value)
    assert redacted["query"] == "hello"
    assert redacted["headers"]["Authorization"] == "[REDACTED]"
    assert redacted["headers"]["X-API-Key"] == "[REDACTED]"
    assert redacted["nested"][0]["password"] == "[REDACTED]"
    assert redacted["nested"][0]["safe"] == "visible"


def test_redact_truncates_large_values(monkeypatch):
    monkeypatch.setenv("MCP_AUDIT_MAX_FIELD_LENGTH", "10")
    assert McpAuditService.redact("1234567890123") == "1234567890…[TRUNCATED]"


def test_redact_limits_collection_size():
    redacted = McpAuditService.redact({"items": list(range(150))})
    assert len(redacted["items"]) == 100


def test_redact_parses_json_strings_and_masks_free_text_tokens():
    redacted_json = McpAuditService.redact('{"access_token":"secret","name":"demo"}')
    assert redacted_json == {"access_token": "[REDACTED]", "name": "demo"}
    redacted_text = McpAuditService.redact("Authorization: Bearer abc123")
    assert "abc123" not in redacted_text
    assert "[REDACTED]" in redacted_text