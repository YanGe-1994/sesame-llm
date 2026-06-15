#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
@Time   : 2026/5/12 09:57
@Author : yange19940310@gmail.com
@File   : app_handler.py
"""

import os
import uuid
from dataclasses import dataclass

from injector import inject
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser

from langchain.chat_models import init_chat_model
from internal.exception import NotFoundException
from internal.schema.app_schema import CompletionReq
from internal.service import AppService, AppDebugMemoryService
from pkg.response import success_json, validate_error_json
from internal.core.tools.builtin_tools.providers import BuiltinProviderManager


@inject
@dataclass
class AppHandler:
    """应用控制器"""
    app_service: AppService
    app_debug_memory_service: AppDebugMemoryService
    builtin_provider_manager:BuiltinProviderManager

    def debug(self, appid: uuid.UUID):
        """聊天接口"""
        # 1.提取从接口中获取的输入，POST
        req = CompletionReq()
        if not req.validate():
            return validate_error_json(req.errors)
        # app = self.app_service.get_app(appid)
        # if app is None:
        #     raise NotFoundException("应用不存在")

        parser = StrOutputParser()
        llm = init_chat_model(
            model="qwen3.6-plus",
            model_provider="openai",
            api_key=os.getenv("DASHSCOPE_API_KEY"),
            base_url=os.getenv("DASHSCOPE_BASE_URL"),
        )


        memory_state = self.app_debug_memory_service.load(appid)
        chat_prompt = ChatPromptTemplate.from_messages(
            self.app_debug_memory_service.build_prompt_messages(memory_state, req.query.data)
        )
        completion = chat_prompt | llm | parser

        content = completion.invoke({})
        self.app_debug_memory_service.append_and_compact(appid, req.query.data, content, llm)
        return success_json({"content": content})

    def ping (self):
        google_serper = self.builtin_provider_manager.get_tool('google','google_serper')()
        print('google_serper', google_serper)
        rults = google_serper.invoke('2026世界杯有哪些国家参加，主办方是谁')
        return success_json(rults)