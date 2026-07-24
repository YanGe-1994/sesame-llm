#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
@Time   : 2026/7/21 16:28
@Author : yange19940310@gmail.com
@File   : oauth_service.py
"""
import os
from pathlib import Path
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from flask import request
from injector import inject

from internal.exception import NotFoundException
from internal.model import AccountOAuth
from pkg.oauth import OAuth, GithubOAuth, AlipayOAuth
from pkg.sqlalchemy import SQLAlchemy
from .account_service import AccountService
from .auth_session_service import AuthSessionService
from .base_service import BaseService

def load_key(file_path: str) -> str:
    """
    读取密钥文件
    """
    path = Path(file_path)

    if not path.exists():
        raise FileNotFoundError(f"密钥文件不存在: {path}")

    return path.read_text(
        encoding="utf-8"
    )

@inject
@dataclass
class OAuthService(BaseService):
    """第三方授权你认证服务"""
    db: SQLAlchemy
    account_service: AccountService
    auth_session_service: AuthSessionService

    @classmethod
    def get_all_oauth(cls) -> dict[str, OAuth]:
        """获取LLMOps集成的所有第三方授权认证方式"""
        # 1.实例化集成的第三方授权认证OAuth
        github = GithubOAuth(
            client_id=os.getenv("GITHUB_CLIENT_ID") or '',
            client_secret=os.getenv("GITHUB_CLIENT_SECRET") or '',
            redirect_uri=os.getenv("GITHUB_REDIRECT_URI") or '',
        )



        private_key_path = os.path.join(
            os.getcwd(),
            "config/alipay/app_private_key.pem"
        )
        alipay_public_key_path = os.path.join(
            os.getcwd(),
            "config/alipay/alipay_public_key.pem"
        )
        alipay_public_key = load_key(alipay_public_key_path)
        app_private_key = load_key(private_key_path)
        alipay = AlipayOAuth(
            appid=os.getenv("ALIPAY_APPID"),
            private_key=app_private_key,
            alipay_public_key=alipay_public_key,
            redirect_uri=os.getenv("ALIPAY_REDIRECT_URI"),
        )

        # 2.构建字典并返回
        return {
            "github": github,
            "alipay": alipay,
        }

    @classmethod
    def get_oauth_by_provider_name(cls, provider_name: str) -> OAuth:
        """根据传递的服务提供商名字获取授权服务"""
        all_oauth = cls.get_all_oauth()
        oauth = all_oauth.get(provider_name)

        if oauth is None:
            raise NotFoundException(f"该授权方式[{provider_name}]不存在")

        return oauth

    def oauth_login(self, provider_name: str, code: str) -> dict[str, Any]:
        """第三方OAuth授权认证登录，返回授权凭证以及过期时间"""
        # 1.根据传递的provider_name获取oauth
        oauth = self.get_oauth_by_provider_name(provider_name)

        # 2.根据code从第三方登录服务中获取access_token
        token_result = oauth.get_access_token(code)
        if isinstance(token_result, tuple):
            oauth_access_token, open_id = token_result
        else:
            oauth_access_token = token_result
            open_id = None
        # 3.根据获取到的token提取user_info信息
        oauth_user_info = oauth.get_user_info(oauth_access_token, open_id=open_id)
        # 4.根据provider_name+openid获取授权记录
        account_oauth = self.account_service.get_account_oauth_by_provider_name_and_openid(
            provider_name,
            oauth_user_info.id,
        )
        if not account_oauth:
            # 5.该授权认证方式是第一次登录，查询邮箱是否存在
            account = self.account_service.get_account_by_email(oauth_user_info.email)
            if not account:
                # 6.账号不存在，注册账号
                account = self.account_service.create_account(
                    name=oauth_user_info.name,
                    email=oauth_user_info.email or None,
                    avatar="https://sesame-llmops.oss-cn-chengdu.aliyuncs.com/2026/07/21/41d0f15c-fd7f-4950-84f9-343ee4d96ca1.png"
                )
            # 7.添加授权认证记录
            account_oauth = self.create(
                AccountOAuth,
                account_id=account.id,
                provider=provider_name,
                openid=oauth_user_info.id,
                encrypted_token=oauth_access_token,
            )
        else:
            # 8.查找账号信息
            account = self.account_service.get_account(account_oauth.account_id)
        # 9.更新账号信息，涵盖最后一次登录时间，以及ip地址
        self.update(
            account,
            last_login_at=datetime.now(),
            last_login_ip=request.remote_addr,
        )
        self.update(
            account_oauth,
            encrypted_token=oauth_access_token,
        )

        # 10.生成授权凭证信息
        return self.auth_session_service.create_session(str(account.id), request)