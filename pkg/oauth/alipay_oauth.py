#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
@Time   : 2026/7/21 21:11
@Author : yange19940310@gmail.com
@File   : alipay_oauth.py
"""
import urllib.parse
from datetime import datetime
from typing import Any

from alipay.aop.api.DefaultAlipayClient import DefaultAlipayClient
from alipay.aop.api.AlipayClientConfig import AlipayClientConfig
from alipay.aop.api.request.AlipaySystemOauthTokenRequest import (
    AlipaySystemOauthTokenRequest,
)
# from alipay.aop.api.request.AlipayUserInfoShareRequest import (
#     AlipayUserInfoShareRequest
# )
import json
import uuid
from .oauth import OAuth, OAuthUserInfo

class AlipayOAuth(OAuth):
    """
    支付宝第三方授权登录
    """
    _AUTHORIZE_URL = (
        "https://openauth.alipay.com/oauth2/publicAppAuthorize.htm"
    )
    _ACCESS_TOKEN_API = (
        "alipay.system.oauth.token"
    )
    _USER_INFO_API = (
        "alipay.user.info.share"
    )


    def __init__(
        self,
        appid: str,
        redirect_uri: str,
        private_key: str,
        alipay_public_key: str,
    ):

        super().__init__(
            client_id=appid,
            client_secret=private_key,
            redirect_uri=redirect_uri,
        )

        config = AlipayClientConfig()
        config.server_url = (
            "https://openapi.alipay.com/gateway.do"
        )
        config.app_id = appid

        config.app_private_key = private_key
        config.alipay_public_key = alipay_public_key
        config.sign_type = "RSA2"

        self.client = DefaultAlipayClient(
            config
        )

    def get_provider(self) -> str:
        return "alipay"

    def get_authorization_url(self) -> str:
        """
        获取支付宝授权地址
        """
        params = {
            "app_id": self.client_id,
            "scope": "auth_base",
            "redirect_uri": self.redirect_uri,
            "state": uuid.uuid4().hex
        }
        return (
            f"{self._AUTHORIZE_URL}?"
            f"{urllib.parse.urlencode(params)}"
        )

    def get_access_token(
        self,
        code: str
    ) -> tuple[str, str]:
        """
        auth_code换access_token
        """
        request = AlipaySystemOauthTokenRequest()
        request.grant_type = "authorization_code"
        request.code = code
        response = self.client.execute(request)
        result = json.loads(response)
        access_token = result.get('access_token')
        if not access_token:
            raise ValueError(
                f"支付宝OAuth授权失败:{result}"
            )
        return access_token, result.get('open_id')


    def get_raw_user_info(
        self,
        token: Any,
        **kwargs
    ) -> dict:
        """
        获取支付宝用户信息
        """
        return {
            "name": '',
            "email": '',
            "open_id": kwargs.get('open_id')
        }


    def _transform_user_info(
        self,
        raw_info: dict
    ) -> OAuthUserInfo:
        """
        转换统一用户结构
        """
        return OAuthUserInfo(
            # 支付宝推荐openid
            id=str(raw_info.get( "open_id")),
            name=raw_info.get("nick_name") or f"sesame{datetime.now().strftime('%Y%m%d%H%M%S')}",
            email=''
        )