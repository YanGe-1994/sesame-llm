#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
@Time   : 2026/5/12 09:57
@Author : yange19940310@gmail.com
@File   : app_handler.py
"""

import json
import inspect
import os
import threading
import uuid
from dataclasses import dataclass
from typing import Generator
from uuid import UUID

from injector import inject
from langchain_core.documents import Document
from langchain_core.tools import StructuredTool
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field
from redis import Redis

from flask import current_app, request
from flask_login import current_user, login_required

from internal.core.agent.agents import FunctionCallAgent, AgentQueueManager
from internal.core.agent.entities.agent_entity import AgentConfig
from internal.core.agent.entities.queue_entity import QueueEvent
from internal.core.tools.api_tools.entities import ToolEntity
from internal.core.tools.builtin_tools.providers import BuiltinProviderManager
from internal.entity.conversation_entity import InvokeFrom, MessageStatus
from internal.entity.dataset_entity import RetrievalSource, RetrievalStrategy
from internal.schema.app_schema import (
    CompletionReq,
    CreateAppReq,
    GetAppResp,
    GetAppsWithPageReq,
    GetAppsWithPageResp,
    GetDraftAppConfigResp,
    UpdateAppReq,
    UpdateDraftAppConfigReq,
    UpdateDebugConversationSummaryReq,
    GetDebugConversationMessagesWithPageReq,
    DebugConversationMessageResp,
)
from internal.service import (
    AppService, VectorDatabaseService, ApiToolService, EmbeddingsService,
    ConversationService, RetrievalService,
)
from pkg.paginator import PageModel
from pkg.response import success_json, validate_error_json, success_message, compact_generate_response


class DatasetRetrievalInput(BaseModel):
    """应用知识库检索工具输入。"""
    query: str = Field(..., description="需要从应用已绑定知识库中检索的问题或关键词")


@inject
@dataclass
class AppHandler:
    """应用控制器"""
    app_service: AppService
    vector_database_service: VectorDatabaseService
    api_tool_service: ApiToolService
    embeddings_service: EmbeddingsService
    builtin_provider_manager: BuiltinProviderManager
    conversation_service: ConversationService
    retrieval_service: RetrievalService
    redis_client: Redis

    @login_required
    def create_app(self):
        req = CreateAppReq(data=request.get_json(silent=True) or {})
        if not req.validate():
            return validate_error_json(req.errors)
        app = self.app_service.create_app(req, current_user)
        return success_json({"id": app.id})

    @login_required
    def get_app(self, app_id: uuid.UUID):
        app = self.app_service.get_app(app_id, current_user)
        return success_json(GetAppResp().dump(app))

    @login_required
    def update_app(self, app_id: uuid.UUID):
        req = UpdateAppReq(data=request.get_json(silent=True) or {})
        if not req.validate():
            return validate_error_json(req.errors)
        app = self.app_service.update_app(app_id, req, current_user)
        return success_json(GetAppResp().dump(app))

    @login_required
    def delete_app(self, app_id: uuid.UUID):
        app = self.app_service.delete_app(app_id, current_user)
        return success_message(f"应用已经成功删除，id为:{app.id}")

    @login_required
    def get_apps_with_page(self):
        req = GetAppsWithPageReq()
        if not req.validate():
            return validate_error_json(req.errors)
        apps, paginator = self.app_service.get_apps_with_page(req, current_user)
        resp = GetAppsWithPageResp(many=True)
        return success_json(PageModel(list=resp.dump(apps), paginator=paginator))

    @login_required
    def get_draft_app_config(self, app_id: uuid.UUID):
        draft_app_config = self.app_service.get_draft_app_config(app_id, current_user)
        return success_json(GetDraftAppConfigResp().dump(draft_app_config))

    @login_required
    def update_draft_app_config(self, app_id: uuid.UUID):
        request_data = request.get_json(silent=True) or {}
        req = UpdateDraftAppConfigReq(data=request_data)
        if not req.validate():
            return validate_error_json(req.errors)
        draft_app_config = self.app_service.update_draft_app_config(
            app_id,
            req,
            current_user,
            submitted_fields=set(request_data.keys()),
        )
        return success_json(GetDraftAppConfigResp().dump(draft_app_config))

    @login_required
    def get_debug_conversation_summary(self, app_id: uuid.UUID):
        self.app_service.get_app(app_id, current_user)
        summary = self.conversation_service.get_debug_summary(app_id, current_user)
        return success_json({"summary": summary})

    @login_required
    def update_debug_conversation_summary(self, app_id: uuid.UUID):
        req = UpdateDebugConversationSummaryReq(data=request.get_json(silent=True) or {})
        if not req.validate():
            return validate_error_json(req.errors)
        self.app_service.get_app(app_id, current_user)
        self.conversation_service.update_debug_summary(app_id, current_user, req.summary.data or "")
        return success_message("长期记忆已保存")

    @login_required
    def get_debug_conversation_messages_with_page(self, app_id: uuid.UUID):
        req = GetDebugConversationMessagesWithPageReq()
        if not req.validate():
            return validate_error_json(req.errors)
        self.app_service.get_app(app_id, current_user)
        messages, paginator = self.conversation_service.paginate_debug_messages(app_id, current_user, req)
        resp = DebugConversationMessageResp(many=True)
        return success_json(PageModel(list=resp.dump(messages), paginator=paginator))

    @login_required
    def delete_debug_conversation(self, app_id: uuid.UUID):
        self.app_service.get_app(app_id, current_user)
        self.conversation_service.clear_debug_conversation(app_id, current_user)
        return success_message("调试会话已清空")

    @login_required
    def stop_debug_chat(self, app_id: uuid.UUID, task_id: UUID):
        self.app_service.get_app(app_id, current_user)
        task_belong_cache_key = AgentQueueManager.generate_task_belong_cache_key(task_id)
        task_belong = self.redis_client.get(task_belong_cache_key)
        if isinstance(task_belong, bytes):
            task_belong = task_belong.decode()
        expected_belong = f"account-{str(current_user.id)}"
        if task_belong == expected_belong:
            self.redis_client.setex(AgentQueueManager.generate_task_stopped_cache_key(task_id), 1800, 1)
        return success_message("调试任务已停止")

    @login_required
    def publish(self, app_id: uuid.UUID):
        self.app_service.get_app(app_id, current_user)
        return success_message("发布能力将在后续阶段实现")

    @login_required
    def cancel_publish(self, app_id: uuid.UUID):
        self.app_service.get_app(app_id, current_user)
        return success_message("取消发布能力将在后续阶段实现")

    @login_required
    def get_publish_histories_with_page(self, app_id: uuid.UUID):
        self.app_service.get_app(app_id, current_user)
        return success_json(PageModel(list=[], paginator={
            "total_page": 0,
            "total_record": 0,
            "current_page": 1,
            "page_size": 20,
        }))

    @login_required
    def fallback_history_to_draft(self, app_id: uuid.UUID):
        self.app_service.get_app(app_id, current_user)
        return success_message("版本回退能力将在后续阶段实现")

    @login_required
    def debug(self, app_id: UUID):
        req = CompletionReq(data=request.get_json(silent=True) or {})
        if not req.validate():
            return validate_error_json(req.errors)

        draft_app_config = self.app_service.get_draft_app_config(app_id, current_user)
        debug_conversation = self.conversation_service.get_or_create_debug_conversation(app_id, current_user)
        debug_message = self.conversation_service.create_debug_message(
            debug_conversation,
            req.query.data,
            current_user,
        )
        debug_conversation_id = debug_conversation.id
        debug_conversation_summary = debug_conversation.summary or ""
        debug_message_id = debug_message.id
        debug_conversation_id_text = str(debug_conversation_id)
        debug_message_id_text = str(debug_message_id)
        flask_app = current_app._get_current_object()
        long_term_memory_enabled = (draft_app_config.long_term_memory or {}).get("enable", False)
        model_config = draft_app_config.model_config or {}
        model_parameters = model_config.get("parameters") or {}
        model_name = os.getenv("DASHSCOPE_MODEL") or "glm-5.2"
        tools = self._build_debug_tools(draft_app_config.tools or [], current_user)
        dataset_retrieval_tool = self._build_dataset_retrieval_tool(
            app_id,
            draft_app_config.datasets or [],
            draft_app_config.retrieval_config or {},
            current_user,
        )
        if dataset_retrieval_tool is not None:
            tools.append(dataset_retrieval_tool)
        task_id = uuid.uuid4()
        agent = FunctionCallAgent(
            AgentConfig(
                llm=ChatOpenAI(
                    model=model_name,
                    api_key=os.getenv("DASHSCOPE_API_KEY"),
                    base_url=os.getenv("DASHSCOPE_BASE_URL"),
                    temperature=model_parameters.get("temperature", 0.7),
                ),
                preset_prompt=draft_app_config.preset_prompt,
                enable_long_term_memory=long_term_memory_enabled,
                tools=tools,
            ),
            AgentQueueManager(
                user_id=current_user.id,
                task_id=task_id,
                invoke_from=InvokeFrom.DEBUGGER,
                redis_client=self.redis_client,
            ),
        )

        def stream_event_response() -> Generator:
            answer = ""
            position = 0
            latency = 0
            total_token_count = 0
            final_status = MessageStatus.NORMAL.value
            error = ""
            try:
                for agent_queue_event in agent.run(
                        query=req.query.data,
                        thread_id=str(app_id),
                        long_term_memory=debug_conversation_summary,
                ):
                    event = agent_queue_event.event
                    data = {
                        "id": str(agent_queue_event.id),
                        "task_id": str(agent_queue_event.task_id),
                        "message_id": debug_message_id_text,
                        "conversation_id": debug_conversation_id_text,
                        "event": event.value,
                        "thought": agent_queue_event.thought,
                        "observation": agent_queue_event.observation,
                        "tool": agent_queue_event.tool,
                        "tool_input": agent_queue_event.tool_input,
                        "answer": agent_queue_event.answer,
                        "message": agent_queue_event.message,
                        "message_token_count": agent_queue_event.message_token_count,
                        "message_unit_price": agent_queue_event.message_unit_price,
                        "message_price_unit": agent_queue_event.message_price_unit,
                        "answer_token_count": agent_queue_event.answer_token_count,
                        "answer_unit_price": agent_queue_event.answer_unit_price,
                        "answer_price_unit": agent_queue_event.answer_price_unit,
                        "total_token_count": agent_queue_event.total_token_count,
                        "total_price": agent_queue_event.total_price,
                        "latency": agent_queue_event.latency,
                    }
                    if event == QueueEvent.AGENT_MESSAGE:
                        answer += agent_queue_event.thought or agent_queue_event.answer or ""
                    if agent_queue_event.latency:
                        latency = agent_queue_event.latency
                    if agent_queue_event.total_token_count:
                        total_token_count = agent_queue_event.total_token_count
                    if event not in [QueueEvent.PING]:
                        position += 1
                        self.conversation_service.append_message_agent_thought(
                            debug_message_id,
                            agent_queue_event.id,
                            event.value,
                            data,
                            position,
                        )
                    if event == QueueEvent.STOP:
                        final_status = MessageStatus.STOP.value
                    elif event in [QueueEvent.ERROR, QueueEvent.TIMEOUT]:
                        final_status = MessageStatus.ERROR.value
                        error = agent_queue_event.observation or agent_queue_event.thought or event.value
                    yield f"event: {event.value}\ndata: {json.dumps(data)}\n\n"
            except Exception as e:
                final_status = MessageStatus.ERROR.value
                error = str(e)
                data = {
                    "id": str(uuid.uuid4()),
                    "task_id": str(task_id),
                    "message_id": debug_message_id_text,
                    "conversation_id": debug_conversation_id_text,
                    "event": QueueEvent.ERROR.value,
                    "thought": "",
                    "observation": error,
                    "tool": "",
                    "tool_input": {},
                    "answer": "",
                    "latency": latency,
                }
                yield f"event: {QueueEvent.ERROR.value}\ndata: {json.dumps(data)}\n\n"
            finally:
                self.conversation_service.finalize_debug_message(
                    debug_message_id,
                    answer,
                    final_status,
                    error=error,
                    latency=latency,
                    total_token_count=total_token_count,
                )
                if long_term_memory_enabled and final_status == MessageStatus.NORMAL.value and answer.strip():
                    threading.Thread(
                        target=self._update_debug_summary_in_background,
                        args=(flask_app, debug_conversation_id, req.query.data, answer),
                        daemon=True,
                    ).start()

        return compact_generate_response(stream_event_response())

    def _update_debug_summary_in_background(
            self,
            flask_app,
            conversation_id: UUID,
            query: str,
            answer: str,
    ) -> None:
        """在 SSE 结束后异步更新长期记忆，避免阻塞当前回答。"""
        with flask_app.app_context():
            try:
                self.conversation_service.update_debug_summary_after_answer(
                    conversation_id,
                    query,
                    answer,
                )
            except Exception:
                flask_app.logger.exception("异步更新调试会话长期记忆失败")

    def _build_dataset_retrieval_tool(
            self,
            app_id: UUID,
            draft_datasets: list,
            retrieval_config: dict,
            account,
    ) -> StructuredTool | None:
        """将草稿绑定的知识库转换为 Agent 可调用的检索工具。"""
        dataset_ids = []
        for item in draft_datasets:
            raw_id = item.get("id") if isinstance(item, dict) else item
            try:
                dataset_id = UUID(str(raw_id))
            except (TypeError, ValueError):
                continue
            if dataset_id not in dataset_ids:
                dataset_ids.append(dataset_id)
        if not dataset_ids:
            return None

        strategy = retrieval_config.get("retrieval_strategy", RetrievalStrategy.SEMANTIC.value)
        if strategy not in {
            RetrievalStrategy.SEMANTIC.value,
            RetrievalStrategy.FULL_TEXT.value,
            RetrievalStrategy.HYBRID.value,
        }:
            strategy = RetrievalStrategy.SEMANTIC.value
        k = max(1, min(int(retrieval_config.get("k", 4)), 10))
        score = max(0.0, min(float(retrieval_config.get("score", 0.5)), 1.0))
        account_id = account.id
        flask_app = current_app._get_current_object()

        def dataset_retrieval(query: str) -> dict:
            with flask_app.app_context():
                documents = self.retrieval_service.search_in_datasets(
                    account_id=account_id,
                    dataset_ids=dataset_ids,
                    query=query,
                    retrieval_strategy=strategy,
                    k=k,
                    score=score,
                    retrival_source=RetrievalSource.APP.value,
                    source_app_id=app_id,
                )
                return {
                    "query": query,
                    "count": len(documents),
                    "results": [
                        {
                            "content": document.page_content,
                            "metadata": {
                                key: str(value) if isinstance(value, UUID) else value
                                for key, value in document.metadata.items()
                            },
                        }
                        for document in documents
                    ],
                }

        return StructuredTool.from_function(
            func=dataset_retrieval,
            name="dataset_retrieval",
            description="从当前应用已绑定的知识库中检索资料。回答知识库相关问题前应优先调用。",
            args_schema=DatasetRetrievalInput,
        )

    def _build_debug_tools(self, draft_tools: list[dict], account) -> list:
        """根据应用草稿配置构建调试工具列表"""
        tools = []
        tool_names = set()
        current_time_tool = self.builtin_provider_manager.get_tool("time", "current_time")()
        tools.append(current_time_tool)
        tool_names.add(current_time_tool.name)
        for draft_tool in draft_tools:
            tool_type = draft_tool.get("type")
            provider_id = draft_tool.get("provider_id") or draft_tool.get("provider", {}).get("id")
            tool_name = draft_tool.get("tool_id") or draft_tool.get("tool", {}).get("name")
            if not provider_id or not tool_name:
                continue
            if tool_type == "builtin_tool":
                tool_factory = self.builtin_provider_manager.get_tool(provider_id, tool_name)
                if tool_factory is not None:
                    params = draft_tool.get("params") or (draft_tool.get("tool") or {}).get("params") or {}
                    factory_signature = inspect.signature(tool_factory)
                    accepts_kwargs = any(
                        parameter.kind == inspect.Parameter.VAR_KEYWORD
                        for parameter in factory_signature.parameters.values()
                    )
                    factory_params = (
                        params
                        if accepts_kwargs
                        else {
                            key: value
                            for key, value in params.items()
                            if key in factory_signature.parameters
                        }
                    )
                    tool = tool_factory(**factory_params)
                    if tool.name not in tool_names:
                        tools.append(tool)
                        tool_names.add(tool.name)
            elif tool_type == "api_tool":
                api_tool = self.api_tool_service.get_api_tool(provider_id, tool_name, account)
                tool = self.api_tool_service.api_provider_manager.get_tool(ToolEntity(
                    id=str(api_tool.provider_id),
                    name=api_tool.name,
                    url=api_tool.url,
                    method=api_tool.method,
                    description=api_tool.description,
                    headers=api_tool.provider.headers or [],
                    parameters=api_tool.parameters or [],
                ))
                if tool.name not in tool_names:
                    tools.append(tool)
                    tool_names.add(tool.name)
        return tools

    @classmethod
    def _combine_documents(cls, documents: list[Document]) -> str:
        """将传入的文档列表合并成字符串"""
        return "\n\n".join([document.page_content for document in documents])

    def ping(self):
        return success_json({"content": "pong"})
