from __future__ import annotations

import subprocess
from typing import Any

from app.schemas.tool import ToolResponse
from app.tools.adapters.base import BaseToolAdapter


class CLIToolAdapter(BaseToolAdapter):
    """CLI 工具适配器。

    Day 4 为了验证调用链路，先支持少量只读白名单命令。
    Day 5 会接入 DockerSandbox，避免裸跑宿主机命令。
    """

    SAFE_COMMANDS = {
        "git status": ["git", "status", "--short"],
        "git status --short": ["git", "status", "--short"],
    }

    def call(self, tool: ToolResponse, tool_input: dict[str, Any]) -> dict[str, Any]:
        command = str(tool_input.get("command") or tool.endpoint or "").strip()
        command_args = self.SAFE_COMMANDS.get(command)
        if command_args is None:
            raise ValueError("CLI command is not in MVP whitelist")

        completed = subprocess.run(
            command_args,
            capture_output=True,
            text=True,
            timeout=min(int(tool_input.get("timeout", 10)), 30),
            check=False,
        )
        return {
            "command": command,
            "stdout": completed.stdout,
            "stderr": completed.stderr,
            "exit_code": completed.returncode,
        }
