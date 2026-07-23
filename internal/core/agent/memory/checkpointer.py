#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
@Time   : 2026/7/17 22:10
@Author : yange19940310@gmail.com
@File   : checkpointer.py
"""
"""
Agent Checkpointer

统一管理 LangGraph Checkpointer。

开发环境：
    InMemorySaver

生产环境：
    Redis/Postgres/SQLite
"""

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.checkpoint.base import BaseCheckpointSaver


class CheckpointerFactory:
    """
    LangGraph Checkpointer Factory
    """
    inMemorySaver = InMemorySaver()

    def create(self) -> BaseCheckpointSaver:
        """
        创建 Checkpointer

        第一版：
            使用官方 InMemorySaver

        后续：
            RedisSaver
            PostgresSaver
        """
        return self.inMemorySaver