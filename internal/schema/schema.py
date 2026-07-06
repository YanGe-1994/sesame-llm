#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
@Time   : 2026/6/21 20:36
@Author : yange19940310@gmail.com
@File    : schema.py
"""
from wtforms import Field


class ListField(Field):
    """自定义list字段，用于存储列表型数据"""
    data: list = None

    def process_formdata(self, valuelist):
        if valuelist is not None and isinstance(valuelist, list):
            self.data = valuelist

    def _value(self):
        return self.data if self.data else []


# 新增:字典字段
class DictField(Field):
    """自定义dict字段"""
    data: dict = None

    def process_formdata(self, valuelist):
        if valuelist is not None and len(valuelist) > 0 and isinstance(valuelist[0], dict):
            self.data = valuelist[0]

    def _value(self):
        return self.data