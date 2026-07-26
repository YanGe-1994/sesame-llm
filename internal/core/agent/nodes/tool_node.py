#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Agent tool execution node with MCP approval and audit support."""

import json
import time
import uuid

from langchain_core.messages import ToolMessage

from internal.core.agent.agents.agent_queue_manager import AgentQueueManager
from internal.core.agent.entities.agent_entity import AgentConfig, AgentState
from internal.core.agent.entities.queue_entity import AgentQueueEvent, QueueEvent
from internal.core.mcp.mcp_approval import (
    McpApprovalRejectedError,
    McpApprovalService,
    McpApprovalTimeoutError,
)


class ToolNode:
    def __init__(self, agent_config: AgentConfig, queue_manager: AgentQueueManager):
        self.agent_config = agent_config
        self.queue_manager = queue_manager

    def __call__(self, state: AgentState):
        tools_by_name = {tool.name: tool for tool in self.agent_config.tools}
        tool_calls = state["messages"][-1].tool_calls
        messages = []

        for tool_call in tool_calls:
            event_id = uuid.uuid4()
            start_at = time.perf_counter()
            tool = tools_by_name.get(tool_call["name"])
            metadata = (tool.metadata or {}) if tool is not None else {}
            succeeded = False
            error_message = ""
            try:
                if tool is None:
                    raise ValueError(f"工具 {tool_call['name']} 不存在或未绑定")
                if metadata.get("tool_type") == "mcp":
                    self._approve_mcp_call(tool, tool_call, metadata)
                tool_result = tool.invoke(tool_call.get("args") or {})
                tool_result_content = self._serialize_tool_result(tool_result)
                succeeded = True
            except Exception as exc:
                error_message = str(exc)
                tool_result_content = self._serialize_tool_result({
                    "success": False,
                    "error": error_message,
                    "tool": tool_call["name"],
                })

            latency = time.perf_counter() - start_at
            if metadata.get("tool_type") == "mcp":
                self._record_audit(
                    metadata,
                    event_type="tool_call",
                    status="success" if succeeded else "error",
                    request_data=tool_call.get("args") or {},
                    response_data={"result": tool_result_content} if succeeded else {},
                    error=error_message,
                    latency=int(latency * 1000),
                )

            messages.append(ToolMessage(
                tool_call_id=tool_call["id"],
                content=tool_result_content,
                name=tool_call["name"],
            ))
            if tool_call["name"] == "dataset_retrieval":
                event = QueueEvent.DATASET_RETRIEVAL
            elif metadata.get("tool_type") == "mcp":
                event = QueueEvent.MCP_TOOL_CALL
            else:
                event = QueueEvent.AGENT_ACTION
            self.queue_manager.publish(AgentQueueEvent(
                id=event_id,
                task_id=self.queue_manager.task_id,
                event=event,
                observation=tool_result_content,
                tool=metadata.get("display_name") or tool_call["name"],
                tool_input=tool_call.get("args") or {},
                metadata=self._public_metadata(metadata),
                latency=latency,
            ))
        return {"messages": messages}

    def _approve_mcp_call(self, tool, tool_call: dict, metadata: dict) -> None:
        risk_level = str(metadata.get("risk_level") or "normal").lower()
        approval_mode = str(metadata.get("approval_mode") or "auto").lower()
        binding_policy = str(metadata.get("approval_policy") or "auto").lower()
        requires_approval = (
            risk_level in {"high", "critical"}
            or approval_mode != "auto"
            or binding_policy == "always_ask"
        )
        if not requires_approval:
            return

        approval_service = McpApprovalService(self.queue_manager.redis_client)
        server_id = str(metadata.get("server_id") or "")
        remote_tool_name = str(metadata.get("remote_tool_name") or tool_call["name"])
        if approval_service.has_session_grant(
                self.queue_manager.task_id, server_id, remote_tool_name,
        ):
            return

        approval = approval_service.create_request(
            account_id=self.queue_manager.user_id,
            task_id=self.queue_manager.task_id,
            server_id=server_id,
            tool_name=remote_tool_name,
            display_name=str(metadata.get("display_name") or tool.name),
            arguments=tool_call.get("args") or {},
            risk_level=risk_level,
        )
        self._record_audit(
            metadata,
            event_type="approval_requested",
            status="pending",
            approval_id=approval.approval_id,
            request_data=approval.arguments,
        )
        self.queue_manager.publish(AgentQueueEvent(
            id=approval.approval_id,
            task_id=self.queue_manager.task_id,
            event=QueueEvent.MCP_APPROVAL_REQUIRED,
            thought="该 MCP 工具需要用户批准后才能执行",
            tool=approval.display_name,
            tool_input=approval.arguments,
            metadata={
                "approval_id": str(approval.approval_id),
                "risk_level": approval.risk_level,
                "expires_at": approval.expires_at,
                "actions": ["approve_once", "approve_session", "reject"],
            },
        ))
        try:
            approval_service.wait_for_decision(
                approval.approval_id,
                is_stopped=self.queue_manager.is_stopped,
            )
        except McpApprovalTimeoutError as error:
            self._record_audit(
                metadata,
                event_type="approval_decided",
                status="timeout",
                approval_id=approval.approval_id,
                request_data=approval.arguments,
                error=str(error),
            )
            raise
        except McpApprovalRejectedError:
            # Explicit rejection is recorded by the authenticated approval endpoint.
            raise

    def _record_audit(
            self,
            metadata: dict,
            event_type: str,
            status: str,
            approval_id=None,
            request_data=None,
            response_data=None,
            error: str = "",
            latency: int = 0,
    ) -> None:
        audit_service = metadata.get("_audit_service")
        if audit_service is None:
            return
        audit_service.record(
            account_id=self.queue_manager.user_id,
            server_id=metadata.get("server_id") or None,
            task_id=self.queue_manager.task_id,
            approval_id=approval_id,
            event_type=event_type,
            status=status,
            risk_level=metadata.get("risk_level") or "normal",
            server_name=metadata.get("server_name") or "",
            tool_name=metadata.get("remote_tool_name") or "",
            tool_display_name=metadata.get("display_name") or "",
            request_data=request_data or {},
            response_data=response_data or {},
            error=error,
            latency=latency,
        )

    @staticmethod
    def _public_metadata(metadata: dict) -> dict:
        return {key: value for key, value in metadata.items() if not key.startswith("_")}

    @staticmethod
    def _serialize_tool_result(tool_result) -> str:
        if isinstance(tool_result, str):
            return tool_result
        return json.dumps(tool_result, ensure_ascii=False, default=str)
