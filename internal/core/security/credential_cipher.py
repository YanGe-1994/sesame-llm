#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""敏感凭据的应用层加密。"""

import base64
import hashlib
import os

from cryptography.fernet import Fernet, InvalidToken

from internal.exception import ValidateErrorException


class CredentialCipher:
    """使用独立主密钥加密 MCP 等外部服务凭据。"""

    VERSION_PREFIX = "fernet:v1:"

    @classmethod
    def encrypt(cls, plaintext: str) -> str:
        if not plaintext:
            return ""
        token = cls._fernet().encrypt(plaintext.encode("utf-8")).decode("ascii")
        return f"{cls.VERSION_PREFIX}{token}"

    @classmethod
    def decrypt(cls, ciphertext: str) -> str:
        if not ciphertext:
            return ""
        if not ciphertext.startswith(cls.VERSION_PREFIX):
            raise ValidateErrorException("凭据密文格式不受支持，请重新配置凭据")
        try:
            token = ciphertext[len(cls.VERSION_PREFIX):].encode("ascii")
            return cls._fernet().decrypt(token).decode("utf-8")
        except (InvalidToken, UnicodeDecodeError, ValueError) as error:
            raise ValidateErrorException("凭据解密失败，请重新配置凭据") from error

    @staticmethod
    def hint(plaintext: str) -> str:
        if not plaintext:
            return ""
        suffix = plaintext[-4:] if len(plaintext) > 4 else plaintext[-1:]
        return f"••••{suffix}"

    @classmethod
    def _fernet(cls) -> Fernet:
        master_key = os.getenv("MCP_CREDENTIAL_ENCRYPTION_KEY") or os.getenv("JWT_SECRET_KEY")
        if not master_key:
            raise ValidateErrorException(
                "未配置MCP_CREDENTIAL_ENCRYPTION_KEY，无法安全保存MCP凭据"
            )
        derived_key = base64.urlsafe_b64encode(
            hashlib.sha256(master_key.encode("utf-8")).digest()
        )
        return Fernet(derived_key)
