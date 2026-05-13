#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
@Time   : 2026/5/12 13:56
@Author : yange19940310@gmail.com
@File   : app_schema.py
"""
from flask_wtf import FlaskForm
from wtforms import StringField
from wtforms.validators import DataRequired,Length
class CompletionReq(FlaskForm):
    """基础聊天接口请求验证"""
    #必填，长度需需要小于2000
    query = StringField("query", validators=[
        DataRequired(message="用户的提问是必填的"),
        Length(max=2000, message="用户的提问最大长度是2000")
    ])