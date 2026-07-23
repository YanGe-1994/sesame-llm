#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
@Time   : 2026/7/21 16:44
@Author : yange19940310@gmail.com
@File   : auth_handler.py
"""
from dataclasses import dataclass
from datetime import datetime

from flask import current_app, make_response, request
from flask_login import logout_user, login_required
from injector import inject

from internal.schema.auth_schema import PasswordLoginReq, PasswordLoginResp
from internal.service import AccountService, AuthSessionService, JwtService
from pkg.response import success_message, validate_error_json, success_json


@inject
@dataclass
class AuthHandler:
    """LLMOps平台自有授权认证处理器"""
    account_service: AccountService
    auth_session_service: AuthSessionService
    jwt_service: JwtService

    def password_login(self):
        """账号密码登录"""
        # 1.提取请求并校验数据
        req = PasswordLoginReq()
        if not req.validate():
            return validate_error_json(req.errors)

        # 2.调用服务登录账号
        credential = self.account_service.password_login(req.email.data, req.password.data)

        # 3.创建响应结构并返回
        resp = PasswordLoginResp()
        response = make_response(success_json(resp.dump(credential)))
        self._set_refresh_token_cookie(response, credential)
        return response

    def refresh(self):
        """刷新访问凭证"""
        credential = self.auth_session_service.refresh_session(
            request.cookies.get("refresh_token"),
            request,
        )
        response = make_response(success_json(PasswordLoginResp().dump(credential)))
        self._set_refresh_token_cookie(response, credential)
        return response

    @login_required
    def logout(self):
        """退出登录，用于提示前端清除授权凭证"""
        auth_header = request.headers.get("Authorization", "")
        if " " in auth_header:
            auth_schema, access_token = auth_header.split(None, 1)
            if auth_schema.lower() == "bearer":
                payload = self.jwt_service.parse_token(access_token)
                self.auth_session_service.revoke_by_access_payload(payload)
        logout_user()
        response = make_response(success_message("退出登陆成功"))
        response.delete_cookie("refresh_token", path="/auth/refresh")
        return response

    def _set_refresh_token_cookie(self, response, credential: dict):
        response.set_cookie(
            "refresh_token",
            credential["refresh_token"],
            max_age=max(int(credential["refresh_expire_at"]) - int(datetime.now().timestamp()), 1),
            httponly=True,
            secure=current_app.config.get("AUTH_COOKIE_SECURE", False),
            samesite=current_app.config.get("AUTH_COOKIE_SAMESITE", "Lax"),
            path="/auth/refresh",
        )