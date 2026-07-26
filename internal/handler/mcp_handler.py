#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""MCP 服务接口处理器。"""

import os
from dataclasses import dataclass
from uuid import UUID

from flask import Response, request
from flask_login import current_user, login_required
from injector import inject

from internal.schema.mcp_schema import GetMcpServersWithPageReq, McpServerResp, McpToolResp, UpsertMcpServerReq
from internal.schema.mcp_audit_schema import GetMcpAuditLogsReq, McpAuditLogResp
from internal.service import McpService, McpAuditService
from internal.service.mcp_oauth_service import McpOAuthService
from pkg.paginator import PageModel
from pkg.response import success_json, success_message, validate_error_json


@inject
@dataclass
class McpHandler:
    mcp_service: McpService
    mcp_oauth_service: McpOAuthService
    mcp_audit_service: McpAuditService

    @login_required
    def get_servers_with_page(self):
        req = GetMcpServersWithPageReq(request.args)
        if not req.validate():
            return validate_error_json(req.errors)
        servers, paginator = self.mcp_service.get_servers_with_page(req, current_user)
        return success_json(PageModel(list=McpServerResp(many=True).dump(servers), paginator=paginator))

    @login_required
    def get_audit_logs_with_page(self):
        req = GetMcpAuditLogsReq(request.args)
        if not req.validate():
            return validate_error_json(req.errors)
        filters = {
            "server_id": req.server_id.data or None,
            "tool_name": req.tool_name.data or "",
            "event_type": req.event_type.data or "",
            "status": req.status.data or "",
        }
        if filters["server_id"]:
            try:
                filters["server_id"] = UUID(filters["server_id"])
            except ValueError:
                return validate_error_json({"server_id": ["MCP 服务 ID 格式不正确"]})
        logs, paginator = self.mcp_audit_service.paginate(current_user.id, req, filters)
        return success_json(PageModel(list=McpAuditLogResp(many=True).dump(logs), paginator=paginator))
    @login_required
    def create_server(self):
        req = UpsertMcpServerReq(data=request.get_json(silent=True) or {})
        if not req.validate():
            return validate_error_json(req.errors)
        server = self.mcp_service.create_server(req, current_user)
        return success_json({"id": server.id})

    @login_required
    def get_server(self, server_id: UUID):
        return success_json(McpServerResp().dump(self.mcp_service.get_server(server_id, current_user)))

    @login_required
    def update_server(self, server_id: UUID):
        req = UpsertMcpServerReq(data=request.get_json(silent=True) or {})
        if not req.validate():
            return validate_error_json(req.errors)
        server = self.mcp_service.update_server(server_id, req, current_user)
        return success_json(McpServerResp().dump(server))

    @login_required
    def delete_server(self, server_id: UUID):
        self.mcp_service.delete_server(server_id, current_user)
        return success_message("删除MCP服务成功")

    @login_required
    def get_server_tools(self, server_id: UUID):
        tools = self.mcp_service.get_server_tools(server_id, current_user)
        return success_json(McpToolResp(many=True).dump(tools))

    @login_required
    def test_connection(self, server_id: UUID):
        result = self.mcp_service.test_connection(server_id, current_user)
        return success_json(result)

    @login_required
    def sync_tools(self, server_id: UUID):
        server, tools = self.mcp_service.sync_tools(server_id, current_user)
        return success_json({
            "server": McpServerResp().dump(server),
            "tools": McpToolResp(many=True).dump(tools),
        })
    @login_required
    def begin_oauth_authorization(self, server_id: UUID):
        redirect_uri = os.getenv("MCP_OAUTH_REDIRECT_URI") or (
            request.url_root.rstrip("/") + "/mcp-servers/oauth/callback"
        )
        return success_json(self.mcp_oauth_service.begin_authorization(server_id, current_user, redirect_uri))

    def oauth_callback(self):
        error = request.args.get("error", "")
        if error:
            message = request.args.get("error_description", error)
            return Response(self._oauth_result_html(False, message), status=400, content_type="text/html; charset=utf-8")
        try:
            server = self.mcp_oauth_service.complete_authorization(
                request.args.get("state", ""), request.args.get("code", ""),
            )
            return Response(self._oauth_result_html(True, str(server.id)), content_type="text/html; charset=utf-8")
        except Exception as error:
            message = getattr(error, "message", "") or str(error) or error.__class__.__name__
            return Response(self._oauth_result_html(False, message), status=400, content_type="text/html; charset=utf-8")

    @login_required
    def disconnect_oauth(self, server_id: UUID):
        server = self.mcp_oauth_service.disconnect(server_id, current_user)
        return success_json(McpServerResp().dump(server))

    @staticmethod
    def _oauth_result_html(success: bool, message: str) -> str:
        import json
        payload = json.dumps({"type": "mcp-oauth-result", "success": success, "message": message}).replace("<", "\\u003c")
        return f"<!doctype html><meta charset='utf-8'><title>MCP OAuth</title><script>window.opener&&window.opener.postMessage({payload}, '*');window.close();</script><p>OAuth authorization completed. You can close this window.</p>"
