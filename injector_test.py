#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
@Time   : 2026/5/11 22:49
@Author : yange19940310@gmail.com
@File   : injector_test.py
"""
# 依赖注入测试代码
from injector import Injector, inject

class A(Injector):
    name:str = "A"

@inject
class B(Injector):
    def __init__(self, a: A):
        super().__init__()
        self.a = a

    def print(self):
        print(self.a.name)

injector = Injector()
b = injector.get(B)
b.print()