#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
@Time   : 2026/7/21 16:21
@Author : yange19940310@gmail.com
@File   : __init__.py.py
"""
from .github_oauth import GithubOAuth
from .oauth import OAuthUserInfo, OAuth
from .alipay_oauth import AlipayOAuth

__all__ = ["OAuthUserInfo", "OAuth", "GithubOAuth", "AlipayOAuth"]