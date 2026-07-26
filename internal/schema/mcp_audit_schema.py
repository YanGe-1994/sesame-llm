#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""MCP audit query and response schemas."""

from flask_wtf import FlaskForm
from marshmallow import Schema, fields, pre_dump
from wtforms import SelectField, StringField
from wtforms.validators import Length, Optional

from internal.model import McpAuditLog
from pkg.paginator import PaginatorReq


class GetMcpAuditLogsReq(PaginatorReq):
    server_id = StringField("server_id", validators=[Optional(), Length(max=36)])
    tool_name = StringField("tool_name", validators=[Optional(), Length(max=255)])
    event_type = SelectField(
        "event_type",
        choices=[
            ("", "全部"),
            ("approval_requested", "请求审批"),
            ("approval_decided", "审批决定"),
            ("tool_call", "工具调用"),
        ],
        validators=[Optional()],
    )
    status = SelectField(
        "status",
        choices=[
            ("", "全部"), ("pending", "等待审批"), ("approved", "已批准"),
            ("rejected", "已拒绝"), ("timeout", "已超时"),
            ("success", "成功"), ("error", "失败"),
        ],
        validators=[Optional()],
    )


class McpAuditLogResp(Schema):
    id = fields.UUID()
    account_id = fields.UUID()
    server_id = fields.UUID(allow_none=True)
    task_id = fields.UUID(allow_none=True)
    approval_id = fields.UUID(allow_none=True)
    event_type = fields.String()
    status = fields.String()
    risk_level = fields.String()
    server_name = fields.String()
    tool_name = fields.String()
    tool_display_name = fields.String()
    request_data = fields.Dict()
    response_data = fields.Dict()
    error = fields.String()
    latency = fields.Integer()
    created_at = fields.Integer()

    @pre_dump
    def process_data(self, data: McpAuditLog, **kwargs):
        return {
            "id": data.id,
            "account_id": data.account_id,
            "server_id": data.server_id,
            "task_id": data.task_id,
            "approval_id": data.approval_id,
            "event_type": data.event_type,
            "status": data.status,
            "risk_level": data.risk_level,
            "server_name": data.server_name,
            "tool_name": data.tool_name,
            "tool_display_name": data.tool_display_name,
            "request_data": data.request_data or {},
            "response_data": data.response_data or {},
            "error": data.error,
            "latency": data.latency,
            "created_at": int(data.created_at.timestamp()),
        }
