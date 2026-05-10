from __future__ import annotations

from typing import Any
from uuid import UUID

from app.common.config import get_settings
from app.infra.docker_sandbox import DockerSandbox
from app.schemas.sandbox import SandboxRunRequest
from app.schemas.tool import ToolResponse
from app.tools.adapters.base import BaseToolAdapter, ToolAdapterExecutionError


class SandboxToolAdapter(BaseToolAdapter):
    """Sandbox 工具适配器，支持 Python / Node.js 代码执行骨架。"""

    def __init__(self) -> None:
        self.settings = get_settings()
        self.sandbox = DockerSandbox()

    def call(
        self,
        tool: ToolResponse,
        tool_input: dict[str, Any],
        *,
        task_id: UUID | None = None,
        run_id: UUID | None = None,
        trace_id: UUID | None = None,
    ) -> dict[str, Any]:
        language = str(tool_input.get("language") or tool.endpoint or "python").lower()
        code = str(tool_input.get("code") or tool_input.get("value") or "")
        if not code:
            raise ValueError("sandbox tool requires code")

        command, image = self._runtime(language, code)

        result = self.sandbox.run_once(
            SandboxRunRequest(
                command=command,
                image=image,
                timeout_seconds=int(tool_input.get("timeout", 10)),
                tool_name=tool.name,
                task_id=task_id,
                run_id=run_id,
                trace_id=trace_id,
                mem_limit=self.settings.sandbox_mem_limit,
                network_disabled=self.settings.sandbox_network_disabled,
                pids_limit=self.settings.sandbox_pids_limit,
                language=language,
                artifact_paths=tool_input.get("artifact_paths") or [],
            )
        )
        output = {
            "language": language,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "exit_code": result.exit_code,
            "sandbox_status": result.status,
            "container_id": result.container_id,
            "artifacts": result.artifacts or [],
        }
        if result.status != "SUCCESS":
            raise ToolAdapterExecutionError(
                result.error_message or result.stderr or "Python sandbox execution failed",
                output,
            )
        return output

    def _runtime(self, language: str, code: str) -> tuple[list[str], str]:
        """根据语言选择运行时命令和镜像。"""
        if language in {"python", "py"}:
            return ["python", "-c", code], self.settings.sandbox_python_image
        if language in {"node", "nodejs", "javascript", "js"}:
            return ["node", "-e", code], self.settings.sandbox_node_image
        raise ValueError(f"Unsupported sandbox language: {language}")
