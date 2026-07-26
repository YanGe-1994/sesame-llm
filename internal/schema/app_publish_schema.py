#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Application publish version response schemas."""

from marshmallow import Schema, fields, pre_dump

from internal.model import AppConfigVersion


class AppConfigVersionResp(Schema):
    id = fields.UUID()
    app_id = fields.UUID()
    version = fields.Integer()
    mcp_server_count = fields.Integer()
    mcp_tool_count = fields.Integer()
    created_at = fields.Integer()

    @pre_dump
    def process_data(self, data: AppConfigVersion, **kwargs):
        bindings = data.mcp_servers or []
        return {
            "id": data.id,
            "app_id": data.app_id,
            "version": data.version,
            "mcp_server_count": len(bindings),
            "mcp_tool_count": sum(len(binding.get("enabled_tools") or []) for binding in bindings),
            "created_at": int(data.created_at.timestamp()),
        }
