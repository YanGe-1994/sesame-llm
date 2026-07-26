#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
@Time   : 2026/5/12 13:56
@Author : yange19940310@gmail.com
@File   : app_schema.py
"""
from flask_wtf import FlaskForm
from marshmallow import Schema, fields, pre_dump
from wtforms import StringField, IntegerField
from wtforms.validators import DataRequired, Length, Optional, NumberRange, URL

from internal.lib.helper import datetime_to_timestamp
from internal.model import App, DraftAppConfig, Message, MessageAgentThought
from internal.schema.schema import DictField, ListField
from pkg.paginator import PaginatorReq


class CompletionReq(FlaskForm):
    """基础聊天接口请求验证"""
    query = StringField("query", validators=[
        DataRequired(message="用户的提问是必填的"),
        Length(max=2000, message="用户的提问最大长度是2000")
    ])


class CreateAppReq(FlaskForm):
    """创建应用请求"""
    name = StringField("name", validators=[
        DataRequired("应用名称不能为空"),
        Length(max=40, message="应用名称长度不能超过40字符"),
    ])
    icon = StringField("icon", default="", validators=[
        Optional(),
        URL(message="应用图标必须是图片url链接"),
    ])
    description = StringField("description", default="", validators=[
        Optional(),
        Length(max=800, message="应用描述长度不能超过800字符"),
    ])


class UpdateAppReq(CreateAppReq):
    """更新应用请求"""
    pass


class GetAppsWithPageReq(PaginatorReq):
    """获取应用分页列表请求"""
    search_word = StringField("search_word", default="", validators=[Optional()])


class GetAppResp(Schema):
    """获取应用详情响应"""
    id = fields.UUID(dump_default="")
    debug_conversation_id = fields.String(dump_default="")
    name = fields.String(dump_default="")
    icon = fields.String(dump_default="")
    description = fields.String(dump_default="")
    status = fields.String(dump_default="")
    draft_updated_at = fields.Integer(dump_default=0)
    updated_at = fields.Integer(dump_default=0)
    created_at = fields.Integer(dump_default=0)

    @pre_dump
    def process_data(self, data: App, **kwargs):
        draft_app_config = getattr(data, "draft_app_config", None)
        return {
            "id": data.id,
            "debug_conversation_id": "",
            "name": data.name,
            "icon": data.icon,
            "description": data.description,
            "status": data.status or "draft",
            "draft_updated_at": datetime_to_timestamp(draft_app_config.updated_at) if draft_app_config else datetime_to_timestamp(data.updated_at),
            "updated_at": datetime_to_timestamp(data.updated_at),
            "created_at": datetime_to_timestamp(data.created_at),
        }


class GetAppsWithPageResp(GetAppResp):
    """获取应用分页列表响应"""
    pass


class UpdateDraftAppConfigReq(FlaskForm):
    """更新应用草稿配置请求"""
    model = DictField("model", default=None)
    dialog_round = IntegerField("dialog_round", validators=[
        Optional(),
        NumberRange(min=1, max=100, message="携带上下文轮数范围为1-100"),
    ])
    preset_prompt = StringField("preset_prompt", default=None, validators=[
        Optional(),
        Length(max=50000, message="人设与回复逻辑长度不能超过50000字符"),
    ])
    tools = ListField("tools", default=None)
    mcp_servers = ListField("mcp_servers", default=None)
    workflows = ListField("workflows", default=None)
    datasets = ListField("datasets", default=None)
    retrieval_config = DictField("retrieval_config", default=None)
    long_term_memory = DictField("long_term_memory", default=None)
    opening_statement = StringField("opening_statement", default=None, validators=[
        Optional(),
        Length(max=2000, message="开场白长度不能超过2000字符"),
    ])
    opening_questions = ListField("opening_questions", default=None)
    speech_to_text = DictField("speech_to_text", default=None)
    text_to_speech = DictField("text_to_speech", default=None)
    suggested_after_answer = DictField("suggested_after_answer", default=None)
    review_config = DictField("review_config", default=None)


class GetDraftAppConfigResp(Schema):
    """获取应用草稿配置响应"""
    id = fields.UUID(dump_default="")
    model_config = fields.Dict(dump_default={})
    dialog_round = fields.Integer(dump_default=3)
    preset_prompt = fields.String(dump_default="")
    tools = fields.List(fields.Dict, dump_default=[])
    mcp_servers = fields.List(fields.Dict, dump_default=[])
    workflows = fields.List(fields.Dict, dump_default=[])
    datasets = fields.List(fields.Raw, dump_default=[])
    retrieval_config = fields.Dict(dump_default={})
    long_term_memory = fields.Dict(dump_default={})
    opening_statement = fields.String(dump_default="")
    opening_questions = fields.List(fields.String, dump_default=[])
    speech_to_text = fields.Dict(dump_default={})
    text_to_speech = fields.Dict(dump_default={})
    suggested_after_answer = fields.Dict(dump_default={})
    review_config = fields.Dict(dump_default={})
    updated_at = fields.Integer(dump_default=0)
    created_at = fields.Integer(dump_default=0)

    @pre_dump
    def process_data(self, data: DraftAppConfig, **kwargs):
        return {
            "id": data.id,
            "model_config": data.model_config,
            "dialog_round": data.dialog_round,
            "preset_prompt": data.preset_prompt,
            "tools": getattr(data, "hydrated_tools", data.tools),
            "mcp_servers": getattr(data, "hydrated_mcp_servers", data.mcp_servers),
            "workflows": data.workflows,
            "datasets": getattr(data, "hydrated_datasets", data.datasets),
            "retrieval_config": data.retrieval_config,
            "long_term_memory": data.long_term_memory,
            "opening_statement": data.opening_statement,
            "opening_questions": data.opening_questions,
            "speech_to_text": data.speech_to_text,
            "text_to_speech": data.text_to_speech,
            "suggested_after_answer": data.suggested_after_answer,
            "review_config": data.review_config,
            "updated_at": datetime_to_timestamp(data.updated_at),
            "created_at": datetime_to_timestamp(data.created_at),
        }


class UpdateDebugConversationSummaryReq(FlaskForm):
    """更新调试会话长期记忆请求"""
    summary = StringField("summary", default="", validators=[
        Optional(),
        Length(max=2000, message="长期记忆长度不能超过2000字符"),
    ])


class GetDebugConversationMessagesWithPageReq(PaginatorReq):
    """获取调试会话消息分页列表请求"""
    created_at = IntegerField("created_at", default=0, validators=[Optional()])


class MessageAgentThoughtResp(Schema):
    """调试消息推理步骤响应"""
    id = fields.UUID(dump_default="")
    position = fields.Integer(dump_default=0)
    event = fields.String(dump_default="")
    thought = fields.String(dump_default="")
    observation = fields.String(dump_default="")
    tool = fields.String(dump_default="")
    tool_input = fields.Dict(dump_default={})
    latency = fields.Float(dump_default=0)
    created_at = fields.Integer(dump_default=0)

    @pre_dump
    def process_data(self, data: MessageAgentThought, **kwargs):
        return {
            "id": data.id,
            "position": data.position,
            "event": data.event,
            "thought": data.thought,
            "observation": data.observation,
            "tool": data.tool,
            "tool_input": data.tool_input or {},
            "latency": data.latency,
            "created_at": datetime_to_timestamp(data.created_at),
        }


class DebugConversationMessageResp(Schema):
    """调试会话消息响应"""
    id = fields.UUID(dump_default="")
    conversation_id = fields.UUID(dump_default="")
    query = fields.String(dump_default="")
    answer = fields.String(dump_default="")
    total_token_count = fields.Integer(dump_default=0)
    latency = fields.Float(dump_default=0)
    agent_thoughts = fields.List(fields.Nested(MessageAgentThoughtResp), dump_default=[])
    created_at = fields.Integer(dump_default=0)

    @pre_dump
    def process_data(self, data: Message, **kwargs):
        return {
            "id": data.id,
            "conversation_id": data.conversation_id,
            "query": data.query,
            "answer": data.answer,
            "total_token_count": data.total_token_count,
            "latency": data.latency,
            "agent_thoughts": getattr(data, "agent_thoughts", []),
            "created_at": datetime_to_timestamp(data.created_at),
        }