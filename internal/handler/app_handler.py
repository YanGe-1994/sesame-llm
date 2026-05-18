#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
@Time   : 2026/5/12 09:57
@Author : yange19940310@gmail.com
@File   : app_handler.py
"""

import os
import uuid
from asyncio import log
from dataclasses import dataclass
from datetime import datetime
from injector import inject
from openai import OpenAI
from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel, Field
from langchain_core.output_parsers import JsonOutputParser



from langchain.chat_models import init_chat_model
from internal.schema.app_schema import CompletionReq
from internal.service import AppService
from pkg.response import success_json, validate_error_json, success_message


@inject
@dataclass
class AppHandler:
    """应用控制器"""
    app_service: AppService

    def create_app(self):
        """调用服务创建新的APP记录"""
        app = self.app_service.create_app()
        return success_message(f"应用已经成功创建，id为{app.id}")

    def get_app(self, id: uuid.UUID):
        app = self.app_service.get_app(id)
        return success_message(f"应用已经成功获取，名字是{app.name}")

    def update_app(self, id: uuid.UUID):
        app = self.app_service.update_app(id)
        return success_message(f"应用已经成功修改，修改的名字是:{app.name}")

    def delete_app(self, id: uuid.UUID):
        app = self.app_service.delete_app(id)
        return success_message(f"应用已经成功删除，id为:{app.id}")

    def completion(self):

        class Joke(BaseModel):
            joke:str= Field(description="回答用户的笑话")
            punchline: str= Field(description="这个笑话的笑点")

        """聊天接口"""
        # 1.提取从接口中获取的输入，POST
        req = CompletionReq()
        if not req.validate():
            return validate_error_json(req.errors)
        # 2.构建OpenAI客户端，并发起请求
        parser = JsonOutputParser(pydantic_object=Joke)

        # 获取格式化指令，告诉model如何输出符合要求的JSON格式
        format_instructions = parser.get_format_instructions()

        chat_prompt = ChatPromptTemplate.from_messages(
            [
                ("system",
                 "你是一个收藏了很多笑话的笑话大师，你的名字是笑话大王，请用幽默的方式回答用户的问题。"),
                ("human", "{query}。{format_instructions}")
            ]
        )
        prompt = chat_prompt.partial(format_instructions=format_instructions)

        llm = init_chat_model(
            model="qwen3.6-plus",
            model_provider="openai",
            api_key=os.getenv("DASHSCOPE_API_KEY"),
            base_url=os.getenv("DASHSCOPE_BASE_URL"),
        )


        # 3.得到请求响应，然后将OpenAI的响应传递给前端
        completion = prompt | llm | parser

        content = completion.invoke(req.query.data)

        return success_json({"content": content})

        # return success_json({"content": "哈哈哈哈"})