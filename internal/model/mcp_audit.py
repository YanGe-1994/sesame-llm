#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""MCP invocation and approval audit model."""

from sqlalchemy import Column, DateTime, Index, Integer, PrimaryKeyConstraint, String, Text, UUID, text
from sqlalchemy.dialects.postgresql import JSONB

from internal.extension.database_extension import db


class McpAuditLog(db.Model):
    __tablename__ = "mcp_audit_log"
    __table_args__ = (
        PrimaryKeyConstraint("id", name="pk_mcp_audit_log_id"),
        Index("idx_mcp_audit_log_account_created", "account_id", "created_at"),
        Index("idx_mcp_audit_log_server_created", "server_id", "created_at"),
        Index("idx_mcp_audit_log_task_id", "task_id"),
        Index("idx_mcp_audit_log_event_status", "event_type", "status"),
    )

    id = Column(UUID, nullable=False, server_default=text("uuid_generate_v4()"))
    account_id = Column(UUID, nullable=False)
    server_id = Column(UUID, nullable=True)
    task_id = Column(UUID, nullable=True)
    approval_id = Column(UUID, nullable=True)
    event_type = Column(String(64), nullable=False)
    status = Column(String(32), nullable=False)
    risk_level = Column(String(32), nullable=False, server_default=text("'normal'::character varying"))
    server_name = Column(String(100), nullable=False, server_default=text("''::character varying"))
    tool_name = Column(String(255), nullable=False, server_default=text("''::character varying"))
    tool_display_name = Column(String(255), nullable=False, server_default=text("''::character varying"))
    request_data = Column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    response_data = Column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    error = Column(Text, nullable=False, server_default=text("''::text"))
    latency = Column(Integer, nullable=False, server_default=text("0"))
    created_at = Column(DateTime, nullable=False, server_default=text("CURRENT_TIMESTAMP(0)"))
