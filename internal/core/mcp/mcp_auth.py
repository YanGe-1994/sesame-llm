#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""MCP 请求认证头构建与敏感信息脱敏。"""

import re
from urllib.parse import quote

from internal.core.security import CredentialCipher
from internal.exception import ValidateErrorException


class McpAuth:
    DEFAULT_API_KEY_HEADER = "X-API-Key"
    _HEADER_NAME_PATTERN = re.compile(r"^[!#$%&'*+\-.^_`|~0-9A-Za-z]+$")

    @classmethod
    def build_headers(
        cls,
        auth_type: str,
        encrypted_secret: str,
        auth_header_name: str = "",
    ) -> tuple[dict[str, str], str]:
        if auth_type == "none":
            return {}, ""
        if auth_type not in {"bearer", "api_key"}:
            raise ValidateErrorException("当前仅支持无认证、Bearer Token和API Key")
        if not encrypted_secret:
            raise ValidateErrorException("MCP服务尚未配置认证凭据")

        secret = CredentialCipher.decrypt(encrypted_secret)
        if auth_type == "bearer":
            return {"Authorization": f"Bearer {secret}"}, secret

        header_name = cls.normalize_api_key_header(auth_header_name)
        return {header_name: secret}, secret

    @classmethod
    def normalize_api_key_header(cls, header_name: str) -> str:
        normalized = (header_name or cls.DEFAULT_API_KEY_HEADER).strip()
        if not cls._HEADER_NAME_PATTERN.fullmatch(normalized):
            raise ValidateErrorException("API Key请求头名称不合法")
        return normalized

    @staticmethod
    def redact(value: object, secret: str) -> str:
        text = str(value)
        if not secret:
            return text
        candidates = {
            secret,
            f"Bearer {secret}",
            quote(secret, safe=""),
        }
        for candidate in sorted(candidates, key=len, reverse=True):
            if candidate:
                text = text.replace(candidate, "[REDACTED]")
        return text
