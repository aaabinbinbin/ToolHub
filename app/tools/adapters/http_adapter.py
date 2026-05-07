from __future__ import annotations

import json
from typing import Any
from urllib import parse, request

from app.tools.adapters.base import BaseToolAdapter
from app.schemas.tool import ToolResponse


class HTTPToolAdapter(BaseToolAdapter):
    """调用普通 HTTP 工具。

    MVP 支持 GET 和 POST JSON。为了本地 demo，也支持 `mock://echo`。
    """

    def call(self, tool: ToolResponse, tool_input: dict[str, Any]) -> dict[str, Any]:
        endpoint = tool.endpoint or ""
        if endpoint == "mock://echo":
            return {"echo": tool_input}

        if not endpoint.startswith(("http://", "https://")):
            raise ValueError("HTTP tool endpoint must start with http:// or https://")

        method = str(tool_input.get("method", "GET")).upper()
        timeout = min(int(tool_input.get("timeout", 10)), 30)
        headers = {"Content-Type": "application/json", **tool_input.get("headers", {})}
        params = tool_input.get("params") or {}
        body = tool_input.get("json")

        url = endpoint
        if params:
            url = f"{endpoint}?{parse.urlencode(params)}"

        data = None
        if method == "POST":
            data = json.dumps(body or {}).encode("utf-8")
        elif method != "GET":
            raise ValueError("HTTP adapter only supports GET and POST in MVP")

        http_request = request.Request(url=url, method=method, headers=headers, data=data)
        with request.urlopen(http_request, timeout=timeout) as response:
            raw_body = response.read(1024 * 1024).decode("utf-8", errors="replace")
            try:
                parsed_body: Any = json.loads(raw_body)
            except json.JSONDecodeError:
                parsed_body = raw_body
            return {
                "status_code": response.status,
                "headers": dict(response.headers),
                "body": parsed_body,
            }
