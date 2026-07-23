#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
@Time   : 2026/7/21 16:21
@Author : yange19940310@gmail.com
@File   : oauth.py.py
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any


@dataclass
class OAuthUserInfo:
    """OAuth用户基础信息，只记录id/name/email"""
    id: str
    name: str
    email: str


@dataclass
class OAuth(ABC):
    """第三方OAuth授权认证基础类"""
    client_id: str  # 客户端id
    client_secret: str  # 客户端秘钥
    redirect_uri: str  # 重定向uri

    @abstractmethod
    def get_provider(self) -> str:
        """获取服务提供者对应的名字"""
        pass

    @abstractmethod
    def get_authorization_url(self) -> str:
        """获取跳转授权认证的URL地址"""
        pass

    @abstractmethod
    def get_access_token(self, code: str) -> str:
        """根据传入的code代码获取授权令牌"""
        pass

    @abstractmethod
    def get_raw_user_info(self, token: Any, **kwargs) -> dict:
        """根据传入的token获取OAuth原始信息"""
        pass

    def get_user_info(self, token: Any, **kwargs) -> OAuthUserInfo:
        """根据传入的token获取OAuthUserInfo信息"""
        raw_info = self.get_raw_user_info(token, **kwargs)
        return self._transform_user_info(raw_info)

    @abstractmethod
    def _transform_user_info(self, raw_info: dict) -> OAuthUserInfo:
        """将OAuth原始信息转换成OAuthUserInfo"""
        pass