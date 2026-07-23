#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
@Time   : 2026/7/17 21:06
@Author : yange19940310@gmail.com
@File   : base_agent.py
"""
from abc import ABC, abstractmethod
from typing import Generator

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.checkpoint.memory import InMemorySaver

from internal.core.agent.entities.agent_entity import AgentConfig
from internal.core.agent.entities.queue_entity import AgentQueueEvent
from internal.core.agent.agents.agent_queue_manager import AgentQueueManager
from internal.core.agent.memory.checkpointer import CheckpointerFactory


class BaseAgent(ABC):
    """
    Agent 基类
    负责：
    1. 保存 AgentConfig
    2. 保存 QueueManager
    3. 保存 Checkpointer
    """
    def __init__(
        self,
        agent_config: AgentConfig,
        agent_queue_manager: AgentQueueManager,
        checkpointer: BaseCheckpointSaver | None = None
    ):
        self.agent_config = agent_config
        self.agent_queue_manager = agent_queue_manager

        # LangGraph Checkpointer
        #
        # 开发环境默认 InMemory
        # 后续可以替换为：
        #
        # RedisSaver
        # PostgresSaver
        #
        self.checkpointer = checkpointer or CheckpointerFactory().create()

    @abstractmethod
    def run(
        self,
        *,
        query: str,
        thread_id: str,
        long_term_memory: str = "",
    ) -> Generator[AgentQueueEvent, None, None]:
        """
        query
            用户输入
        thread_id
            会话唯一ID（LangGraph Memory Key）
        long_term_memory
            长期记忆（后续可迁移到 Store）
        """
        raise NotImplementedError