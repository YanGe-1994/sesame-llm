#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""MCP Streamable HTTP 客户端。"""

from dataclasses import dataclass, field
from datetime import timedelta
from typing import Any

import anyio
import httpx
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

from internal.core.security import SafeAsyncTransport


@dataclass
class McpInspectionResult:
    protocol_version: str
    server_name: str
    server_version: str
    session_id: str | None
    tools: list[dict[str, Any]] = field(default_factory=list)


class McpClient:
    """短生命周期 MCP 客户端，用于连接测试与工具目录同步。"""

    connect_timeout_seconds = 10
    read_timeout_seconds = 30
    max_tools = 500

    def inspect(self, endpoint_url: str, headers: dict[str, str] | None = None) -> McpInspectionResult:
        return anyio.run(self._inspect, endpoint_url, headers or {})

    async def _inspect(self, endpoint_url: str, headers: dict[str, str]) -> McpInspectionResult:
        timeout = httpx.Timeout(
            connect=self.connect_timeout_seconds,
            read=self.read_timeout_seconds,
            write=self.read_timeout_seconds,
            pool=self.connect_timeout_seconds,
        )
        async with httpx.AsyncClient(
            timeout=timeout,
            follow_redirects=False,
            headers=headers,
            transport=SafeAsyncTransport(),
        ) as http_client:
            async with streamable_http_client(
                endpoint_url,
                http_client=http_client,
                terminate_on_close=True,
            ) as (read_stream, write_stream, get_session_id):
                async with ClientSession(
                    read_stream,
                    write_stream,
                    read_timeout_seconds=timedelta(seconds=self.read_timeout_seconds),
                ) as session:
                    initialize_result = await session.initialize()
                    tools: list[dict[str, Any]] = []
                    cursor = None
                    while True:
                        result = await session.list_tools(cursor=cursor)
                        tools.extend(tool.model_dump(by_alias=True, mode="json") for tool in result.tools)
                        if len(tools) > self.max_tools:
                            raise ValueError(f"MCP工具数量超过上限{self.max_tools}")
                        cursor = result.nextCursor
                        if not cursor:
                            break
                    server_info = initialize_result.serverInfo
                    return McpInspectionResult(
                        protocol_version=initialize_result.protocolVersion,
                        server_name=server_info.name,
                        server_version=server_info.version,
                        session_id=get_session_id(),
                        tools=tools,
                    )
    def call_tool(
            self,
            endpoint_url: str,
            tool_name: str,
            arguments: dict[str, Any],
            headers: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        """建立短生命周期会话并执行 MCP tools/call。"""
        return anyio.run(self._call_tool, endpoint_url, tool_name, arguments, headers or {})

    async def _call_tool(
            self,
            endpoint_url: str,
            tool_name: str,
            arguments: dict[str, Any],
            headers: dict[str, str],
    ) -> dict[str, Any]:
        timeout = httpx.Timeout(
            connect=self.connect_timeout_seconds,
            read=self.read_timeout_seconds,
            write=self.read_timeout_seconds,
            pool=self.connect_timeout_seconds,
        )
        async with httpx.AsyncClient(
            timeout=timeout,
            follow_redirects=False,
            headers=headers,
            transport=SafeAsyncTransport(),
        ) as http_client:
            async with streamable_http_client(
                endpoint_url,
                http_client=http_client,
                terminate_on_close=True,
            ) as (read_stream, write_stream, _):
                async with ClientSession(
                    read_stream,
                    write_stream,
                    read_timeout_seconds=timedelta(seconds=self.read_timeout_seconds),
                ) as session:
                    await session.initialize()
                    result = await session.call_tool(
                        tool_name,
                        arguments=arguments,
                        read_timeout_seconds=timedelta(seconds=self.read_timeout_seconds),
                    )
                    payload = result.model_dump(by_alias=True, mode="json")
                    if result.isError:
                        error_text = self._extract_error_text(payload)
                        raise RuntimeError(error_text or f"MCP工具 {tool_name} 执行失败")
                    return {
                        "success": True,
                        "content": payload.get("content") or [],
                        "structured_content": payload.get("structuredContent"),
                    }

    @staticmethod
    def _extract_error_text(payload: dict[str, Any]) -> str:
        texts = []
        for content in payload.get("content") or []:
            if isinstance(content, dict) and content.get("type") == "text" and content.get("text"):
                texts.append(str(content["text"]))
        return "\n".join(texts)
