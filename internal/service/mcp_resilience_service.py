#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Redis-backed rate limiting and circuit breaker for MCP calls."""

import hashlib
import json
import logging
import os
import time
from dataclasses import dataclass
from uuid import UUID

from injector import inject
from redis import Redis
from redis.exceptions import RedisError


logger = logging.getLogger(__name__)


class McpRateLimitError(RuntimeError):
    pass


class McpCircuitOpenError(RuntimeError):
    pass


@dataclass(frozen=True)
class McpCallPermit:
    server_id: str
    half_open: bool = False


@inject
@dataclass
class McpResilienceService:
    redis_client: Redis

    RATE_LIMIT_SCRIPT = """
    for index = 1, #KEYS do
      local current = tonumber(redis.call('GET', KEYS[index]) or '0')
      local limit = tonumber(ARGV[index])
      if limit > 0 and current >= limit then
        return index
      end
    end
    for index = 1, #KEYS do
      local value = redis.call('INCR', KEYS[index])
      if value == 1 then
        redis.call('EXPIRE', KEYS[index], tonumber(ARGV[#KEYS + 1]))
      end
    end
    return 0
    """

    def before_call(self, account_id: UUID | str, server_id: UUID | str, tool_name: str) -> McpCallPermit:
        try:
            self._check_rate_limit(str(account_id), str(server_id), tool_name)
            return self._check_circuit(str(server_id))
        except RedisError as error:
            if self._env_bool("MCP_RESILIENCE_FAIL_OPEN", True):
                logger.warning("MCP resilience Redis unavailable; call allowed without protection: %s", error)
                return McpCallPermit(server_id=str(server_id))
            raise RuntimeError("MCP protection service is temporarily unavailable") from None

    def record_success(self, permit: McpCallPermit) -> None:
        try:
            self.redis_client.delete(
                self._failure_key(permit.server_id),
                self._open_key(permit.server_id),
                self._open_count_key(permit.server_id),
                self._half_open_key(permit.server_id),
            )
        except RedisError as error:
            logger.warning("Failed to clear MCP circuit state: %s", error)

    def record_failure(self, permit: McpCallPermit) -> int:
        try:
            self.redis_client.delete(self._half_open_key(permit.server_id))
            failure_key = self._failure_key(permit.server_id)
            failures = int(self.redis_client.incr(failure_key))
            if failures == 1:
                self.redis_client.expire(failure_key, self._failure_window_seconds())
            if permit.half_open or failures >= self._failure_threshold():
                return self._open_circuit(permit.server_id)
            return 0
        except RedisError as error:
            logger.warning("Failed to update MCP circuit state: %s", error)
            return 0

    def reset_server(self, server_id: UUID | str) -> None:
        server = str(server_id)
        try:
            self.redis_client.delete(
                self._failure_key(server),
                self._open_key(server),
                self._open_count_key(server),
                self._half_open_key(server),
            )
        except RedisError as error:
            logger.warning("Failed to reset MCP circuit state: %s", error)

    def _check_rate_limit(self, account_id: str, server_id: str, tool_name: str) -> None:
        window = self._rate_window_seconds()
        bucket = int(time.time()) // window
        tool_hash = hashlib.sha256(tool_name.encode("utf-8")).hexdigest()[:16]
        keys = [
            f"mcp:rate:account:{account_id}:{bucket}",
            f"mcp:rate:server:{server_id}:{bucket}",
            f"mcp:rate:tool:{server_id}:{tool_hash}:{bucket}",
        ]
        limits = [
            self._env_int("MCP_RATE_LIMIT_ACCOUNT", 120),
            self._env_int("MCP_RATE_LIMIT_SERVER", 60),
            self._env_int("MCP_RATE_LIMIT_TOOL", 30),
        ]
        exceeded = int(self.redis_client.eval(
            self.RATE_LIMIT_SCRIPT,
            len(keys),
            *keys,
            *limits,
            window + 1,
        ))
        if exceeded:
            retry_after = window - (int(time.time()) % window)
            dimensions = ("account", "server", "tool")
            raise McpRateLimitError(
                f"MCP {dimensions[exceeded - 1]} rate limit exceeded; retry after {retry_after}s"
            )

    def _check_circuit(self, server_id: str) -> McpCallPermit:
        raw = self.redis_client.get(self._open_key(server_id))
        if not raw:
            return McpCallPermit(server_id=server_id)
        state = json.loads(raw.decode("utf-8") if isinstance(raw, bytes) else raw)
        retry_at = float(state.get("retry_at", 0))
        now = time.time()
        if now < retry_at:
            raise McpCircuitOpenError(
                f"MCP service circuit is open; retry after {max(int(retry_at - now), 1)}s"
            )
        acquired = self.redis_client.set(
            self._half_open_key(server_id),
            "1",
            nx=True,
            ex=self._half_open_timeout_seconds(),
        )
        if not acquired:
            raise McpCircuitOpenError("MCP service is recovering; a probe request is already running")
        return McpCallPermit(server_id=server_id, half_open=True)

    def _open_circuit(self, server_id: str) -> int:
        attempts = int(self.redis_client.incr(self._open_count_key(server_id)))
        maximum = self._max_backoff_seconds()
        delay = min(self._base_backoff_seconds() * (2 ** max(attempts - 1, 0)), maximum)
        self.redis_client.expire(self._open_count_key(server_id), maximum * 4)
        state = json.dumps({"retry_at": time.time() + delay, "attempt": attempts})
        self.redis_client.setex(self._open_key(server_id), self._max_backoff_seconds() * 4, state)
        return delay

    @staticmethod
    def _failure_key(server_id: str) -> str:
        return f"mcp:circuit:failures:{server_id}"

    @staticmethod
    def _open_key(server_id: str) -> str:
        return f"mcp:circuit:open:{server_id}"

    @staticmethod
    def _open_count_key(server_id: str) -> str:
        return f"mcp:circuit:open-count:{server_id}"

    @staticmethod
    def _half_open_key(server_id: str) -> str:
        return f"mcp:circuit:half-open:{server_id}"

    @classmethod
    def _rate_window_seconds(cls) -> int:
        return max(cls._env_int("MCP_RATE_LIMIT_WINDOW_SECONDS", 60), 1)

    @classmethod
    def _failure_threshold(cls) -> int:
        return max(cls._env_int("MCP_CIRCUIT_FAILURE_THRESHOLD", 5), 1)

    @classmethod
    def _failure_window_seconds(cls) -> int:
        return max(cls._env_int("MCP_CIRCUIT_FAILURE_WINDOW_SECONDS", 120), 1)

    @classmethod
    def _base_backoff_seconds(cls) -> int:
        return max(cls._env_int("MCP_CIRCUIT_BASE_BACKOFF_SECONDS", 30), 1)

    @classmethod
    def _max_backoff_seconds(cls) -> int:
        return max(cls._env_int("MCP_CIRCUIT_MAX_BACKOFF_SECONDS", 600), cls._base_backoff_seconds())

    @classmethod
    def _half_open_timeout_seconds(cls) -> int:
        return max(cls._env_int("MCP_CIRCUIT_HALF_OPEN_TIMEOUT_SECONDS", 30), 1)

    @staticmethod
    def _env_int(name: str, default: int) -> int:
        return int(os.getenv(name, str(default)))

    @staticmethod
    def _env_bool(name: str, default: bool) -> bool:
        value = os.getenv(name)
        return default if value is None else value.strip().lower() == "true"
