#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""将应用草稿绑定的 MCP 工具转换为 LangChain 工具。"""

import hashlib
import re
from dataclasses import dataclass
from uuid import UUID

from injector import inject
from langchain_core.tools import StructuredTool

from internal.core.mcp import McpAuth, McpClient
from internal.model import Account, McpServer, McpTool
from internal.service.mcp_oauth_service import McpOAuthService
from internal.service.mcp_audit_service import McpAuditService
from internal.service.mcp_resilience_service import (
    McpCircuitOpenError, McpRateLimitError, McpResilienceService,
)
from pkg.sqlalchemy import SQLAlchemy


@inject
@dataclass
class McpRuntimeService:
    db: SQLAlchemy
    mcp_client: McpClient
    mcp_oauth_service: McpOAuthService
    mcp_resilience_service: McpResilienceService

    def build_tools(self, bindings: list[dict], account: Account) -> list[StructuredTool]:
        runtime_tools = []
        runtime_names = set()
        for binding in bindings or []:
            if not isinstance(binding, dict):
                continue
            server_id = binding.get("server_id")
            enabled_names = [str(name) for name in binding.get("enabled_tools") or [] if name]
            if not server_id or not enabled_names:
                continue
            try:
                server_uuid = UUID(str(server_id))
            except (TypeError, ValueError):
                continue
            server = self.db.session.query(McpServer).filter(
                McpServer.id == server_uuid,
                McpServer.account_id == account.id,
                McpServer.status == "active",
                McpServer.transport == "streamable_http",
                McpServer.auth_type.in_(["none", "bearer", "api_key", "oauth2"]),
            ).one_or_none()
            if server is None:
                continue
            tools = self.db.session.query(McpTool).filter(
                McpTool.server_id == server.id,
                McpTool.tool_name.in_(enabled_names),
                McpTool.enabled.is_(True),
                McpTool.is_available.is_(True),
            ).all()
            tool_map = {tool.tool_name: tool for tool in tools}
            saved_versions = binding.get("tool_versions") or {}
            for tool_name in enabled_names:
                tool = tool_map.get(tool_name)
                if tool is None or saved_versions.get(tool_name) != tool.schema_hash:
                    continue
                runtime_name = self._runtime_name(str(server.id), tool.tool_name)
                if runtime_name in runtime_names:
                    continue
                runtime_tools.append(self._build_tool(
                    server, tool, runtime_name, binding.get("approval_policy") or "auto",
                ))
                runtime_names.add(runtime_name)
        return runtime_tools

    def _build_tool(
            self, server: McpServer, tool: McpTool, runtime_name: str, approval_policy: str = "auto",
    ) -> StructuredTool:
        endpoint_url = server.endpoint_url
        auth_type = server.auth_type
        encrypted_secret = server.encrypted_secret
        auth_header_name = server.auth_header_name
        server_id = server.id
        account_id = server.account_id
        server_name = server.name
        remote_tool_name = tool.tool_name
        mcp_client = self.mcp_client
        oauth_service = self.mcp_oauth_service
        resilience = self.mcp_resilience_service

        def invoke_mcp_tool(**kwargs):
            permit = None
            secret = ""
            try:
                permit = resilience.before_call(account_id, server_id, remote_tool_name)
                if auth_type == "oauth2":
                    headers, secret = oauth_service.get_authorization_headers(server_id, account_id)
                else:
                    headers, secret = McpAuth.build_headers(
                        auth_type, encrypted_secret, auth_header_name,
                    )
                result = mcp_client.call_tool(
                    endpoint_url, remote_tool_name, kwargs, headers=headers,
                )
                resilience.record_success(permit)
                return result
            except (McpRateLimitError, McpCircuitOpenError) as error:
                raise RuntimeError(str(error)) from None
            except Exception as error:
                if permit is not None:
                    resilience.record_failure(permit)
                raise RuntimeError(McpAuth.redact(error, secret)) from None

        input_schema = tool.input_schema or {"type": "object", "properties": {}}
        display_name = tool.display_name or tool.tool_name
        return StructuredTool.from_function(
            func=invoke_mcp_tool,
            name=runtime_name,
            description=f"MCP service {server_name} tool {display_name}. {tool.description or ''}",
            args_schema=input_schema,
            metadata={
                "tool_type": "mcp", "server_id": str(server_id),
                "server_name": server_name, "remote_tool_name": remote_tool_name,
                "display_name": f"{server_name} / {display_name}",
                "risk_level": getattr(tool, "risk_level", "normal") or "normal",
                "approval_mode": getattr(tool, "approval_mode", "auto") or "auto",
                "approval_policy": approval_policy,
                "_audit_service": McpAuditService(self.db),
            },
        )

    @staticmethod
    def _runtime_name(server_id: str, tool_name: str) -> str:
        safe_name = re.sub(r"[^a-zA-Z0-9_-]", "_", tool_name).strip("_") or "tool"
        suffix = hashlib.sha256(tool_name.encode("utf-8")).hexdigest()[:8]
        return f"mcp_{server_id.replace('-', '')[:8]}_{safe_name[:35]}_{suffix}"[:64]