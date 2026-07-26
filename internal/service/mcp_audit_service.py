#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""MCP invocation and approval audit service."""

import json
import logging
import os
import re
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from injector import inject
from sqlalchemy import desc

from internal.model import McpAuditLog
from pkg.paginator import Paginator, PaginatorReq
from pkg.sqlalchemy import SQLAlchemy

logger = logging.getLogger(__name__)
SENSITIVE_MARKERS = (
    "authorization", "token", "secret", "password", "credential",
    "api_key", "api-key", "apikey", "access_key", "private_key", "cookie",
)


@inject
@dataclass
class McpAuditService:
    db: SQLAlchemy

    @classmethod
    def redact(cls, value: Any, depth: int = 0) -> Any:
        if depth > 8:
            return "[TRUNCATED]"
        if isinstance(value, dict):
            return {
                str(key): (
                    "[REDACTED]"
                    if any(marker in str(key).lower() for marker in SENSITIVE_MARKERS)
                    else cls.redact(item, depth + 1)
                )
                for key, item in list(value.items())[:100]
            }
        if isinstance(value, (list, tuple)):
            return [cls.redact(item, depth + 1) for item in list(value)[:100]]
        if isinstance(value, bytes):
            value = value.decode("utf-8", errors="replace")
        if isinstance(value, str):
            stripped = value.strip()
            if stripped.startswith(("{", "[")):
                try:
                    return cls.redact(json.loads(stripped), depth + 1)
                except (TypeError, ValueError):
                    pass
            value = re.sub(r"(?i)(bearer\s+)[^\s,;]+", r"\1[REDACTED]", value)
            value = re.sub(
                r"(?i)((?:api[_-]?key|token|secret|password)\s*[:=]\s*)[^\s,;]+",
                r"\1[REDACTED]",
                value,
            )
            max_length = int(os.getenv("MCP_AUDIT_MAX_FIELD_LENGTH", "4096"))
            return value if len(value) <= max_length else value[:max_length] + "…[TRUNCATED]"
        if value is None or isinstance(value, (bool, int, float)):
            return value
        return cls.redact(str(value), depth + 1)

    def record(self, **kwargs) -> None:
        """Best effort: audit storage failures never break tool execution."""
        try:
            request_data = self.redact(kwargs.pop("request_data", {}) or {})
            response_data = self.redact(kwargs.pop("response_data", {}) or {})
            error = self.redact(kwargs.pop("error", "") or "")
            with self.db.auto_commit():
                self.db.session.add(McpAuditLog(
                    request_data=request_data,
                    response_data=response_data,
                    error=error,
                    **kwargs,
                ))
        except Exception:
            self.db.session.rollback()
            logger.exception("Failed to persist MCP audit record")

    def paginate(self, account_id: UUID, req: PaginatorReq, filters: dict):
        query = self.db.session.query(McpAuditLog).filter(McpAuditLog.account_id == account_id)
        if filters.get("server_id"):
            query = query.filter(McpAuditLog.server_id == filters["server_id"])
        if filters.get("event_type"):
            query = query.filter(McpAuditLog.event_type == filters["event_type"])
        if filters.get("status"):
            query = query.filter(McpAuditLog.status == filters["status"])
        if filters.get("tool_name"):
            query = query.filter(McpAuditLog.tool_name.ilike(f"%{filters['tool_name']}%"))
        paginator = Paginator(self.db, req)
        return paginator.paginate(query.order_by(desc(McpAuditLog.created_at))), paginator
