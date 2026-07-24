#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""阿里百炼图片生成工具。"""
import os
from http import HTTPStatus
from typing import Any, Type
from urllib.parse import urlparse

import dashscope
import requests
from dashscope import ImageSynthesis
from langchain.tools import BaseTool
from pydantic import BaseModel, Field

from internal.lib.helper import add_attribute
from internal.service.oss_service import OssService


dashscope.base_http_api_url = "https://dashscope.aliyuncs.com/api/v1"


class DashscopeImageArgsSchema(BaseModel):
    """DashScope 图片生成输入参数。"""
    prompt: str = Field(..., description="用于生成图像的文本提示词")
    negative_prompt: str | None = Field(None, description="不希望出现在图像中的内容")
    n: int = Field(1, ge=1, le=4, description="生成图片数量")
    size: str = Field("2048*2048", description="生成图片尺寸，例如 2048*2048")


class DashscopeImageRun(BaseTool):
    """生成图片后直接上传 OSS，不写入服务器本地。"""
    name: str = "dashscope_image"
    description: str = "基于文本描述生成图片，并返回可直接访问的图片 URL"
    args_schema: Type[BaseModel] = DashscopeImageArgsSchema

    def _run(self, *args: Any, **kwargs: Any) -> dict:
        api_key = os.getenv("DASHSCOPE_API_KEY")
        if not api_key:
            return {"success": False, "error": "未配置 DASHSCOPE_API_KEY"}

        response = ImageSynthesis.call(
            api_key=api_key,
            model="qwen-image-plus",
            prompt=kwargs.get("prompt"),
            negative_prompt=kwargs.get("negative_prompt"),
            n=kwargs.get("n", 1),
            size=kwargs.get("size", "2048*2048"),
            prompt_extend=True,
            watermark=False,
        )
        if response.status_code != HTTPStatus.OK:
            return {
                "success": False,
                "error": getattr(response, "message", "图片生成失败"),
                "code": getattr(response, "code", ""),
            }

        images = []
        for result in response.output.results:
            download_response = requests.get(result.url, timeout=60)
            download_response.raise_for_status()
            content_type = download_response.headers.get("Content-Type", "").split(";", 1)[0].lower()
            extension = {
                "image/jpeg": "jpg",
                "image/webp": "webp",
                "image/gif": "gif",
            }.get(content_type)
            if extension is None:
                path_extension = os.path.splitext(urlparse(result.url).path)[1].lstrip(".").lower()
                extension = path_extension if path_extension in {"png", "jpg", "jpeg", "webp", "gif"} else "png"
            image_url = OssService.upload_bytes(download_response.content, extension=extension)
            images.append({"url": image_url})

        return {
            "success": True,
            "message": "图片生成成功",
            "images": images,
            "markdown": "\n".join(f"![生成图片]({image['url']})" for image in images),
        }


@add_attribute("args_schema", DashscopeImageArgsSchema)
def dashscope_image() -> BaseTool:
    return DashscopeImageRun()