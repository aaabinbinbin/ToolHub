from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlparse


class HTTPPolicy:
    """HTTP 工具调用安全策略。

    这层主要防 SSRF：不允许 HTTP 工具访问 localhost、内网、链路本地地址、
    云厂商元数据地址或非白名单端口。重定向后的 URL 也必须重新校验。
    """

    BLOCKED_HEADER_NAMES = {
        "authorization",        # 防止携带认证令牌
        "cookie",               # 防止会话劫持
        "host",                 # 防止 Host 头注入
        "proxy-authorization",  # 防止代理认证
        "x-forwarded-for",      # 防止 IP 伪造
        "x-real-ip",            # 防止 IP 伪造
        "forwarded",            # 防止代理链伪造
        "connection",           # 防止连接升级攻击
        "transfer-encoding",    # 防止 HTTP 走私
        "content-length",       # 防止长度篡改
    }
    SENSITIVE_RESPONSE_HEADERS = {
        "authorization",
        "cookie",
        "proxy-authorization",
        "set-cookie", # 服务器设置的 Cookie
    }

    def __init__(self, allowed_ports: tuple[int, ...]) -> None:
        self.allowed_ports = allowed_ports # 只允许标准 HTTP/HTTPS 端口

    def validate_url(self, url: str) -> None:
        """校验 URL scheme、认证信息、端口和 DNS 解析后的 IP。"""
        parsed = urlparse(url)
        # 协议检查
        if parsed.scheme not in {"http", "https"}:
            raise ValueError("HTTP tool endpoint must use http or https")
        # 主机名检查
        if not parsed.hostname:
            raise ValueError("HTTP tool endpoint must include hostname")
        # 认证信息检查 【防止硬编码凭证泄露、避免凭证出现在日志中、强制使用 Header 方式传递认证（可被审计）】
        if parsed.username or parsed.password:
            raise ValueError("HTTP tool endpoint must not include credentials")

        # 端口检查
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
        if port not in self.allowed_ports:
            raise ValueError(f"HTTP tool port is not allowed: {port}")

        # IP 地址检查：
        #   DNS 解析：将域名解析为 IP 地址
        #   IP 校验：检查每个 IP 是否是内网/敏感地址
        for ip_address in self._resolve_hostname(parsed.hostname, port):
            self._validate_ip(ip_address)

    def sanitize_request_headers(self, headers: dict[str, object]) -> dict[str, str]:
        """过滤危险请求头，避免伪造 Host、携带 Cookie 或把密钥写入审计表。"""
        safe_headers: dict[str, str] = {}
        for name, value in headers.items():
            normalized = name.lower()
            if normalized in self.BLOCKED_HEADER_NAMES:
                raise ValueError(f"HTTP request header is not allowed: {name}")
            safe_headers[name] = str(value)
        return safe_headers

    def redact_response_headers(self, headers: dict[str, str]) -> dict[str, str]:
        """响应头入库前脱敏，避免 Set-Cookie 等敏感信息进入审计数据。"""
        redacted: dict[str, str] = {}
        for name, value in headers.items():
            if name.lower() in self.SENSITIVE_RESPONSE_HEADERS:
                redacted[name] = "***REDACTED***"
            else:
                redacted[name] = value
        return redacted

    def _resolve_hostname(
        self, hostname: str, port: int
    ) -> list[ipaddress.IPv4Address | ipaddress.IPv6Address]:
        try:
            # 使用 getaddrinfo 而非 gethostbyname，以便支持 IPv4 和 IPv6
            infos = socket.getaddrinfo(hostname, port, type=socket.SOCK_STREAM)
        except socket.gaierror as exc:
            raise ValueError(f"HTTP tool hostname cannot be resolved: {hostname}") from exc

        addresses = []
        for info in infos:
            addresses.append(ipaddress.ip_address(info[4][0]))
        return addresses

    def _validate_ip(self, ip_address: ipaddress.IPv4Address | ipaddress.IPv6Address) -> None:
        if (
            ip_address.is_private           # 私有地址（内网）
            or ip_address.is_loopback       # 回环地址（127.0.0.1）
            or ip_address.is_link_local     # 链路本地地址（169.254.x.x）
            or ip_address.is_multicast      # 组播地址
            or ip_address.is_reserved       # 保留地址
            or ip_address.is_unspecified    # 未指定地址（0.0.0.0）
        ):
            raise ValueError(f"HTTP tool target IP is not allowed: {ip_address}")
