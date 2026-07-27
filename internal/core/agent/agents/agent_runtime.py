#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
@Time   : 2026/7/17 22:21
@Author : yange19940310@gmail.com
@File   : agent_runtime.py
"""
from __future__ import annotations

import threading
from typing import Any
from uuid import UUID

from langchain_core.messages import HumanMessage
from flask import copy_current_request_context, has_request_context
from langgraph.graph.state import CompiledStateGraph

from internal.core.agent.agents.agent_queue_manager import AgentQueueManager


class AgentRuntime:
    """
    Agent Runtime

    职责：

    1. 运行 LangGraph
    2. 管理 Thread
    3. 管理 thread_id
    4. Graph 生命周期
    """

    def __init__(
        self,
        *,
        graph: CompiledStateGraph,
        queue_manager: AgentQueueManager,
    ):
        self.graph = graph
        self.queue_manager = queue_manager

    def run(
        self,
        *,
        query: str,
        thread_id: str | UUID,
        long_term_memory: str = "",
    ) -> None:
        """
        异步运行 Graph
        """
        invoke_target = self._invoke
        if has_request_context():
            invoke_target = copy_current_request_context(self._invoke)

        worker = threading.Thread(
            target=invoke_target,
            kwargs={
                "query": query,
                "thread_id": thread_id,
                "long_term_memory": long_term_memory,
            },
            daemon=True,
        )

        worker.start()

    def _invoke(
        self,
        *,
        query: str,
        thread_id: str,
        long_term_memory: str,
    ) -> None:
        """
        Graph 真正执行入口
        """
        try:
            self.graph.invoke(
                {
                    "messages": [
                        HumanMessage(content=query)
                    ],
                    "long_term_memory": long_term_memory,
                },
                config={
                    "configurable": {
                        "thread_id": thread_id,
                    }
                },
            )

        except Exception as e:
            self.queue_manager.publish_error(e)
        finally:
            #
            # Graph 已结束
            #
            self.queue_manager.stop_listen()