#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
@Time   : 2026/7/18 17:23
@Author : yange19940310@gmail.com
@File   : tool_node.py
"""

import time
import uuid
import json

from langchain_core.messages import  ToolMessage

from internal.core.agent.agents.agent_queue_manager import AgentQueueManager
from internal.core.agent.entities.agent_entity import (
    AgentConfig,
    AgentState,
)
from internal.core.agent.entities.queue_entity import (
    AgentQueueEvent,
    QueueEvent,
)


class ToolNode:
    """
    Tool Node
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
        # Bind Tools
        #
        """工具执行节点"""
        # 1.将工具列表转换成字典，便于调用指定的工具
        tools_by_name = {tool.name: tool for tool in self.agent_config.tools}

        # 2.提取消息中的工具调用参数
        tool_calls = state["messages"][-1].tool_calls

        # 3.循环执行工具组装工具消息
        messages = []
        for tool_call in tool_calls:
            # 4.创建智能体动作事件id并记录开始时间
            id = uuid.uuid4()
            start_at = time.perf_counter()

            # 5.获取工具并调用工具
            tool = tools_by_name.get(tool_call["name"])
            try:
                if tool is None:
                    raise ValueError(f"工具 {tool_call['name']} 不存在或未绑定")
                tool_result = tool.invoke(tool_call.get("args") or {})
                tool_result_content = self._serialize_tool_result(tool_result)
            except Exception as exc:
                tool_result_content = self._serialize_tool_result({
                    "success": False,
                    "error": str(exc),
                    "tool": tool_call["name"],
                })

            # 6.将工具消息添加到消息列表中
            messages.append(ToolMessage(
                tool_call_id=tool_call["id"],
                content=tool_result_content,
                name=tool_call["name"],
            ))

            # 7.判断执行工具的名字，提交不同事件，涵盖智能体动作以及知识库检索
            event = (
                QueueEvent.AGENT_ACTION
                if tool_call["name"] != "dataset_retrieval"
                else QueueEvent.DATASET_RETRIEVAL
            )
            self.queue_manager.publish(AgentQueueEvent(
                id=id,
                task_id=self.queue_manager.task_id,
                event=event,
                observation=tool_result_content,
                tool=tool_call["name"],
                tool_input=tool_call.get("args") or {},
                latency=(time.perf_counter() - start_at),
            ))

        return {"messages": messages}

    @staticmethod
    def _serialize_tool_result(tool_result) -> str:
        if isinstance(tool_result, str):
            return tool_result
        return json.dumps(tool_result, ensure_ascii=False, default=str)
