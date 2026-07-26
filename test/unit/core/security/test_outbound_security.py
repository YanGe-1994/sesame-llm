import socket

import httpx
import pytest

from internal.core.security.outbound_security import (
    OutboundSecurityError,
    OutboundSecurityPolicy,
    SafeSyncTransport,
)


def make_policy(**overrides):
    values = {
        "allow_private_networks": False,
        "require_https": True,
        "allowed_ports": frozenset({443}),
        "allowed_hosts": frozenset(),
        "max_response_bytes": 1024,
    }
    values.update(overrides)
    return OutboundSecurityPolicy(**values)


def install_dns(monkeypatch, *addresses):
    records = [
        (socket.AF_INET6 if ":" in address else socket.AF_INET, socket.SOCK_STREAM, 6, "", (address, 443))
        for address in addresses
    ]
    monkeypatch.setattr(socket, "getaddrinfo", lambda *args, **kwargs: records)


def test_allows_public_https_destination(monkeypatch):
    install_dns(monkeypatch, "93.184.216.34")
    hostname, addresses = make_policy().validate_url("https://example.com/mcp")
    assert hostname == "example.com"
    assert addresses == ("93.184.216.34",)


@pytest.mark.parametrize("address", [
    "127.0.0.1", "10.0.0.1", "172.16.0.1", "192.168.1.1",
    "169.254.169.254", "::1", "fc00::1", "fe80::1", "::ffff:127.0.0.1",
])
def test_blocks_non_global_destinations(monkeypatch, address):
    install_dns(monkeypatch, address)
    with pytest.raises(OutboundSecurityError):
        make_policy().validate_url("https://attacker.example/mcp")


def test_blocks_http_credentials_and_unapproved_port(monkeypatch):
    install_dns(monkeypatch, "93.184.216.34")
    policy = make_policy()
    with pytest.raises(OutboundSecurityError):
        policy.validate_url("http://example.com/mcp")
    with pytest.raises(OutboundSecurityError):
        policy.validate_url("https://user:password@example.com/mcp")
    with pytest.raises(OutboundSecurityError):
        policy.validate_url("https://example.com:8443/mcp")


def test_private_network_requires_explicit_development_policy(monkeypatch):
    install_dns(monkeypatch, "127.0.0.1")
    policy = make_policy(
        allow_private_networks=True,
        require_https=False,
        allowed_ports=frozenset({8000}),
    )
    policy.validate_url("http://localhost:8000/mcp")


def test_host_allowlist_is_exact_or_explicit_wildcard(monkeypatch):
    install_dns(monkeypatch, "93.184.216.34")
    policy = make_policy(allowed_hosts=frozenset({"api.example.com", "*.trusted.example"}))
    policy.validate_url("https://api.example.com/mcp")
    policy.validate_url("https://tools.trusted.example/mcp")
    with pytest.raises(OutboundSecurityError):
        policy.validate_url("https://example.com/mcp")


def test_transport_rejects_redirect(monkeypatch):
    install_dns(monkeypatch, "93.184.216.34")
    inner = httpx.MockTransport(
        lambda request: httpx.Response(302, headers={"Location": "https://example.com/other"})
    )
    with httpx.Client(transport=SafeSyncTransport(make_policy(), inner)) as client:
        with pytest.raises(OutboundSecurityError):
            client.get("https://example.com/mcp")


def test_transport_limits_response_size(monkeypatch):
    install_dns(monkeypatch, "93.184.216.34")
    inner = httpx.MockTransport(lambda request: httpx.Response(200, content=b"x" * 2048))
    with httpx.Client(transport=SafeSyncTransport(make_policy(max_response_bytes=1024), inner)) as client:
        with pytest.raises(OutboundSecurityError):
            client.get("https://example.com/mcp")
