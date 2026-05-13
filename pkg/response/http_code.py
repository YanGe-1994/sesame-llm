#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
@Time   : 2026/5/12 14:34
@Author : yange19940310@gmail.com
@File   : http_code.py
"""
from enum import  Enum

class HttpCode(str, Enum):
    """HTTP基础业务状态码"""
    SUCCESS = "success"  # 成功状态
    FAIL = "fail"  # 失败状态
    NOT_FOUND = "not_found"  # 未找到
    UNAUTHORIZED = "unauthorized"  # 未授权
    FORBIDDEN = "forbidden"  # 无权限
    VALIDATE_ERROR = "validate_error"  # 数据验证错误