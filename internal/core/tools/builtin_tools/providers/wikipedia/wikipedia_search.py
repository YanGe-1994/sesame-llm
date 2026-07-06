#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
@Time   : 2026/6/17 09:15
@Author : yange19940310@gmail.com
@File   : wikipedia_search.py
"""

from langchain_community.tools.wikipedia.tool import WikipediaQueryInput,WikipediaQueryRun
from langchain_community.utilities import WikipediaAPIWrapper

from langchain.tools import BaseTool

from internal.lib.helper import add_attribute


@add_attribute("args_schema",WikipediaQueryInput)
def wikipedia_search(**kwargs) -> BaseTool:
    return WikipediaQueryRun(
        api_wrapper=WikipediaAPIWrapper(),
    )