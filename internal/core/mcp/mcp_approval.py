#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Redis-backed approval state for high-risk MCP tool calls."""

import json
import os
import time
import uuid
from dataclasses import dataclass
from typing import Literal
from uuid import UUID

from redis import Redis


ApprovalAction = Literal["approve_once", "approve_session", "reject"]


class McpApprovalError(RuntimeError):
    """Base MCP approval error."""


class McpApprovalRejectedError(McpApprovalError):
    """The user rejected the tool call."""


class McpApprovalTimeoutError(McpApprovalError):
    """The approval request expired."""


@dataclass
class McpApprovalRequest:
    approval_id: UUID
    account_id: UUID
    task_id: UUID
    server_id: str
    tool_name: str
    display_name: str
    arguments: dict
    risk_level: str
    status: str
    expires_at: int

    def to_dict(self) -> dict:
        return {
            "approval_id": str(self.approval_id),
            "account_id": str(self.account_id),
            "task_id": str(self.task_id),
            "server_id": self.server_id,
            "tool_name": self.tool_name,
            "display_name": self.display_name,
            "arguments": self.arguments,
            "risk_level": self.risk_level,
            "status": self.status,
            "expires_at": self.expires_at,
        }


class McpApprovalService:
    """Create, decide and wait for MCP tool approval requests."""

    def __init__(self, redis_client: Redis):
        self.redis_client = redis_client
        self.timeout_seconds = max(10, int(os.getenv("MCP_APPROVAL_TIMEOUT_SECONDS", "120")))
        self.session_ttl_seconds = max(
            self.timeout_seconds,
            int(os.getenv("MCP_APPROVAL_SESSION_TTL_SECONDS", "1800")),
        )
        self.poll_interval_seconds = max(
            0.05,
            float(os.getenv("MCP_APPROVAL_POLL_INTERVAL_SECONDS", "0.25")),
        )

    def has_session_grant(self, task_id: UUID, server_id: str, tool_name: str) -> bool:
        return bool(self.redis_client.get(self._session_key(task_id, server_id, tool_name)))

    def create_request(
            self,
            account_id: UUID,
            task_id: UUID,
            server_id: str,
            tool_name: str,
            display_name: str,
            arguments: dict,
            risk_level: str,
    ) -> McpApprovalRequest:
        approval = McpApprovalRequest(
            approval_id=uuid.uuid4(),
            account_id=account_id,
            task_id=task_id,
            server_id=server_id,
            tool_name=tool_name,
            display_name=display_name,
            arguments=arguments,
            risk_level=risk_level,
            status="pending",
            expires_at=int(time.time()) + self.timeout_seconds,
        )
        self.redis_client.setex(
            self._request_key(approval.approval_id),
            self.timeout_seconds + 60,
            json.dumps(approval.to_dict(), ensure_ascii=False, default=str),
        )
        return approval

    def decide(
            self,
            approval_id: UUID,
            account_id: UUID,
            task_id: UUID,
            action: ApprovalAction,
    ) -> dict:
        if action not in {"approve_once", "approve_session", "reject"}:
            raise McpApprovalError("不支持的审批操作")
        key = self._request_key(approval_id)
        approval = self._load(key)
        if approval is None:
            raise McpApprovalError("审批请求不存在或已过期")
        if approval["account_id"] != str(account_id) or approval["task_id"] != str(task_id):
            raise McpApprovalError("无权处理该审批请求")
        if approval.get("status") != "pending":
            raise McpApprovalError("该审批请求已处理")

        approval["status"] = action
        approval["decided_at"] = int(time.time())
        ttl = max(1, int(approval["expires_at"]) - int(time.time()) + 60)
        self.redis_client.setex(key, ttl, json.dumps(approval, ensure_ascii=False))
        if action == "approve_session":
            self.redis_client.setex(
                self._session_key(
                    task_id,
                    approval["server_id"],
                    approval["tool_name"],
                ),
                self.session_ttl_seconds,
                "1",
            )
        return approval

    def wait_for_decision(self, approval_id: UUID, is_stopped=None) -> str:
        key = self._request_key(approval_id)
        while True:
            approval = self._load(key)
            if approval is None or int(approval.get("expires_at", 0)) <= int(time.time()):
                raise McpApprovalTimeoutError("MCP 工具审批已超时")
            status = approval.get("status")
            if status in {"approve_once", "approve_session"}:
                return status
            if status == "reject":
                raise McpApprovalRejectedError("用户拒绝执行 MCP 工具")
            if is_stopped is not None and is_stopped():
                raise McpApprovalRejectedError("当前响应已停止，MCP 工具未执行")
            time.sleep(self.poll_interval_seconds)

    def _load(self, key: str) -> dict | None:
        value = self.redis_client.get(key)
        if value is None:
            return None
        if isinstance(value, bytes):
            value = value.decode("utf-8")
        return json.loads(value)

    @staticmethod
    def _request_key(approval_id: UUID) -> str:
        return f"mcp:approval:{approval_id}"

    @staticmethod
    def _session_key(task_id: UUID, server_id: str, tool_name: str) -> str:
        return f"mcp:approval:session:{task_id}:{server_id}:{tool_name}"
