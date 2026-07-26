#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""MCP OAuth 2.1 authorization-code/PKCE and token lifecycle."""

import base64
import hashlib
import json
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta
from urllib.parse import urlencode, urlparse
from uuid import UUID

import httpx
from injector import inject
from redis import Redis

from internal.core.security import CredentialCipher, OutboundSecurityPolicy, SafeSyncTransport
from internal.exception import FailException, NotFoundException, ValidateErrorException
from internal.model import Account, McpServer
from pkg.sqlalchemy import SQLAlchemy


@inject
@dataclass
class McpOAuthService:
    db: SQLAlchemy
    redis_client: Redis

    STATE_TTL_SECONDS = 600
    REFRESH_SKEW_SECONDS = 60
    REQUEST_TIMEOUT_SECONDS = 20

    def begin_authorization(self, server_id: UUID, account: Account, redirect_uri: str) -> dict:
        server = self._get_server(server_id, account.id)
        self._validate_config(server)
        state = secrets.token_urlsafe(32)
        verifier = secrets.token_urlsafe(64)
        challenge = base64.urlsafe_b64encode(
            hashlib.sha256(verifier.encode("ascii")).digest()
        ).rstrip(b"=").decode("ascii")
        payload = {
            "server_id": str(server.id),
            "account_id": str(account.id),
            "redirect_uri": redirect_uri,
            "code_verifier": verifier,
        }
        self.redis_client.setex(
            self._state_key(state),
            self.STATE_TTL_SECONDS,
            json.dumps(payload, ensure_ascii=False),
        )
        params = {
            "response_type": "code",
            "client_id": server.oauth_client_id,
            "redirect_uri": redirect_uri,
            "state": state,
            "code_challenge": challenge,
            "code_challenge_method": "S256",
        }
        if server.oauth_scopes:
            params["scope"] = " ".join(server.oauth_scopes)
        separator = "&" if "?" in server.oauth_authorization_url else "?"
        return {
            "authorization_url": f"{server.oauth_authorization_url}{separator}{urlencode(params)}",
            "expires_in": self.STATE_TTL_SECONDS,
        }

    def complete_authorization(self, state: str, code: str) -> McpServer:
        if not state or not code:
            raise ValidateErrorException("OAuth callback is missing state or code")
        key = self._state_key(state)
        raw = self.redis_client.get(key)
        self.redis_client.delete(key)
        if not raw:
            raise ValidateErrorException("OAuth authorization state has expired or was already used")
        payload = json.loads(raw.decode("utf-8") if isinstance(raw, bytes) else raw)
        server = self._get_server(UUID(payload["server_id"]), UUID(payload["account_id"]))
        token = self._request_token(server, {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": payload["redirect_uri"],
            "code_verifier": payload["code_verifier"],
        })
        self._save_token(server, token)
        return server

    def get_authorization_headers(self, server_id: UUID, account_id: UUID) -> tuple[dict[str, str], str]:
        server = self._get_server(server_id, account_id)
        if server.auth_type != "oauth2":
            raise ValidateErrorException("MCP server is not configured for OAuth 2.1")
        if not server.encrypted_access_token:
            raise ValidateErrorException("MCP server has not completed OAuth authorization")
        if self._is_expiring(server):
            server = self._refresh(server)
        access_token = CredentialCipher.decrypt(server.encrypted_access_token)
        token_type = (server.oauth_token_type or "Bearer").strip()
        return {"Authorization": f"{token_type} {access_token}"}, access_token

    def disconnect(self, server_id: UUID, account: Account) -> McpServer:
        server = self._get_server(server_id, account.id)
        with self.db.auto_commit():
            server.encrypted_access_token = ""
            server.encrypted_refresh_token = ""
            server.oauth_token_type = "Bearer"
            server.oauth_expires_at = None
            server.oauth_granted_scopes = []
            server.oauth_authorized_at = None
            server.oauth_last_error = ""
            server.status = "draft"
        return server

    def _refresh(self, server: McpServer) -> McpServer:
        if not server.encrypted_refresh_token:
            raise ValidateErrorException("OAuth access token has expired and no refresh token is available")
        lock = self.redis_client.lock(f"mcp:oauth:refresh:{server.id}", timeout=30, blocking_timeout=10)
        with lock:
            server = self._get_server(server.id, server.account_id)
            if not self._is_expiring(server):
                return server
            refresh_token = CredentialCipher.decrypt(server.encrypted_refresh_token)
            try:
                token = self._request_token(server, {
                    "grant_type": "refresh_token",
                    "refresh_token": refresh_token,
                })
                if not token.get("refresh_token"):
                    token["refresh_token"] = refresh_token
                self._save_token(server, token)
                return server
            except Exception as error:
                with self.db.auto_commit():
                    server.oauth_last_error = str(error)[:2000]
                    server.status = "unavailable"
                raise

    def _request_token(self, server: McpServer, data: dict) -> dict:
        payload = {**data, "client_id": server.oauth_client_id}
        auth = None
        client_secret = CredentialCipher.decrypt(server.encrypted_oauth_client_secret)
        method = server.oauth_token_endpoint_auth_method or "client_secret_post"
        if client_secret and method == "client_secret_basic":
            auth = (server.oauth_client_id, client_secret)
            payload.pop("client_id", None)
        elif client_secret and method == "client_secret_post":
            payload["client_secret"] = client_secret
        try:
            with httpx.Client(
                transport=SafeSyncTransport(),
                timeout=self.REQUEST_TIMEOUT_SECONDS,
                follow_redirects=False,
                headers={"Accept": "application/json"},
            ) as client:
                response = client.post(server.oauth_token_url, data=payload, auth=auth)
                response.raise_for_status()
                token = response.json()
        except (httpx.HTTPError, ValueError) as error:
            raise FailException(f"OAuth token request failed: {error}") from None
        if not token.get("access_token"):
            raise FailException("OAuth token endpoint did not return access_token")
        return token

    def _save_token(self, server: McpServer, token: dict) -> None:
        expires_in = token.get("expires_in")
        expires_at = datetime.now() + timedelta(seconds=max(int(expires_in), 0)) if expires_in is not None else None
        scopes = token.get("scope") or []
        if isinstance(scopes, str):
            scopes = [scope for scope in scopes.split(" ") if scope]
        with self.db.auto_commit():
            server.encrypted_access_token = CredentialCipher.encrypt(token["access_token"])
            if token.get("refresh_token"):
                server.encrypted_refresh_token = CredentialCipher.encrypt(token["refresh_token"])
            server.oauth_token_type = token.get("token_type") or "Bearer"
            server.oauth_expires_at = expires_at
            server.oauth_granted_scopes = scopes
            server.oauth_authorized_at = datetime.now()
            server.oauth_last_error = ""
            server.status = "draft"

    @classmethod
    def _is_expiring(cls, server: McpServer) -> bool:
        return bool(
            server.oauth_expires_at
            and server.oauth_expires_at <= datetime.now() + timedelta(seconds=cls.REFRESH_SKEW_SECONDS)
        )

    @staticmethod
    def _validate_config(server: McpServer) -> None:
        if server.auth_type != "oauth2":
            raise ValidateErrorException("MCP server is not configured for OAuth 2.1")
        policy = OutboundSecurityPolicy.from_env()
        for url in (server.oauth_authorization_url, server.oauth_token_url):
            policy.validate_url(url)
        if not server.oauth_client_id:
            raise ValidateErrorException("OAuth client_id is required")

    def _get_server(self, server_id: UUID, account_id: UUID) -> McpServer:
        server = self.db.session.query(McpServer).filter(
            McpServer.id == server_id,
            McpServer.account_id == account_id,
        ).one_or_none()
        if server is None:
            raise NotFoundException("MCP server does not exist")
        return server

    @staticmethod
    def _state_key(state: str) -> str:
        return f"mcp:oauth:state:{state}"
