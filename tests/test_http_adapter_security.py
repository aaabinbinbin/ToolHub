from __future__ import annotations

import pytest

from app.security.http_policy import HTTPPolicy


def make_policy() -> HTTPPolicy:
    return HTTPPolicy(allowed_ports=(80, 443))


def test_reject_private_ip() -> None:
    """内网 IP 必须被拒绝。"""
    policy = make_policy()
    with pytest.raises(ValueError):
        policy.validate_url("http://10.0.0.1/api")


def test_reject_loopback() -> None:
    """回环地址必须被拒绝。"""
    policy = make_policy()
    with pytest.raises(ValueError):
        policy.validate_url("http://127.0.0.1/api")


def test_reject_localhost_hostname() -> None:
    """localhost 域名解析后应为回环地址，必须拒绝。"""
    policy = make_policy()
    with pytest.raises(ValueError):
        policy.validate_url("http://localhost:80/api")


def test_reject_metadata_ip_169_254() -> None:
    """AWS/GC/Azure 元数据 IP 169.254.169.254 必须拒绝。"""
    policy = make_policy()
    with pytest.raises(ValueError):
        policy.validate_url("http://169.254.169.254/latest/meta-data/")


def test_reject_link_local() -> None:
    """链路本地地址 169.254.x.x 必须拒绝。"""
    policy = make_policy()
    with pytest.raises(ValueError):
        policy.validate_url("http://169.254.1.1/")


def test_reject_metadata_hostname() -> None:
    """GCP 元数据 hostname 必须被拒绝。"""
    policy = make_policy()
    with pytest.raises(ValueError):
        policy.validate_url("http://metadata.google.internal/")


def test_allow_public_https() -> None:
    """正常公网 HTTPS 地址应允许。"""
    policy = make_policy()
    # 公网地址 DNS 解析可能不稳定，这里只验证不因 hostname/port 被拒
    # URL 格式检查应通过（除了 DNS 解析可能失败）
    try:
        policy.validate_url("https://httpbin.org/get")
    except ValueError as e:
        # 如果 DNS 解析失败（本地无网络），这是环境问题而非策略问题
        if "cannot be resolved" not in str(e).lower():
            raise


def test_reject_non_standard_port() -> None:
    """非标准端口应拒绝。"""
    policy = make_policy()
    with pytest.raises(ValueError):
        policy.validate_url("http://example.com:8080/api")


def test_sanitize_blocks_dangerous_headers() -> None:
    """sanitize_request_headers 应拦截 Host/Cookie 等危险头。"""
    policy = make_policy()
    with pytest.raises(ValueError):
        policy.sanitize_request_headers({"Host": "evil.com"})


def test_sanitize_allows_auth_headers() -> None:
    """sanitize_request_headers 应允许 Authorization 等认证头。"""
    policy = make_policy()
    headers = policy.sanitize_request_headers({"Authorization": "Bearer tok", "X-Api-Key": "key"})
    assert "Authorization" in headers
    assert "X-Api-Key" in headers
