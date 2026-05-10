from __future__ import annotations

import json
from typing import Any
from uuid import UUID

import anyio
import httpx

from app.common.config import get_settings
from app.schemas.tool import ToolResponse
from app.security.secret_manager import secret_resolver
from app.security.http_policy import HTTPPolicy
from app.tools.adapters.base import BaseToolAdapter


class HTTPToolAdapter(BaseToolAdapter):
    """调用普通 HTTP 工具。

    该适配器在发起请求前会执行 SSRF 防护、危险请求头检查和重定向校验。
    当前保持同步接口，避免提前扩大到 Dispatcher/API 的异步改造。
    """

    ALLOWED_METHODS = {"GET", "POST", "PUT", "PATCH", "DELETE"}
    RETRYABLE_METHODS = {"GET", "PUT"}
    RETRYABLE_STATUS_CODES = { # 可重试的状态码
        408,    # Request Timeout - 请求超时
        429,    # Too Many Requests - 速率限制
        500,    # Internal Server Error - 服务器错误
        502,    # Bad Gateway - 网关错误
        503,    # Service Unavailable - 服务不可用
        504     # Gateway Timeout - 网关超时
    }

    def __init__(self) -> None:
        self.settings = get_settings()
        self.policy = HTTPPolicy(self.settings.http_allowed_ports) # 配置读取允许的端口

    def call(
        self,
        tool: ToolResponse,
        tool_input: dict[str, Any],
        *,
        task_id: UUID | None = None,
        run_id: UUID | None = None,
        trace_id: UUID | None = None,
    ) -> dict[str, Any]:
        endpoint = tool.endpoint or ""
        if endpoint == "mock://echo":
            return {"echo": tool_input}

        # 方法校验
        method = str(tool_input.get("method", "GET")).upper()
        if method not in self.ALLOWED_METHODS:
            raise ValueError(f"HTTP adapter does not support method: {method}")

        # 构建 URL 并校验
        url = self._build_url(
            endpoint,
            tool_input.get("params") or {},
            tool_input.get("path_params") or {},
        )
        # 构建并过滤请求头
        headers = self._build_headers(tool_input.get("headers") or {})
        # 计算超时时间
        timeout = min(
            float(tool_input.get("timeout", self.settings.http_timeout_seconds)),
            self.settings.http_timeout_seconds,
        )
        body = secret_resolver.resolve(tool_input.get("json"))
        # 解析重试配置，得到最大重试次数
        retry_options = tool_input.get("retry") or {}
        max_retries = self._resolve_max_retries(method, retry_options)

        # 执行异步请求，当前函数不是异步函数，因此想要调用异步函数，得使用anyio.run
        response = anyio.run(
            self._send_with_retries,
            method,
            url,
            headers,
            body,
            timeout,
            max_retries,
        )
        return self._format_response(response)

    def _build_url(
        self,
        endpoint: str,
        params: dict[str, Any],
        path_params: dict[str, Any] | None = None,
    ) -> str:
        for name, value in (path_params or {}).items():
            endpoint = endpoint.replace("{" + str(name) + "}", str(value))
        self.policy.validate_url(endpoint) # SSRF 防护
        if not params:
            return endpoint
        return str(httpx.URL(endpoint).copy_merge_params(params))

    def _build_headers(self, user_headers: dict[str, Any]) -> dict[str, str]:
        # Content-Type 由适配器设置，用户不能通过 Host/Cookie 等危险头影响请求。
        headers = {"Content-Type": "application/json", **secret_resolver.resolve(user_headers)}
        return self.policy.sanitize_request_headers(headers) # 过滤危险头

    def _resolve_max_retries(self, method: str, retry_options: dict[str, Any]) -> int:
        # 显式禁用重试
        if retry_options.get("enabled") is False:
            return 0
        # 检查是否允许非幂等方法重试
        allow_non_idempotent = bool(retry_options.get("allow_non_idempotent", False))
        if method not in self.RETRYABLE_METHODS and not allow_non_idempotent:
            return 0
        # 限制最大重试次数
        requested = int(retry_options.get("max_retries", self.settings.http_max_retries))
        return max(0, min(requested, self.settings.http_max_retries))

    async def _send_with_retries(
        self,
        method: str,
        url: str,
        headers: dict[str, str],
        body: Any,
        timeout: float,
        max_retries: int,
    ) -> httpx.Response:
        """重试机制"""
        attempts = max_retries + 1  # 原始尝试 + 重试次数
        last_error: Exception | None = None
        last_response: httpx.Response | None = None

        for attempt in range(attempts):
            try:
                response = await self._send_once(
                    method,
                    url,
                    headers,
                    body,
                    timeout,
                )
                # 如果状态码不可重试，直接返回
                if response.status_code not in self.RETRYABLE_STATUS_CODES:
                    return response
                # 记录最后一次响应（可能返回给调用者）
                last_response = response
                last_error = ValueError(f"HTTP retryable status: {response.status_code}")
            except (httpx.ConnectError, httpx.ConnectTimeout, httpx.ReadTimeout) as exc:
                # 网络错误也可以重试
                last_error = exc

            # 指数退避等待
            if attempt < attempts - 1:
                await anyio.sleep(min(0.3 * (2**attempt), 1.5))
        # 所有重试都失败了
        if last_response is not None:
            return last_response    # 返回最后一次响应
        if last_error is not None:
            raise last_error        # 抛出最后一次的错误
        raise RuntimeError("HTTP request failed without response")

    async def _send_once(
        self,
        method: str,
        url: str,
        headers: dict[str, str],
        body: Any,
        timeout: float,
    ) -> httpx.Response:
        """单次请求执行"""
        current_url = url
        async with httpx.AsyncClient(
            timeout=timeout,
            follow_redirects=False, # 禁用自动跟随
            max_redirects=self.settings.http_max_redirects,
        ) as client:
            for redirect_count in range(self.settings.http_max_redirects + 1):
                # 每次请求前校验 URL（包括重定向后的）
                self.policy.validate_url(current_url)
                # 构建请求
                request = client.build_request(
                    method=method,
                    url=current_url,
                    headers=headers,
                    json=body if method in {"POST", "PUT", "PATCH"} else None,
                )
                # 发送请求（流式接收）
                response = await client.send(request, stream=True)

                # 如果不是重定向，读取响应并返回
                if not response.is_redirect:
                    return await self._read_limited_response(response)

                # 检查重定向次数
                if redirect_count >= self.settings.http_max_redirects:
                    await response.aclose()
                    raise ValueError("HTTP redirect limit exceeded")

                # 获取重定向目标
                location = response.headers.get("location")
                if not location:
                    await response.aclose()
                    raise ValueError("HTTP redirect response missing Location header")

                # 解析下一个 URL
                next_url = str(response.url.join(location))
                await response.aclose()
                # 检查 HTTPS → HTTP 降级
                # HTTPS → HTTP 降级的风险：1. 中间人攻击（MITM） 2. 数据泄露（明文传输） 3. 会话劫持
                if response.url.scheme == "https" and next_url.startswith("http://"):
                    raise ValueError("HTTP redirect downgrade from https to http is not allowed")
                # 校验重定向后的 URL（防 SSRF）
                self.policy.validate_url(next_url)
                current_url = next_url

        raise RuntimeError("HTTP redirect handling ended unexpectedly")

    async def _read_limited_response(self, response: httpx.Response) -> httpx.Response:
        """最多保存配置大小的响应体，避免单个超大 chunk 撑爆内存。"""
        limit = self.settings.http_max_response_bytes
        content = bytearray()
        truncated = False # 是否截断
        try:
            # 流式读取
            async for chunk in response.aiter_bytes():
                remaining = limit - len(content)
                if remaining <= 0:
                    truncated = True
                    break
                if len(chunk) > remaining:
                    content.extend(chunk[:remaining])
                    truncated = True
                    break
                content.extend(chunk)
            # 移除可能误导的头部
            headers = dict(response.headers)
            headers.pop("content-encoding", None) # Content-Length 是原始响应的大小，不是截断后的大小
            headers.pop("content-length", None) # Content-Encoding 可能导致解码错误（因为数据不完整）
            extensions = dict(response.extensions)
            extensions["toolhub_truncated"] = truncated
            return httpx.Response(
                status_code=response.status_code,
                headers=headers,
                content=bytes(content),
                request=response.request,
                extensions=extensions,
            )
        finally:
            await response.aclose()

    def _format_response(self, response: httpx.Response) -> dict[str, Any]:
        truncated = bool(response.extensions.get("toolhub_truncated", False))
        raw_body = response.content
        text_body = raw_body.decode(response.encoding or "utf-8", errors="replace")

        try:
            parsed_body: Any = json.loads(text_body)
        except json.JSONDecodeError:
            parsed_body = text_body

        return {
            "status_code": response.status_code,
            "final_url": str(response.url), # 最终 URL（可能有重定向）
            "headers": self.policy.redact_response_headers(dict(response.headers)), # 脱敏
            "body": parsed_body,
            "truncated": truncated, # 是否被截断v
        }
