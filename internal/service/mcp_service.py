#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""MCP 服务管理、连接测试与工具同步。"""

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from urllib.parse import urlparse
from uuid import UUID

from injector import inject
from sqlalchemy import desc

from internal.core.mcp import McpAuth, McpClient, McpInspectionResult
from internal.core.security import CredentialCipher, OutboundSecurityPolicy
from internal.exception import FailException, NotFoundException, ValidateErrorException
from internal.model import Account, McpServer, McpTool
from internal.schema.mcp_schema import GetMcpServersWithPageReq, UpsertMcpServerReq
from pkg.paginator import Paginator
from pkg.sqlalchemy import SQLAlchemy
from .base_service import BaseService
from .mcp_oauth_service import McpOAuthService
from .mcp_resilience_service import McpResilienceService


@inject
@dataclass
class McpService(BaseService):
    db: SQLAlchemy
    mcp_client: McpClient
    mcp_oauth_service: McpOAuthService
    mcp_resilience_service: McpResilienceService

    def get_servers_with_page(self, req: GetMcpServersWithPageReq, account: Account):
        filters = [McpServer.account_id == account.id]
        if req.search_word.data:
            filters.append(McpServer.name.ilike(f"%{req.search_word.data}%"))
        if req.status.data:
            filters.append(McpServer.status == req.status.data)
        paginator = Paginator(db=self.db, req=req)
        servers = paginator.paginate(
            self.db.session.query(McpServer).filter(*filters).order_by(desc(McpServer.created_at))
        )
        return servers, paginator

    def create_server(self, req: UpsertMcpServerReq, account: Account) -> McpServer:
        OutboundSecurityPolicy.from_env().validate_url(req.endpoint_url.data.strip())
        self._ensure_unique_name(account.id, req.name.data)
        encrypted_secret, secret_hint = self._prepare_credentials(
            req.auth_type.data,
            req.secret_ref.data or "",
        )
        return self.create(
            McpServer,
            account_id=account.id,
            name=req.name.data.strip(),
            description=req.description.data or "",
            icon=req.icon.data or "",
            transport=req.transport.data,
            endpoint_url=req.endpoint_url.data.strip(),
            auth_type=req.auth_type.data,
            secret_ref="",
            encrypted_secret=encrypted_secret,
            secret_hint=secret_hint,
            auth_header_name=self._normalize_auth_header_name(req.auth_type.data, req.auth_header_name.data),
            **self._oauth_values(req),
            status="draft",
        )

    def get_server(self, server_id: UUID, account: Account) -> McpServer:
        server = self.db.session.query(McpServer).filter(
            McpServer.id == server_id,
            McpServer.account_id == account.id,
        ).one_or_none()
        if server is None:
            raise NotFoundException("MCP服务不存在")
        return server

    def update_server(self, server_id: UUID, req: UpsertMcpServerReq, account: Account) -> McpServer:
        server = self.get_server(server_id, account)
        OutboundSecurityPolicy.from_env().validate_url(req.endpoint_url.data.strip())
        self._ensure_unique_name(account.id, req.name.data, server_id)
        values = {
            "name": req.name.data.strip(),
            "description": req.description.data or "",
            "icon": req.icon.data or "",
            "transport": req.transport.data,
            "endpoint_url": req.endpoint_url.data.strip(),
            "auth_type": req.auth_type.data,
            "auth_header_name": self._normalize_auth_header_name(
                req.auth_type.data,
                req.auth_header_name.data,
            ),
            "status": "draft",
            "protocol_version": "",
            "tools_hash": "",
            "last_error": "",
            "last_connected_at": None,
        }
        values.update(self._oauth_values(req, server))
        if req.auth_type.data == "oauth2":
            values.update(secret_ref="", encrypted_secret="", secret_hint="")
        if req.auth_type.data == "none":
            values.update(secret_ref="", encrypted_secret="", secret_hint="")
        elif req.auth_type.data in {"bearer", "api_key"} and req.secret_ref.data:
            values.update(
                secret_ref="",
                encrypted_secret=CredentialCipher.encrypt(req.secret_ref.data),
                secret_hint=CredentialCipher.hint(req.secret_ref.data),
            )
        elif req.auth_type.data in {"bearer", "api_key"} and not server.encrypted_secret:
            raise ValidateErrorException("该认证方式必须配置凭据")
        updated = self.update(server, **values)
        self.mcp_resilience_service.reset_server(server.id)
        return updated

    def delete_server(self, server_id: UUID, account: Account) -> None:
        server = self.get_server(server_id, account)
        with self.db.auto_commit():
            self.db.session.query(McpTool).filter(McpTool.server_id == server.id).delete()
            self.db.session.delete(server)
        self.mcp_resilience_service.reset_server(server.id)

    def get_server_tools(self, server_id: UUID, account: Account) -> list[McpTool]:
        server = self.get_server(server_id, account)
        return self.db.session.query(McpTool).filter(McpTool.server_id == server.id).order_by(McpTool.tool_name).all()

    def test_connection(self, server_id: UUID, account: Account) -> dict:
        server = self.get_server(server_id, account)
        result = self._inspect_server(server)
        self.update(
            server,
            status="active",
            protocol_version=result.protocol_version,
            tool_count=len(result.tools),
            last_error="",
            last_connected_at=datetime.now(),
        )
        return self._inspection_response(result)

    def sync_tools(self, server_id: UUID, account: Account) -> tuple[McpServer, list[McpTool]]:
        server = self.get_server(server_id, account)
        result = self._inspect_server(server)
        synchronized_at = datetime.now()
        tools_hash = self._calculate_tools_hash(result.tools)

        with self.db.auto_commit():
            existing_tools = {
                tool.tool_name: tool
                for tool in self.db.session.query(McpTool).filter(McpTool.server_id == server.id).all()
            }
            for tool in existing_tools.values():
                tool.is_available = False

            for raw_tool in result.tools:
                tool_name = raw_tool["name"]
                input_schema = raw_tool.get("inputSchema") or {}
                output_schema = raw_tool.get("outputSchema") or {}
                annotations = raw_tool.get("annotations") or {}
                schema_hash = self._calculate_schema_hash(raw_tool)
                tool = existing_tools.get(tool_name)
                if tool is None:
                    is_destructive = annotations.get("destructiveHint") is True
                    tool = McpTool(
                        server_id=server.id,
                        tool_name=tool_name,
                        risk_level="high" if is_destructive else "normal",
                        approval_mode="once" if is_destructive else "auto",
                    )
                    self.db.session.add(tool)
                tool.display_name = raw_tool.get("title") or tool_name
                tool.description = raw_tool.get("description") or ""
                tool.input_schema = input_schema
                tool.output_schema = output_schema
                tool.annotations = annotations
                tool.schema_hash = schema_hash
                tool.is_available = True
                tool.last_synced_at = synchronized_at

            server.status = "active"
            server.protocol_version = result.protocol_version
            server.tool_count = len(result.tools)
            server.tools_hash = tools_hash
            server.last_error = ""
            server.last_connected_at = synchronized_at

        tools = self.db.session.query(McpTool).filter(McpTool.server_id == server.id).order_by(McpTool.tool_name).all()
        return server, tools

    def _inspect_server(self, server: McpServer) -> McpInspectionResult:
        self._validate_connection_config(server)
        permit = self.mcp_resilience_service.before_call(server.account_id, server.id, "__inspect__")
        secret = ""
        try:
            if server.auth_type == "oauth2":
                headers, secret = self.mcp_oauth_service.get_authorization_headers(server.id, server.account_id)
            else:
                headers, secret = McpAuth.build_headers(
                    server.auth_type, server.encrypted_secret, server.auth_header_name,
                )
            result = self.mcp_client.inspect(server.endpoint_url, headers=headers)
            self.mcp_resilience_service.record_success(permit)
            return result
        except Exception as error:
            self.mcp_resilience_service.record_failure(permit)
            message = McpAuth.redact(self._format_connection_error(error), secret)
            self.update(server, status="unavailable", last_error=message)
            raise FailException(f"MCP service connection failed: {message}") from None

    @staticmethod
    def _validate_connection_config(server: McpServer) -> None:
        parsed = urlparse(server.endpoint_url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValidateErrorException("MCP服务地址仅支持合法的HTTP/HTTPS URL")
        if server.transport != "streamable_http":
            raise ValidateErrorException("当前仅支持Streamable HTTP传输")
        if server.auth_type not in {"none", "bearer", "api_key", "oauth2"}:
            raise ValidateErrorException("当前仅支持无认证、Bearer Token和API Key")
        if server.auth_type in {"bearer", "api_key"} and not server.encrypted_secret:
            raise ValidateErrorException("MCP服务尚未配置认证凭据")

    @classmethod
    def _calculate_tools_hash(cls, tools: list[dict]) -> str:
        normalized = sorted(tools, key=lambda item: item.get("name", ""))
        return hashlib.sha256(cls._canonical_json(normalized).encode("utf-8")).hexdigest()

    @classmethod
    def _calculate_schema_hash(cls, tool: dict) -> str:
        schema = {
            "name": tool.get("name"),
            "inputSchema": tool.get("inputSchema") or {},
            "outputSchema": tool.get("outputSchema") or {},
        }
        return hashlib.sha256(cls._canonical_json(schema).encode("utf-8")).hexdigest()

    @staticmethod
    def _canonical_json(data) -> str:
        return json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":"))

    @staticmethod
    def _format_connection_error(error: Exception) -> str:
        current = error
        while isinstance(current, BaseExceptionGroup) and current.exceptions:
            current = current.exceptions[0]
        message = str(current).strip() or current.__class__.__name__
        return message[:2000]

    @staticmethod
    def _inspection_response(result: McpInspectionResult) -> dict:
        return {
            "protocol_version": result.protocol_version,
            "server_name": result.server_name,
            "server_version": result.server_version,
            "tool_count": len(result.tools),
        }

    @staticmethod
    def _normalize_auth_header_name(auth_type: str, header_name: str) -> str:
        if auth_type != "api_key":
            return ""
        return McpAuth.normalize_api_key_header(header_name)

    @staticmethod
    def _prepare_credentials(auth_type: str, secret: str) -> tuple[str, str]:
        if auth_type == "none":
            return "", ""
        if auth_type == "oauth2":
            return "", ""
        if not secret:
            raise ValidateErrorException("Bearer Token或API Key不能为空")
        return CredentialCipher.encrypt(secret), CredentialCipher.hint(secret)

    @staticmethod
    def _oauth_values(req: UpsertMcpServerReq, server: McpServer | None = None) -> dict:
        if req.auth_type.data != "oauth2":
            return {
                "oauth_authorization_url": "", "oauth_token_url": "", "oauth_client_id": "",
                "encrypted_oauth_client_secret": "", "oauth_client_secret_hint": "", "oauth_scopes": [],
                "oauth_token_endpoint_auth_method": "client_secret_post", "encrypted_access_token": "",
                "encrypted_refresh_token": "", "oauth_expires_at": None, "oauth_authorized_at": None,
            }
        authorization_url = (req.oauth_authorization_url.data or "").strip()
        token_url = (req.oauth_token_url.data or "").strip()
        client_id = (req.oauth_client_id.data or "").strip()
        if not authorization_url or not token_url or not client_id:
            raise ValidateErrorException("OAuth authorization URL, token URL and client_id are required")
        policy = OutboundSecurityPolicy.from_env()
        policy.validate_url(authorization_url)
        policy.validate_url(token_url)
        client_secret = req.oauth_client_secret.data or ""
        encrypted_secret = CredentialCipher.encrypt(client_secret) if client_secret else (server.encrypted_oauth_client_secret if server else "")
        secret_hint = CredentialCipher.hint(client_secret) if client_secret else (server.oauth_client_secret_hint if server else "")
        scopes = [item for item in (req.oauth_scopes.data or "").replace(",", " ").split() if item]
        return {
            "oauth_authorization_url": authorization_url, "oauth_token_url": token_url,
            "oauth_client_id": client_id, "encrypted_oauth_client_secret": encrypted_secret,
            "oauth_client_secret_hint": secret_hint, "oauth_scopes": scopes,
            "oauth_token_endpoint_auth_method": req.oauth_token_endpoint_auth_method.data or "client_secret_post",
        }

    def _ensure_unique_name(self, account_id: UUID, name: str, exclude_id: UUID | None = None) -> None:
        query = self.db.session.query(McpServer).filter(
            McpServer.account_id == account_id,
            McpServer.name == name.strip(),
        )
        if exclude_id is not None:
            query = query.filter(McpServer.id != exclude_id)
        if query.one_or_none() is not None:
            raise ValidateErrorException("MCP服务名称已存在")