#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
@Time   : 2026/6/17 09:29
@Author : yange19940310@gmail.com
@File   : dashscope_image.py
"""
from pathlib import PurePosixPath
from typing import Any, Type

from urllib.parse import urlparse, unquote
from langchain.tools import BaseTool
from pydantic import BaseModel, Field

from http import HTTPStatus
import requests
from dashscope import ImageSynthesis
import os
import dashscope

from internal.lib.helper import add_attribute

dashscope.base_http_api_url = 'https://dashscope.aliyuncs.com/api/v1'
api_key = os.getenv("DASHSCOPE_API_KEY")


class DashscopeImageArgsSchema(BaseModel):
    """DashscopeImage文件生成的输入描述"""
    prompt: str = Field(..., description="用于生成图像的文本提示词")
    negative_prompt: str = Field(None, description="不希望出现在图像中的内容")
    n: str = Field(1, description="生成图片的数量，默认为1")
    size: str = Field("1024*1024", description="生成图片的尺寸，例如 1024*1024")

class DashscopeImageRun(BaseTool):
    """根据用户输入的描述信息，生成图片的工具"""
    name: str = "dashscope_image"
    description: str = "一个基于用户的输入，生成图片的工具"
    args_schema:Type[BaseModel] = DashscopeImageArgsSchema
    def _run(self, *args: Any, **kwargs: Any) -> Any:
        # 检查 API Key 是否存在
        if not api_key:
            return "错误：未找到 DASHSCOPE_API_KEY 环境变量。"
        print('----同步调用，请等待任务执行----')
        print('kwargs',kwargs)

        rsp = ImageSynthesis.call(
            api_key=api_key,
            model="qwen-image-plus",
            # 当前仅qwen-image-plus、qwen-image模型支持异步接口
            prompt=kwargs.get("prompt"),
            negative_prompt=kwargs.get("negative_prompt"),
            n=kwargs.get('n'),
            size=kwargs.get("size"),
            prompt_extend=True,
            watermark=False
        )
        print(f'response: {rsp}')
        if rsp.status_code == HTTPStatus.OK:
            # 在当前目录下保存图像
            for result in rsp.output.results:
                file_name = \
                PurePosixPath(unquote(urlparse(result.url).path)).parts[-1]
                with open('./%s' % file_name, 'wb+') as f:
                    f.write(requests.get(result.url).content)
            return '生成成功，请打开文件夹查看'
        else:
            print(
                f'同步调用失败, status_code: {rsp.status_code}, code: {rsp.code}, message: {rsp.message}')
            return ''

@add_attribute("args_schema",DashscopeImageArgsSchema)
def dashscope_image() -> BaseTool:
    return  DashscopeImageRun()