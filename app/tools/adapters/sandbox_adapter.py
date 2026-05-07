from __future__ import annotations

import subprocess
from typing import Any

from app.schemas.tool import ToolResponse
from app.tools.adapters.base import BaseToolAdapter


class SandboxToolAdapter(BaseToolAdapter):
    """Sandbox 工具适配器。

    目前先支持 Python 代码 demo；后续会切换到 DockerSandbox 并记录 sandbox_executions。
    """

    def call(self, tool: ToolResponse, tool_input: dict[str, Any]) -> dict[str, Any]:
        code = str(tool_input.get("code") or tool_input.get("value") or "")
        if not code:
            raise ValueError("sandbox python demo requires code")

        if self._contains_dangerous_code(code):
            raise ValueError("sandbox code contains dangerous pattern")

        completed = subprocess.run(
            ["python", "-c", code],
            capture_output=True,
            text=True,
            timeout=min(int(tool_input.get("timeout", 10)), 30),
            check=False,
        )
        return {
            "language": "python",
            "stdout": completed.stdout,
            "stderr": completed.stderr,
            "exit_code": completed.returncode,
        }

    def _contains_dangerous_code(self, code: str) -> bool:
        dangerous_patterns = ["os.remove", "shutil.rmtree", "subprocess", "socket", "open("]
        return any(pattern in code for pattern in dangerous_patterns)
