#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
@Time   : 2026/6/16 10:20
@Author : yange19940310@gmail.com
@File   : current_time.py
"""

from typing import  Any
from langchain.tools import BaseTool
from datetime import datetime



class CurrentTimeTool(BaseTool):
    name: str = "current_time"
    description: str = "获取当前时间的工具"
    def _run(self, *args: Any, **kwargs: Any) -> Any:
        """获取当前系统的时间并进行格式化后返回"""
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S %Z")


def current_time(**kwargs) -> BaseTool:
    """返回获取当前时间的LangChain工具"""
    return CurrentTimeTool()