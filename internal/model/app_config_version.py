#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Immutable published application configuration version."""

from sqlalchemy import Column, DateTime, Index, Integer, PrimaryKeyConstraint, UUID, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB

from internal.extension.database_extension import db


class AppConfigVersion(db.Model):
    __tablename__ = "app_config_version"
    __table_args__ = (
        PrimaryKeyConstraint("id", name="pk_app_config_version_id"),
        UniqueConstraint("app_id", "version", name="uq_app_config_version_app_version"),
        Index("idx_app_config_version_app_created", "app_id", "created_at"),
    )

    id = Column(UUID, nullable=False, server_default=text("uuid_generate_v4()"))
    app_id = Column(UUID, nullable=False)
    version = Column(Integer, nullable=False)
    config = Column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    mcp_servers = Column(JSONB, nullable=False, server_default=text("'[]'::jsonb"))
    created_at = Column(DateTime, nullable=False, server_default=text("CURRENT_TIMESTAMP(0)"))
