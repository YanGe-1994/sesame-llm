#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
@Time   : 2026/5/12 16:15
@Author : yange19940310@gmail.com
@File   : app.py
"""
import uuid
from datetime import datetime

from openai.types.beta.threads import text
from sqlalchemy import (
    Column,
    UUID,
    String,
    Text,
    DateTime,
    PrimaryKeyConstraint,
    Index,
    text
)

from internal.extension.database_extension import db


class App(db.Model):
    """AI应用基础模型类"""
    __tablename__ = "app" # 表名
    __table_args__ = (
        PrimaryKeyConstraint("id", name="pk_app_id"), # 主键约束
        Index("idx_app_account_id", "account_id"), # 索引
    )

    id = Column(UUID, nullable=False, server_default=text("uuid_generate_v4()"))
    account_id = Column(UUID)
    name = Column(String(255), nullable=False, server_default=text("''::character varying"))
    icon = Column(String(255),  nullable=False, server_default=text("''::character varying"))
    description = Column(Text, nullable=False, server_default=text("''::text"))
    status = Column(String(255), nullable=False, server_default=text("''::character varying"))
    updated_at = Column(
        DateTime,
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP(0)"),
        server_onupdate=text("CURRENT_TIMESTAMP(0)")
    )
    created_at = Column(DateTime,  nullable=False, server_default=text("CURRENT_TIMESTAMP(0)"))