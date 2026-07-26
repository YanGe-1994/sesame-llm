#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""MCP 服务与工具目录模型。"""

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Index,
    Integer,
    PrimaryKeyConstraint,
    String,
    Text,
    UniqueConstraint,
    UUID,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB

from internal.extension.database_extension import db


class McpServer(db.Model):
    """账号级 MCP 服务连接配置。"""

    __tablename__ = "mcp_server"
    __table_args__ = (
        PrimaryKeyConstraint("id", name="pk_mcp_server_id"),
        UniqueConstraint("account_id", "name", name="uq_mcp_server_account_name"),
        Index("idx_mcp_server_account_id", "account_id"),
        Index("idx_mcp_server_status", "status"),
    )

    id = Column(UUID, nullable=False, server_default=text("uuid_generate_v4()"))
    account_id = Column(UUID, nullable=False)
    name = Column(String(100), nullable=False)
    description = Column(Text, nullable=False, server_default=text("''::text"))
    icon = Column(String(255), nullable=False, server_default=text("''::character varying"))
    transport = Column(String(32), nullable=False, server_default=text("'streamable_http'::character varying"))
    endpoint_url = Column(String(2048), nullable=False)
    auth_type = Column(String(32), nullable=False, server_default=text("'none'::character varying"))
    secret_ref = Column(String(255), nullable=False, server_default=text("''::character varying"))
    encrypted_secret = Column(Text, nullable=False, server_default=text("''::text"))
    secret_hint = Column(String(32), nullable=False, server_default=text("''::character varying"))
    auth_header_name = Column(String(100), nullable=False, server_default=text("''::character varying"))
    oauth_authorization_url = Column(String(2048), nullable=False, server_default=text("''::character varying"))
    oauth_token_url = Column(String(2048), nullable=False, server_default=text("''::character varying"))
    oauth_client_id = Column(String(255), nullable=False, server_default=text("''::character varying"))
    encrypted_oauth_client_secret = Column(Text, nullable=False, server_default=text("''::text"))
    oauth_client_secret_hint = Column(String(32), nullable=False, server_default=text("''::character varying"))
    oauth_scopes = Column(JSONB, nullable=False, server_default=text("'[]'::jsonb"))
    oauth_token_endpoint_auth_method = Column(String(32), nullable=False, server_default=text("'client_secret_post'::character varying"))
    encrypted_access_token = Column(Text, nullable=False, server_default=text("''::text"))
    encrypted_refresh_token = Column(Text, nullable=False, server_default=text("''::text"))
    oauth_token_type = Column(String(32), nullable=False, server_default=text("'Bearer'::character varying"))
    oauth_expires_at = Column(DateTime, nullable=True)
    oauth_granted_scopes = Column(JSONB, nullable=False, server_default=text("'[]'::jsonb"))
    oauth_authorized_at = Column(DateTime, nullable=True)
    oauth_last_error = Column(Text, nullable=False, server_default=text("''::text"))
    status = Column(String(32), nullable=False, server_default=text("'draft'::character varying"))
    protocol_version = Column(String(64), nullable=False, server_default=text("''::character varying"))
    tool_count = Column(Integer, nullable=False, server_default=text("0"))
    tools_hash = Column(String(128), nullable=False, server_default=text("''::character varying"))
    last_error = Column(Text, nullable=False, server_default=text("''::text"))
    last_connected_at = Column(DateTime, nullable=True)
    updated_at = Column(DateTime, nullable=False, server_default=text("CURRENT_TIMESTAMP(0)"), server_onupdate=text("CURRENT_TIMESTAMP(0)"))
    created_at = Column(DateTime, nullable=False, server_default=text("CURRENT_TIMESTAMP(0)"))


class McpTool(db.Model):
    """从 MCP 服务同步的工具目录缓存。"""

    __tablename__ = "mcp_tool"
    __table_args__ = (
        PrimaryKeyConstraint("id", name="pk_mcp_tool_id"),
        UniqueConstraint("server_id", "tool_name", name="uq_mcp_tool_server_name"),
        Index("idx_mcp_tool_server_id", "server_id"),
    )

    id = Column(UUID, nullable=False, server_default=text("uuid_generate_v4()"))
    server_id = Column(UUID, nullable=False)
    tool_name = Column(String(255), nullable=False)
    display_name = Column(String(255), nullable=False, server_default=text("''::character varying"))
    description = Column(Text, nullable=False, server_default=text("''::text"))
    input_schema = Column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    output_schema = Column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    annotations = Column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    enabled = Column(Boolean, nullable=False, server_default=text("true"))
    is_available = Column(Boolean, nullable=False, server_default=text("true"))
    risk_level = Column(String(32), nullable=False, server_default=text("'normal'::character varying"))
    approval_mode = Column(String(32), nullable=False, server_default=text("'auto'::character varying"))
    schema_hash = Column(String(128), nullable=False, server_default=text("''::character varying"))
    last_synced_at = Column(DateTime, nullable=True)
    updated_at = Column(DateTime, nullable=False, server_default=text("CURRENT_TIMESTAMP(0)"), server_onupdate=text("CURRENT_TIMESTAMP(0)"))
    created_at = Column(DateTime, nullable=False, server_default=text("CURRENT_TIMESTAMP(0)"))