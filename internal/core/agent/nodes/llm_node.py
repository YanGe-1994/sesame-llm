#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
@Time   : 2026/7/17 22:17
@Author : yange19940310@gmail.com
@File   : llm_node.py
"""

import time
import uuid

from langchain_core.messages import AIMessageChunk
from langchain_core.messages import messages_to_dict

from internal.core.agent.agents.agent_queue_manager import AgentQueueManager
from internal.core.agent.entities.agent_entity import (
    AgentConfig,
    AgentState,
)
from internal.core.agent.entities.queue_entity import (
    AgentQueueEvent,
    QueueEvent,
)


class LLMNode:
    """
    LLM Node

    职责：

    1. 调用 LLM
    2. Streaming
    3. 发布 SSE
    4. 返回 AIMessage
    """

    def __init__(
        self,
        agent_config: AgentConfig,
        queue_manager: AgentQueueManager,
    ):
        self.agent_config = agent_config
        self.queue_manager = queue_manager

    def __call__(self, state: AgentState):

        start_at = time.perf_counter()

        event_id = uuid.uuid4()

        llm = self.agent_config.llm

        #
        # Bind Tools
        #
        if self.agent_config.tools:
            llm = llm.bind_tools(self.agent_config.tools)

        gathered: AIMessageChunk | None = None

        generation_type = ""

        #
        # Streaming
        #
        for chunk in llm.stream(state["messages"]):

            if gathered is None:
                gathered = chunk
            else:
                gathered += chunk

            #
            # Detect Generation Type
            #
            if not generation_type:
                if chunk.tool_calls:
                    generation_type = "tool"
                elif chunk.content:
                    generation_type = "message"

            #
            # Message Event
            #
            if generation_type == "message":

                self.queue_manager.publish(
                    AgentQueueEvent(
                        id=event_id,
                        task_id=self.queue_manager.task_id,
                        event=QueueEvent.AGENT_MESSAGE,
                        thought=chunk.content,
                        answer=chunk.content,
                        messages=messages_to_dict(state["messages"]),
                        latency=time.perf_counter() - start_at,
                    )
                )

        #
        # Tool Call Event
        #
        if generation_type == "tool":
            self.queue_manager.publish(
                AgentQueueEvent(
                    id=event_id,
                    task_id=self.queue_manager.task_id,
                    event=QueueEvent.AGENT_THOUGHT,
                    messages=messages_to_dict(state["messages"]),
                    latency=time.perf_counter() - start_at,
                )
            )

        #
        # Final Answer
        #
        if generation_type == "message":
            self.queue_manager.stop_listen()

        return {
            "messages": [gathered]
        }