#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
@Time   : 2026/6/16 10:30
@Author : yange19940310@gmail.com
@File   : duckduckgo_search.py
"""

from langchain.tools import BaseTool
from langchain_community.tools import DuckDuckGoSearchRun
from pydantic import BaseModel,Field

from internal.lib.helper import add_attribute


class DuckDuckGoArgsSchema(BaseModel):
    """"""
    query: str = Field(description='需要检索查询的语句')


@add_attribute("args_schema",DuckDuckGoArgsSchema)
def duckduckgo_search(**kwargs) -> BaseTool:
    """"""
    return DuckDuckGoSearchRun(
        description="一个注重隐私的搜索工具，当你需要搜索时事时可以使用该工具，工具的输入是一个查询语句",
        args_schema=DuckDuckGoArgsSchema
    )