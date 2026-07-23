#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
@Time   : 2026/7/23 00:00
@Author : yange19940310@gmail.com
@File   : auth_session_service.py
"""
import hashlib
import json
import secrets
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from flask import Request, current_app
from injector import inject
from redis import Redis

from internal.exception import UnauthorizedException
from .jwt_service import JwtService


@inject
@dataclass
class AuthSessionService:
    """认证会话服务"""
    redis_client: Redis
    jwt_service: JwtService

    session_key_prefix = "auth:session:"
    issuer = "llmops"

    def create_session(self, account_id: str, request: Request) -> dict[str, Any]:
        """创建认证会话并返回访问凭证"""
        device_id = self._get_device_id(request)
        now = datetime.now()
        now_ts = int(now.timestamp())
        access_expire_at = int((now + timedelta(seconds=self._access_token_ttl())).timestamp())
        refresh_expire_at = int((now + timedelta(seconds=self._refresh_token_ttl())).timestamp())
        session_id = str(uuid.uuid4())
        access_token_id = str(uuid.uuid4())
        refresh_token = self._generate_refresh_token()

        session = {
            "session_id": session_id,
            "account_id": account_id,
            "device_id_hash": self._hash(device_id),
            "refresh_token_hash": self._hash(refresh_token),
            "refresh_token_family": str(uuid.uuid4()),
            "refresh_token_version": 1,
            "user_agent_hash": self._hash(request.headers.get("User-Agent", "")),
            "last_ip_prefix_hash": self._hash(self._ip_prefix(request.remote_addr)),
            "status": "active",
            "created_at": now_ts,
            "last_seen_at": now_ts,
            "expire_at": refresh_expire_at,
            "revoked_at": None,
            "revoked_reason": None,
        }
        self.redis_client.setex(
            self._session_key(session_id),
            max(refresh_expire_at - now_ts, 1),
            json.dumps(session, ensure_ascii=False),
        )

        return {
            "access_token": self._generate_access_token(
                account_id,
                session_id,
                access_token_id,
                now_ts,
                access_expire_at,
            ),
            "expire_at": access_expire_at,
            "refresh_token": refresh_token,
            "refresh_expire_at": refresh_expire_at,
            "session_id": session_id,
        }

    def validate_access_session(self, payload: dict[str, Any], request: Request) -> None:
        """校验访问令牌关联的服务端会话"""
        account_id = payload.get("sub")
        session_id = payload.get("sid")
        access_token_id = payload.get("jti")
        if not account_id or not session_id or not access_token_id:
            raise UnauthorizedException("授权认证凭证无效，请重新登陆")

        session = self._get_active_session(session_id)
        if session.get("account_id") != account_id:
            raise UnauthorizedException("授权认证凭证无效，请重新登陆")
        self._validate_request_fingerprint(session, request)

        session["last_seen_at"] = int(datetime.now().timestamp())
        self._save_session(session)

    def refresh_session(self, refresh_token: str, request: Request) -> dict[str, Any]:
        """刷新访问令牌并轮换refresh token"""
        if not refresh_token:
            raise UnauthorizedException("刷新凭证不存在，请重新登陆")

        session = self._get_session_by_refresh_token(refresh_token)
        self._validate_request_fingerprint(session, request)

        now = datetime.now()
        now_ts = int(now.timestamp())
        access_expire_at = int((now + timedelta(seconds=self._access_token_ttl())).timestamp())
        new_refresh_token = self._generate_refresh_token()
        session["refresh_token_hash"] = self._hash(new_refresh_token)
        session["refresh_token_version"] = int(session.get("refresh_token_version", 0)) + 1
        session["last_seen_at"] = now_ts
        session["last_ip_prefix_hash"] = self._hash(self._ip_prefix(request.remote_addr))
        self._save_session(session)

        return {
            "access_token": self._generate_access_token(
                session["account_id"],
                session["session_id"],
                str(uuid.uuid4()),
                now_ts,
                access_expire_at,
            ),
            "expire_at": access_expire_at,
            "refresh_token": new_refresh_token,
            "refresh_expire_at": int(session["expire_at"]),
            "session_id": session["session_id"],
        }

    def revoke_session(self, session_id: str, reason: str = "logout") -> None:
        """撤销指定认证会话"""
        if session_id:
            self.redis_client.delete(self._session_key(session_id))

    def revoke_by_access_payload(self, payload: dict[str, Any], reason: str = "logout") -> None:
        """根据access token载荷撤销当前会话"""
        self.revoke_session(payload.get("sid"), reason=reason)

    def _generate_access_token(
            self,
            account_id: str,
            session_id: str,
            access_token_id: str,
            issued_at: int,
            expire_at: int,
    ) -> str:
        payload = {
            "sub": account_id,
            "sid": session_id,
            "jti": access_token_id,
            "iss": self.issuer,
            "iat": issued_at,
            "exp": expire_at,
        }
        return self.jwt_service.generate_token(payload)

    def _get_session_by_refresh_token(self, refresh_token: str) -> dict[str, Any]:
        token_hash = self._hash(refresh_token)
        for key in self.redis_client.scan_iter(f"{self.session_key_prefix}*"):
            session = self._loads(self.redis_client.get(key))
            if not session or session.get("status") != "active":
                continue
            if session.get("refresh_token_hash") == token_hash:
                return session
        raise UnauthorizedException("刷新凭证无效，请重新登陆")

    def _get_active_session(self, session_id: str) -> dict[str, Any]:
        session = self._loads(self.redis_client.get(self._session_key(session_id)))
        if not session or session.get("status") != "active":
            raise UnauthorizedException("授权会话已失效，请重新登陆")
        return session

    def _save_session(self, session: dict[str, Any]) -> None:
        ttl = max(int(session["expire_at"]) - int(datetime.now().timestamp()), 1)
        self.redis_client.setex(
            self._session_key(session["session_id"]),
            ttl,
            json.dumps(session, ensure_ascii=False),
        )

    def _validate_request_fingerprint(self, session: dict[str, Any], request: Request) -> None:
        device_id = self._get_device_id(request)
        if session.get("device_id_hash") != self._hash(device_id):
            raise UnauthorizedException("设备认证失败，请重新登陆")
        if session.get("user_agent_hash") != self._hash(request.headers.get("User-Agent", "")):
            raise UnauthorizedException("设备环境变更，请重新登陆")

    def _get_device_id(self, request: Request) -> str:
        device_id = request.headers.get("X-Device-Id", "").strip()
        if not device_id:
            raise UnauthorizedException("设备标识缺失，请重新登陆")
        return device_id

    def _loads(self, value: Any) -> dict[str, Any] | None:
        if not value:
            return None
        if isinstance(value, bytes):
            value = value.decode("utf-8")
        return json.loads(value)

    def _session_key(self, session_id: str) -> str:
        return f"{self.session_key_prefix}{session_id}"

    def _generate_refresh_token(self) -> str:
        return secrets.token_urlsafe(64)

    def _hash(self, value: str | None) -> str:
        return hashlib.sha256((value or "").encode("utf-8")).hexdigest()

    def _ip_prefix(self, ip: str | None) -> str:
        if not ip:
            return ""
        if ":" in ip:
            return ":".join(ip.split(":")[:4])
        parts = ip.split(".")
        return ".".join(parts[:3]) if len(parts) == 4 else ip

    def _access_token_ttl(self) -> int:
        return int(current_app.config.get("ACCESS_TOKEN_TTL_SECONDS", 30 * 60))

    def _refresh_token_ttl(self) -> int:
        return int(current_app.config.get("REFRESH_TOKEN_TTL_SECONDS", 30 * 24 * 60 * 60))
