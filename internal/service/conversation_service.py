#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
@Time   : 2026/7/5 15:09
@Author : yange19940310@gmail.com
@File   : conversation_service.py
"""
import logging
import os
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from sqlalchemy import desc

from injector import inject
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI

from internal.entity.conversation_entity import (
    SUMMARIZER_TEMPLATE,
    CONVERSATION_NAME_TEMPLATE,
    ConversationInfo,
    SUGGESTED_QUESTIONS_TEMPLATE,
    SuggestedQuestions,
    InvokeFrom,
    MessageStatus,
)
from internal.exception import NotFoundException
from internal.lib.helper import datetime_to_timestamp
from internal.model import Account, Conversation, Message, MessageAgentThought
from pkg.paginator import Paginator, PaginatorReq
from pkg.sqlalchemy import SQLAlchemy
from .base_service import BaseService


@inject
@dataclass
class ConversationService(BaseService):
    """会话服务"""
    db: SQLAlchemy

    @classmethod
    def _build_llm(cls, temperature: float = 0) -> ChatOpenAI:
        return ChatOpenAI(
            model=os.getenv("DASHSCOPE_MODEL") or "qwen3.7-max-2026-06-08",
            api_key=os.getenv("DASHSCOPE_API_KEY"),
            base_url=os.getenv("DASHSCOPE_BASE_URL"),
            temperature=temperature,
        )

    @classmethod
    def summary(cls, human_message: str, ai_message: str, old_summary: str = "") -> str:
        """根据传递的人类消息、AI消息还有原始的摘要信息总结生成一段新的摘要"""
        # 1.创建prompt
        prompt = ChatPromptTemplate.from_template(SUMMARIZER_TEMPLATE)

        # 2.构建大语言模型实例，并且将大语言模型的温度调低，降低幻觉的概率
        llm = cls._build_llm(temperature=0.5)

        # 3.构建链应用
        summary_chain = prompt | llm | StrOutputParser()

        # 4.调用链并获取新摘要信息
        new_summary = summary_chain.invoke({
            "summary": old_summary,
            "new_lines": f"Human: {human_message}\nAI: {ai_message}",
        })

        return new_summary

    @classmethod
    def generate_conversation_name(cls, query: str) -> str:
        """根据传递的query生成对应的会话名字，并且语言与用户的输入保持一致"""
        # 1.创建prompt
        prompt = ChatPromptTemplate.from_messages([
            ("system", CONVERSATION_NAME_TEMPLATE),
            ("human", "{query}")
        ])

        # 2.构建大语言模型实例，并且将大语言模型的温度调低，降低幻觉的概率
        llm = cls._build_llm(temperature=0)
        structured_llm = llm.with_structured_output(ConversationInfo)

        # 3.构建链应用
        chain = prompt | structured_llm

        # 4.提取并整理query，截取长度过长的部分
        if len(query) > 2000:
            query = query[:300] + "...[TRUNCATED]..." + query[-300:]
        query = query.replace("\n", " ")

        # 5.调用链并获取会话信息
        conversation_info = chain.invoke({"query": query})

        # 6.提取会话名称
        name = "新的会话"
        try:
            if conversation_info and hasattr(conversation_info, "subject"):
                name = conversation_info.subject
        except Exception as e:
            logging.exception(f"提取会话名称出错, conversation_info: {conversation_info}, 错误信息: {str(e)}")
        if len(name) > 75:
            name = name[:75] + "..."

        return name

    @classmethod
    def generate_suggested_questions(cls, histories: str) -> list[str]:
        """根据传递的历史信息生成最多不超过3个的建议问题"""
        # 1.创建prompt
        prompt = ChatPromptTemplate.from_messages([
            ("system", SUGGESTED_QUESTIONS_TEMPLATE),
            ("human", "{histories}")
        ])

        # 2.构建大语言模型实例，并且将大语言模型的温度调低，降低幻觉的概率
        llm = cls._build_llm(temperature=0)
        structured_llm = llm.with_structured_output(SuggestedQuestions)

        # 3.构建链应用
        chain = prompt | structured_llm

        # 4.调用链并获取建议问题列表
        suggested_questions = chain.invoke({"histories": histories})

        # 5.提取建议问题列表
        questions = []
        try:
            if suggested_questions and hasattr(suggested_questions, "questions"):
                questions = suggested_questions.questions
        except Exception as e:
            logging.exception(f"生成建议问题出错, suggested_questions: {suggested_questions}, 错误信息: {str(e)}")
        if len(questions) > 3:
            questions = questions[:3]

        return questions

    def get_or_create_debug_conversation(self, app_id: UUID, account: Account) -> Conversation:
        """获取或创建调试会话"""
        conversation = self.db.session.query(Conversation).filter(
            Conversation.app_id == app_id,
            Conversation.created_by == account.id,
            Conversation.invoke_from == InvokeFrom.DEBUGGER,
            Conversation.is_deleted == False,
        ).one_or_none()
        if conversation is not None:
            return conversation

        with self.db.auto_commit():
            conversation = Conversation(
                app_id=app_id,
                name="调试会话",
                invoke_from=InvokeFrom.DEBUGGER,
                created_by=account.id,
            )
            self.db.session.add(conversation)
            self.db.session.flush()
            conversation_id = conversation.id
        return self.db.session.query(Conversation).filter(Conversation.id == conversation_id).one()

    def get_debug_summary(self, app_id: UUID, account: Account) -> str:
        """获取调试会话长期记忆"""
        conversation = self.get_or_create_debug_conversation(app_id, account)
        return conversation.summary or ""

    def update_debug_summary(self, app_id: UUID, account: Account, summary: str) -> Conversation:
        """更新调试会话长期记忆"""
        conversation = self.get_or_create_debug_conversation(app_id, account)
        return self.update(conversation, summary=summary or "")

    def create_debug_message(self, conversation: Conversation, query: str, account: Account) -> Message:
        """创建调试消息"""
        with self.db.auto_commit():
            message = Message(
                app_id=conversation.app_id,
                conversation_id=conversation.id,
                invoke_from=InvokeFrom.DEBUGGER,
                created_by=account.id,
                query=query,
                status="generating",
            )
            self.db.session.add(message)
            self.db.session.flush()
            message_id = message.id
        return self.db.session.query(Message).filter(Message.id == message_id).one()

    def append_message_agent_thought(
            self,
            message_id: UUID,
            event_id: UUID,
            event: str,
            data: dict,
            position: int,
    ) -> MessageAgentThought:
        """追加调试消息推理步骤"""
        message = self.db.session.query(Message).filter(Message.id == message_id).one_or_none()
        if message is None:
            raise NotFoundException("调试消息不存在")
        with self.db.auto_commit():
            agent_thought = self.db.session.query(MessageAgentThought).filter(
                MessageAgentThought.id == event_id,
                MessageAgentThought.message_id == message_id,
            ).one_or_none()
            if agent_thought is None:
                agent_thought = MessageAgentThought(
                    id=event_id,
                    app_id=message.app_id,
                    conversation_id=message.conversation_id,
                    message_id=message_id,
                    invoke_from=InvokeFrom.DEBUGGER,
                    created_by=message.created_by,
                    position=position,
                )
                self.db.session.add(agent_thought)
            agent_thought.event = event or ""
            agent_thought.thought = f"{agent_thought.thought or ''}{data.get('thought') or ''}"
            agent_thought.observation = data.get("observation") or agent_thought.observation or ""
            agent_thought.tool = data.get("tool") or agent_thought.tool or ""
            agent_thought.tool_input = data.get("tool_input") or agent_thought.tool_input or {}
            agent_thought.message = data.get("message") or agent_thought.message or []
            agent_thought.message_token_count = data.get("message_token_count") or agent_thought.message_token_count or 0
            agent_thought.message_unit_price = data.get("message_unit_price") or agent_thought.message_unit_price or 0
            agent_thought.message_price_unit = data.get("message_price_unit") or agent_thought.message_price_unit or 0
            agent_thought.answer = data.get("answer") or agent_thought.thought or ""
            agent_thought.answer_token_count = data.get("answer_token_count") or agent_thought.answer_token_count or 0
            agent_thought.answer_unit_price = data.get("answer_unit_price") or agent_thought.answer_unit_price or 0
            agent_thought.answer_price_unit = data.get("answer_price_unit") or agent_thought.answer_price_unit or 0
            agent_thought.total_token_count = data.get("total_token_count") or agent_thought.total_token_count or 0
            agent_thought.total_price = data.get("total_price") or agent_thought.total_price or 0
            agent_thought.latency = data.get("latency") or agent_thought.latency or 0
            self.db.session.flush()
        return agent_thought

    def finalize_debug_message(
            self,
            message_id: UUID,
            answer: str,
            status: str = MessageStatus.NORMAL.value,
            error: str = "",
            latency: float = 0,
            total_token_count: int = 0,
    ) -> Message:
        """完成调试消息"""
        message = self.db.session.query(Message).filter(Message.id == message_id).one_or_none()
        if message is None:
            raise NotFoundException("调试消息不存在")
        return self.update(
            message,
            answer=answer or "",
            status=status,
            error=error or "",
            latency=latency or 0,
            total_token_count=total_token_count or 0,
        )

    def paginate_debug_messages(self, app_id: UUID, account: Account, req: PaginatorReq) -> tuple[list[Message], Paginator]:
        """获取调试消息分页列表"""
        conversation = self.get_or_create_debug_conversation(app_id, account)
        paginator = Paginator(db=self.db, req=req)
        filters = [
            Message.app_id == app_id,
            Message.conversation_id == conversation.id,
            Message.created_by == account.id,
            Message.invoke_from == InvokeFrom.DEBUGGER,
            Message.is_deleted == False,
        ]
        if getattr(req, "created_at", None) is not None and req.created_at.data:
            filters.append(Message.created_at < datetime.fromtimestamp(req.created_at.data))
        messages = paginator.paginate(
            self.db.session.query(Message).filter(*filters).order_by(desc("created_at"))
        )
        for message in messages:
            message.agent_thoughts = self.db.session.query(MessageAgentThought).filter(
                MessageAgentThought.message_id == message.id,
            ).order_by(MessageAgentThought.position.asc(), MessageAgentThought.created_at.asc()).all()
        return messages, paginator

    def clear_debug_conversation(self, app_id: UUID, account: Account) -> Conversation:
        """清空调试会话"""
        conversation = self.get_or_create_debug_conversation(app_id, account)
        with self.db.auto_commit():
            self.db.session.query(Message).filter(
                Message.app_id == app_id,
                Message.conversation_id == conversation.id,
                Message.created_by == account.id,
                Message.invoke_from == InvokeFrom.DEBUGGER,
                Message.is_deleted == False,
            ).update({"is_deleted": True}, synchronize_session=False)
            conversation.summary = ""
        return conversation

    def update_debug_summary_after_answer(self, conversation_id: UUID, query: str, answer: str) -> Conversation:
        """根据调试问答更新长期记忆"""
        conversation = self.db.session.query(Conversation).filter(Conversation.id == conversation_id).one_or_none()
        if conversation is None:
            raise NotFoundException("调试会话不存在")
        new_summary = self.summary(query, answer, conversation.summary or "")
        return self.update(conversation, summary=new_summary)

    def generate_suggested_questions_by_message(self, message_id: UUID, account: Account) -> list[str]:
        """根据已保存的调试消息生成建议问题"""
        message = self.db.session.query(Message).join(
            Conversation,
            Message.conversation_id == Conversation.id,
        ).filter(
            Message.id == message_id,
            Message.created_by == account.id,
            Message.invoke_from == InvokeFrom.DEBUGGER,
            Message.is_deleted == False,
            Conversation.created_by == account.id,
            Conversation.invoke_from == InvokeFrom.DEBUGGER,
            Conversation.is_deleted == False,
        ).one_or_none()
        if message is None:
            raise NotFoundException("调试消息不存在")

        recent_messages = self.db.session.query(Message).filter(
            Message.app_id == message.app_id,
            Message.conversation_id == message.conversation_id,
            Message.created_by == account.id,
            Message.invoke_from == InvokeFrom.DEBUGGER,
            Message.is_deleted == False,
        ).order_by(desc("created_at")).limit(5).all()
        histories = "\n".join([
            f"Human: {item.query}\nAI: {item.answer}"
            for item in reversed(recent_messages)
            if item.answer
        ])
        if histories.strip() == "":
            histories = f"Human: {message.query}\nAI: {message.answer}"
        return self.generate_suggested_questions(histories)