import json

import pytest
from redis.exceptions import RedisError

import internal.service.mcp_resilience_service as resilience_module
from internal.service.mcp_resilience_service import (
    McpCircuitOpenError,
    McpRateLimitError,
    McpResilienceService,
)


class FakeRedis:
    def __init__(self):
        self.values = {}
        self.expirations = {}

    def eval(self, script, numkeys, *args):
        keys = list(args[:numkeys])
        limits = [int(value) for value in args[numkeys:numkeys * 2]]
        for index, key in enumerate(keys):
            if limits[index] > 0 and int(self.values.get(key, 0)) >= limits[index]:
                return index + 1
        for key in keys:
            self.values[key] = int(self.values.get(key, 0)) + 1
        return 0

    def get(self, key):
        return self.values.get(key)

    def set(self, key, value, nx=False, ex=None):
        if nx and key in self.values:
            return False
        self.values[key] = value
        return True

    def setex(self, key, ttl, value):
        self.values[key] = value
        self.expirations[key] = ttl
        return True

    def incr(self, key):
        self.values[key] = int(self.values.get(key, 0)) + 1
        return self.values[key]

    def expire(self, key, ttl):
        self.expirations[key] = ttl
        return True

    def delete(self, *keys):
        for key in keys:
            self.values.pop(key, None)
            self.expirations.pop(key, None)
        return len(keys)


def configure(monkeypatch):
    settings = {
        "MCP_RATE_LIMIT_ACCOUNT": "2",
        "MCP_RATE_LIMIT_SERVER": "10",
        "MCP_RATE_LIMIT_TOOL": "10",
        "MCP_RATE_LIMIT_WINDOW_SECONDS": "60",
        "MCP_CIRCUIT_FAILURE_THRESHOLD": "2",
        "MCP_CIRCUIT_FAILURE_WINDOW_SECONDS": "120",
        "MCP_CIRCUIT_BASE_BACKOFF_SECONDS": "30",
        "MCP_CIRCUIT_MAX_BACKOFF_SECONDS": "120",
        "MCP_CIRCUIT_HALF_OPEN_TIMEOUT_SECONDS": "15",
    }
    for key, value in settings.items():
        monkeypatch.setenv(key, value)


def test_account_rate_limit_is_atomic(monkeypatch):
    configure(monkeypatch)
    monkeypatch.setattr(resilience_module.time, "time", lambda: 120)
    service = McpResilienceService(FakeRedis())
    service.before_call("account", "server-1", "search")
    service.before_call("account", "server-2", "weather")
    with pytest.raises(McpRateLimitError, match="account"):
        service.before_call("account", "server-3", "files")


def test_failures_open_circuit_and_block_calls(monkeypatch):
    configure(monkeypatch)
    now = [100.0]
    monkeypatch.setattr(resilience_module.time, "time", lambda: now[0])
    service = McpResilienceService(FakeRedis())

    first = service.before_call("a1", "s1", "tool")
    assert service.record_failure(first) == 0
    second = service.before_call("a2", "s1", "tool")
    assert service.record_failure(second) == 30

    with pytest.raises(McpCircuitOpenError, match="retry after"):
        service.before_call("a3", "s1", "tool")


def test_half_open_allows_one_probe_and_success_resets(monkeypatch):
    configure(monkeypatch)
    now = [100.0]
    monkeypatch.setattr(resilience_module.time, "time", lambda: now[0])
    redis = FakeRedis()
    service = McpResilienceService(redis)
    permit = service.before_call("a1", "s1", "tool")
    service.record_failure(permit)
    permit = service.before_call("a2", "s1", "tool")
    service.record_failure(permit)

    now[0] = 131.0
    probe = service.before_call("a3", "s1", "tool")
    assert probe.half_open is True
    with pytest.raises(McpCircuitOpenError, match="probe"):
        service.before_call("a4", "s1", "tool")

    service.record_success(probe)
    assert service.before_call("a5", "s1", "tool").half_open is False


def test_failed_half_open_probe_uses_exponential_backoff(monkeypatch):
    configure(monkeypatch)
    now = [100.0]
    monkeypatch.setattr(resilience_module.time, "time", lambda: now[0])
    service = McpResilienceService(FakeRedis())
    permit = service.before_call("a1", "s1", "tool")
    service.record_failure(permit)
    permit = service.before_call("a2", "s1", "tool")
    service.record_failure(permit)
    now[0] = 131.0
    probe = service.before_call("a3", "s1", "tool")
    assert service.record_failure(probe) == 60


def test_redis_failure_is_fail_open_by_default(monkeypatch):
    configure(monkeypatch)

    class BrokenRedis(FakeRedis):
        def eval(self, *args, **kwargs):
            raise RedisError("offline")

    permit = McpResilienceService(BrokenRedis()).before_call("a", "s", "tool")
    assert permit.server_id == "s"
    assert permit.half_open is False
