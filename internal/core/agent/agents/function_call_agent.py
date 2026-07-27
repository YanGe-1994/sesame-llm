#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
@Time   : 2026/7/17 21:06
@Author : yange19940310@gmail.com
@File   : function_call_agent.py
"""
from typing import Generator
from uuid import UUID

from internal.core.agent.agents.base_agent import BaseAgent
from internal.core.agent.graph.builder import GraphBuilder
from internal.core.agent.agents.agent_runtime import AgentRuntime
from internal.core.agent.entities.queue_entity import AgentQueueEvent


class FunctionCallAgent(BaseAgent):
    """
    Function Call Agent
    职责：
        1. 初始化 Graph
        2. 初始化 Runtime
        3. 对外提供 run()
    """

    def __init__(
        self,
        agent_config,
        agent_queue_manager,
    ):
        super().__init__(
            agent_config=agent_config,
            agent_queue_manager=agent_queue_manager,
        )

        #
        # Build Graph（仅编译一次）
        #
        self.graph = GraphBuilder(
            agent_config=self.agent_config,
            queue_manager=self.agent_queue_manager,
            checkpointer=self.checkpointer,
        ).build()

        #
        # Runtime
        #
        self.runtime = AgentRuntime(
            graph=self.graph,
            queue_manager=self.agent_queue_manager,
        )

    def run(
        self,
        *,
        query: str,
        thread_id: str | UUID,
        long_term_memory: str = "",
    ) -> Generator[AgentQueueEvent, None, None]:
        """
        运行 Agent
        """

        #
        # 启动 Runtime
        #
        self.runtime.run(
            query=query,
            thread_id=str(thread_id),
            long_term_memory=long_term_memory,
        )

        #
        # 返回 SSE
        #
        yield from self.agent_queue_manager.listen()