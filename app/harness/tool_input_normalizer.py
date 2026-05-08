from __future__ import annotations

from typing import Any

from app.schemas.tool import ToolResponse, ToolType


class ToolInputNormalizer:
    """把 LLM 生成的 tool_input 归一化为各类 Adapter 可接受的结构。

    这里不再从用户自然语言里用正则猜参数。LLM 负责给出候选 tool_input，
    Harness 只做轻量结构修正，最终安全校验仍然由 Adapter / Policy 完成。
    """

    def normalize(
        self,
        *,
        tool: ToolResponse,
        tool_input: dict[str, Any],
    ) -> dict[str, Any]:
        normalized = dict(tool_input)
        if tool.tool_type == ToolType.CLI:
            return self._normalize_cli(tool, normalized)
        if tool.tool_type == ToolType.SANDBOX:
            return self._normalize_sandbox(normalized)
        if tool.tool_type == ToolType.MCP:
            return self._normalize_mcp(normalized)
        return normalized

    def _normalize_cli(
        self,
        tool: ToolResponse,
        tool_input: dict[str, Any],
    ) -> dict[str, Any]:
        if "rule_id" not in tool_input and "command" not in tool_input:
            tool_input["rule_id"] = tool.endpoint
        return tool_input

    def _normalize_sandbox(self, tool_input: dict[str, Any]) -> dict[str, Any]:
        if "code" not in tool_input and tool_input.get("code_hint"):
            tool_input["code"] = tool_input["code_hint"]
        return tool_input

    def _normalize_mcp(self, tool_input: dict[str, Any]) -> dict[str, Any]:
        if "expression" not in tool_input:
            for key in ("value", "query", "input"):
                if tool_input.get(key):
                    tool_input["expression"] = str(tool_input[key])
                    break
        return tool_input
