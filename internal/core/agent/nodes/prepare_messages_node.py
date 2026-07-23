#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
@Time   : 2026/7/17 22:11
@Author : yange19940310@gmail.com
@File   : prepare_messages_node.py
"""
import uuid

from langchain_core.messages import (
    HumanMessage,
    RemoveMessage,
    SystemMessage,
)

from internal.core.agent.entities.agent_entity import (
    AgentConfig,
    AgentState,
    AGENT_SYSTEM_PROMPT_TEMPLATE,
)
from internal.core.agent.entities.queue_entity import (
    AgentQueueEvent,
    QueueEvent,
)
from internal.core.agent.agents.agent_queue_manager import AgentQueueManager


class PrepareMessagesNode:
    """
    Prepare Messages Node
    职责：

    1. 召回长期记忆
    2. 构建 System Prompt
    3. 拼接历史消息
    4. 重新组织 Messages
    输入：
        AgentState
    输出：
        {
            "messages": [...]
        }
    """

    def __init__(
        self,
        agent_config: AgentConfig,
        queue_manager: AgentQueueManager,
    ):
        self.agent_config = agent_config
        self.queue_manager = queue_manager

    def __call__(self, state: AgentState):

        #
        # Long Memory
        #
        long_term_memory = ""

        if self.agent_config.enable_long_term_memory:
            long_term_memory = state.get("long_term_memory", "")

            self.queue_manager.publish(
                AgentQueueEvent(
                    id=uuid.uuid4(),
                    task_id=self.queue_manager.task_id,
                    event=QueueEvent.LONG_TERM_MEMORY_RECALL,
                    observation=long_term_memory,
                )
            )

        #
        # Messages
        #
        messages = list(state["messages"])

        if not messages:
            return state

        #
        # Current Human Message
        #
        current_message = messages[-1]

        if not isinstance(current_message, HumanMessage):
            return state

        #
        # System Prompt
        #
        system_message = SystemMessage(
            content=AGENT_SYSTEM_PROMPT_TEMPLATE.format(
                preset_prompt=self.agent_config.preset_prompt,
                long_term_memory=long_term_memory,
            )
        )

        #
        # Build Messages
        #
        new_messages = [
            RemoveMessage(id=current_message.id),
            system_message,
            *messages[:-1],
            HumanMessage(content=current_message.content),
        ]

        return {
            "messages": new_messages
        }