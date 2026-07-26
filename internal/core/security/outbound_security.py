#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Security policy and bounded transports for untrusted outbound URLs."""

import ipaddress
import os
import socket
from dataclasses import dataclass
from urllib.parse import urlsplit

import httpx

from internal.exception import ValidateErrorException


class OutboundSecurityError(ValidateErrorException):
    """Raised when an outbound destination violates the SSRF policy."""


@dataclass(frozen=True)
class OutboundSecurityPolicy:
    allow_private_networks: bool
    require_https: bool
    allowed_ports: frozenset[int]
    allowed_hosts: frozenset[str]
    max_response_bytes: int

    @classmethod
    def from_env(cls) -> "OutboundSecurityPolicy":
        return cls(
            allow_private_networks=cls._env_bool("MCP_ALLOW_PRIVATE_NETWORKS", False),
            require_https=cls._env_bool("MCP_REQUIRE_HTTPS", True),
            allowed_ports=cls._parse_ports(os.getenv("MCP_OUTBOUND_ALLOWED_PORTS", "443")),
            allowed_hosts=frozenset(
                cls._normalize_hostname(item)
                for item in os.getenv("MCP_OUTBOUND_HOST_ALLOWLIST", "").split(",")
                if item.strip()
            ),
            max_response_bytes=max(int(os.getenv("MCP_MAX_RESPONSE_BYTES", str(10 * 1024 * 1024))), 1024),
        )

    def validate_url(self, url: str) -> tuple[str, tuple[str, ...]]:
        try:
            parsed = urlsplit(url)
            port = parsed.port
        except ValueError as error:
            raise OutboundSecurityError("Outbound URL is invalid") from error
        if parsed.scheme not in {"http", "https"}:
            raise OutboundSecurityError("Only HTTP/HTTPS outbound URLs are allowed")
        if self.require_https and parsed.scheme != "https":
            raise OutboundSecurityError("HTTPS is required for MCP outbound requests")
        if not parsed.hostname or parsed.username is not None or parsed.password is not None:
            raise OutboundSecurityError("Outbound URL must not contain credentials")
        hostname = self._normalize_hostname(parsed.hostname)
        if hostname in {"localhost", "localhost.localdomain"} or hostname.endswith(".localhost"):
            if not self.allow_private_networks:
                raise OutboundSecurityError("Local and private network destinations are blocked")
        effective_port = port or (443 if parsed.scheme == "https" else 80)
        if self.allowed_ports and effective_port not in self.allowed_ports:
            raise OutboundSecurityError("Outbound destination port is not allowed")
        if self.allowed_hosts and not self._host_is_allowed(hostname):
            raise OutboundSecurityError("Outbound destination host is not allowlisted")
        addresses = self._resolve(hostname, effective_port)
        if not addresses:
            raise OutboundSecurityError("Outbound destination could not be resolved")
        if not self.allow_private_networks:
            for address in addresses:
                if not ipaddress.ip_address(address).is_global:
                    raise OutboundSecurityError("Local, private and reserved network destinations are blocked")
        return hostname, addresses

    def validate_redirect(self, response: httpx.Response, request_url: httpx.URL | None = None) -> None:
        if response.is_redirect:
            location = response.headers.get("location", "")
            if location:
                base_url = request_url or response.request.url
                self.validate_url(str(base_url.join(location)))
            raise OutboundSecurityError("Outbound HTTP redirects are disabled")

    def _host_is_allowed(self, hostname: str) -> bool:
        for pattern in self.allowed_hosts:
            if pattern.startswith("*."):
                suffix = pattern[1:]
                if hostname.endswith(suffix) and hostname != suffix[1:]:
                    return True
            elif hostname == pattern:
                return True
        return False

    @staticmethod
    def _resolve(hostname: str, port: int) -> tuple[str, ...]:
        try:
            records = socket.getaddrinfo(hostname, port, type=socket.SOCK_STREAM)
        except socket.gaierror as error:
            raise OutboundSecurityError("Outbound destination could not be resolved") from error
        return tuple(sorted({record[4][0].split("%", 1)[0] for record in records}))

    @staticmethod
    def _normalize_hostname(hostname: str) -> str:
        value = hostname.strip().rstrip(".").lower()
        try:
            return value.encode("idna").decode("ascii")
        except UnicodeError as error:
            raise OutboundSecurityError("Outbound hostname is invalid") from error

    @staticmethod
    def _parse_ports(value: str) -> frozenset[int]:
        ports = set()
        for item in value.split(","):
            if not item.strip():
                continue
            try:
                port = int(item.strip())
            except ValueError as error:
                raise OutboundSecurityError("MCP_OUTBOUND_ALLOWED_PORTS is invalid") from error
            if port < 1 or port > 65535:
                raise OutboundSecurityError("MCP_OUTBOUND_ALLOWED_PORTS is invalid")
            ports.add(port)
        return frozenset(ports)

    @staticmethod
    def _env_bool(name: str, default: bool) -> bool:
        value = os.getenv(name)
        return default if value is None else value.strip().lower() == "true"


class _LimitedAsyncStream(httpx.AsyncByteStream):
    def __init__(self, stream: httpx.AsyncByteStream, limit: int):
        self._stream = stream
        self._limit = limit
        self._received = 0

    async def __aiter__(self):
        async for chunk in self._stream:
            self._received += len(chunk)
            if self._received > self._limit:
                raise OutboundSecurityError("MCP response exceeded the configured size limit")
            yield chunk

    async def aclose(self) -> None:
        await self._stream.aclose()


class SafeAsyncTransport(httpx.AsyncBaseTransport):
    def __init__(self, policy: OutboundSecurityPolicy | None = None, transport: httpx.AsyncBaseTransport | None = None):
        self.policy = policy or OutboundSecurityPolicy.from_env()
        self._transport = transport or httpx.AsyncHTTPTransport(retries=0, trust_env=False)

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        self.policy.validate_url(str(request.url))
        request.headers["Accept-Encoding"] = "identity"
        response = await self._transport.handle_async_request(request)
        if response.is_redirect:
            await response.aclose()
            self.policy.validate_redirect(response, request.url)
        content_length = response.headers.get("content-length")
        if content_length and int(content_length) > self.policy.max_response_bytes:
            await response.aclose()
            raise OutboundSecurityError("MCP response exceeded the configured size limit")
        response.stream = _LimitedAsyncStream(response.stream, self.policy.max_response_bytes)
        return response

    async def aclose(self) -> None:
        await self._transport.aclose()


class _LimitedSyncStream(httpx.SyncByteStream):
    def __init__(self, stream: httpx.SyncByteStream, limit: int):
        self._stream = stream
        self._limit = limit
        self._received = 0

    def __iter__(self):
        for chunk in self._stream:
            self._received += len(chunk)
            if self._received > self._limit:
                raise OutboundSecurityError("OAuth response exceeded the configured size limit")
            yield chunk

    def close(self) -> None:
        self._stream.close()


class SafeSyncTransport(httpx.BaseTransport):
    def __init__(self, policy: OutboundSecurityPolicy | None = None, transport: httpx.BaseTransport | None = None):
        self.policy = policy or OutboundSecurityPolicy.from_env()
        self._transport = transport or httpx.HTTPTransport(retries=0, trust_env=False)

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        self.policy.validate_url(str(request.url))
        request.headers["Accept-Encoding"] = "identity"
        response = self._transport.handle_request(request)
        if response.is_redirect:
            response.close()
            self.policy.validate_redirect(response, request.url)
        content_length = response.headers.get("content-length")
        if content_length and int(content_length) > self.policy.max_response_bytes:
            response.close()
            raise OutboundSecurityError("OAuth response exceeded the configured size limit")
        response.stream = _LimitedSyncStream(response.stream, self.policy.max_response_bytes)
        return response

    def close(self) -> None:
        self._transport.close()
