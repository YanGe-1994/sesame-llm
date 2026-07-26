#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""MCP 服务接口请求与响应 Schema。"""

from flask_wtf import FlaskForm
from marshmallow import Schema, fields, pre_dump
from wtforms import SelectField, StringField
from wtforms.validators import DataRequired, Length, Optional, URL

from internal.model import McpServer, McpTool
from pkg.paginator import PaginatorReq


class GetMcpServersWithPageReq(PaginatorReq):
    search_word = StringField("search_word", validators=[Optional(), Length(max=100)])
    status = SelectField(
        "status",
        choices=[("", "全部"), ("draft", "草稿"), ("active", "可用"), ("unavailable", "不可用"), ("disabled", "已禁用")],
        validators=[Optional()],
    )


class UpsertMcpServerReq(FlaskForm):
    name = StringField("name", validators=[DataRequired(message="MCP服务名称不能为空"), Length(min=1, max=100)])
    description = StringField("description", default="", validators=[Optional(), Length(max=2000)])
    icon = StringField("icon", default="", validators=[Optional(), Length(max=8192)])
    transport = SelectField(
        "transport",
        choices=[("streamable_http", "Streamable HTTP")],
        validators=[DataRequired(message="暂只支持Streamable HTTP")],
    )
    endpoint_url = StringField(
        "endpoint_url",
        validators=[DataRequired(message="MCP服务地址不能为空"), URL(message="MCP服务地址必须是合法URL"), Length(max=2048)],
    )
    auth_type = SelectField(
        "auth_type",
        choices=[("none", "无认证"), ("bearer", "Bearer"), ("api_key", "API Key"), ("oauth2", "OAuth 2.1")],
        validators=[DataRequired(message="认证类型不能为空")],
    )
    secret_ref = StringField("secret_ref", default="", validators=[Optional(), Length(max=8192)])
    auth_header_name = StringField("auth_header_name", default="", validators=[Optional(), Length(max=100)])
    oauth_authorization_url = StringField("oauth_authorization_url", default="", validators=[Optional(), Length(max=2048)])
    oauth_token_url = StringField("oauth_token_url", default="", validators=[Optional(), Length(max=2048)])
    oauth_client_id = StringField("oauth_client_id", default="", validators=[Optional(), Length(max=255)])
    oauth_client_secret = StringField("oauth_client_secret", default="", validators=[Optional(), Length(max=8192)])
    oauth_scopes = StringField("oauth_scopes", default="", validators=[Optional(), Length(max=2000)])
    oauth_token_endpoint_auth_method = SelectField("oauth_token_endpoint_auth_method", choices=[("none", "None"), ("client_secret_post", "client_secret_post"), ("client_secret_basic", "client_secret_basic")], default="client_secret_post", validators=[Optional()])


class McpServerResp(Schema):
    id = fields.UUID()
    name = fields.String()
    description = fields.String()
    icon = fields.String()
    transport = fields.String()
    endpoint_url = fields.String()
    auth_type = fields.String()
    has_secret = fields.Boolean()
    secret_hint = fields.String()
    auth_header_name = fields.String()
    oauth_authorization_url = fields.String()
    oauth_token_url = fields.String()
    oauth_client_id = fields.String()
    oauth_scopes = fields.List(fields.String())
    oauth_token_endpoint_auth_method = fields.String()
    oauth_authorized = fields.Boolean()
    oauth_expires_at = fields.Integer(allow_none=True)
    oauth_client_secret_hint = fields.String()
    oauth_last_error = fields.String()
    status = fields.String()
    protocol_version = fields.String()
    tool_count = fields.Integer()
    tools_hash = fields.String()
    last_error = fields.String()
    last_connected_at = fields.Integer(allow_none=True)
    created_at = fields.Integer()
    updated_at = fields.Integer()

    @pre_dump
    def process_data(self, data: McpServer, **kwargs):
        return {
            "id": data.id,
            "name": data.name,
            "description": data.description,
            "icon": data.icon,
            "transport": data.transport,
            "endpoint_url": data.endpoint_url,
            "auth_type": data.auth_type,
            "has_secret": bool(data.encrypted_secret),
            "secret_hint": data.secret_hint or "",
            "auth_header_name": data.auth_header_name or "",
            "oauth_authorization_url": data.oauth_authorization_url or "",
            "oauth_token_url": data.oauth_token_url or "",
            "oauth_client_id": data.oauth_client_id or "",
            "oauth_scopes": data.oauth_scopes or [],
            "oauth_token_endpoint_auth_method": data.oauth_token_endpoint_auth_method or "client_secret_post",
            "oauth_authorized": bool(data.encrypted_access_token),
            "oauth_expires_at": int(data.oauth_expires_at.timestamp()) if data.oauth_expires_at else None,
            "oauth_client_secret_hint": data.oauth_client_secret_hint or "",
            "oauth_last_error": data.oauth_last_error or "",
            "status": data.status,
            "protocol_version": data.protocol_version,
            "tool_count": int(data.tool_count or 0),
            "tools_hash": data.tools_hash,
            "last_error": data.last_error,
            "last_connected_at": int(data.last_connected_at.timestamp()) if data.last_connected_at else None,
            "created_at": int(data.created_at.timestamp()),
            "updated_at": int(data.updated_at.timestamp()),
        }


class McpToolResp(Schema):
    id = fields.UUID()
    server_id = fields.UUID()
    tool_name = fields.String()
    display_name = fields.String()
    description = fields.String()
    input_schema = fields.Dict()
    output_schema = fields.Dict()
    annotations = fields.Dict()
    enabled = fields.Boolean()
    is_available = fields.Boolean()
    risk_level = fields.String()
    approval_mode = fields.String()
    schema_hash = fields.String()
    last_synced_at = fields.Integer(allow_none=True)

    @pre_dump
    def process_data(self, data: McpTool, **kwargs):
        return {
            "id": data.id,
            "server_id": data.server_id,
            "tool_name": data.tool_name,
            "display_name": data.display_name or data.tool_name,
            "description": data.description,
            "input_schema": data.input_schema or {},
            "output_schema": data.output_schema or {},
            "annotations": data.annotations or {},
            "enabled": data.enabled,
            "is_available": data.is_available,
            "risk_level": data.risk_level,
            "approval_mode": data.approval_mode,
            "schema_hash": data.schema_hash,
            "last_synced_at": int(data.last_synced_at.timestamp()) if data.last_synced_at else None,
        }