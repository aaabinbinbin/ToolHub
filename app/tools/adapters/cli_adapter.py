from __future__ import annotations

from pathlib import Path
from typing import Any
from uuid import UUID

from app.common.config import get_settings
from app.infra.docker_sandbox import DockerSandbox
from app.schemas.sandbox import SandboxRunRequest
from app.schemas.tool import ToolResponse
from app.security.cli_policy import CLICommandPolicy
from app.tools.adapters.base import BaseToolAdapter, ToolAdapterExecutionError


class CLIToolAdapter(BaseToolAdapter):
    """CLI 工具适配器，默认通过 DockerSandbox 隔离执行。"""

    def __init__(self) -> None:
        self.settings = get_settings()
        self.sandbox = DockerSandbox()
        self.cli_policy = CLICommandPolicy()

    def call(
        self,
        tool: ToolResponse,
        tool_input: dict[str, Any],
        *,
        task_id: UUID | None = None,
        run_id: UUID | None = None,
        trace_id: UUID | None = None,
    ) -> dict[str, Any]:
        # 从 rule_id / endpoint 解析 CLI 规则，再用结构化 args 生成 argv。
        # 兼容期仍支持旧 command="git status --short" 写法，但内部会映射为规则 ID。
        plan = self.cli_policy.build_plan(endpoint=tool.endpoint, tool_input=tool_input)
        rule = plan.rule

        result = self.sandbox.run_once(
            SandboxRunRequest(
                command=plan.argv,
                image=rule.image or self.settings.sandbox_cli_image,
                timeout_seconds=min(
                    int(tool_input.get("timeout", rule.timeout_seconds)),
                    rule.timeout_seconds,
                ),
                tool_name=tool.name,
                task_id=task_id,
                run_id=run_id,
                trace_id=trace_id,
                workdir=rule.workdir,
                volumes=self._build_volumes(rule),
                mem_limit=rule.mem_limit or self.settings.sandbox_mem_limit,
                network_disabled=rule.network_disabled,
                pids_limit=rule.pids_limit or self.settings.sandbox_pids_limit,
            )
        )
        output = {
            "rule_id": rule.id,
            "command": plan.display_command,
            "argv": plan.argv,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "exit_code": result.exit_code,
            "sandbox_status": result.status,
            "container_id": result.container_id,
        }
        if result.status != "SUCCESS":
            raise ToolAdapterExecutionError(
                result.error_message or result.stderr or "CLI sandbox execution failed",
                output,
            )
        return output

    def _build_volumes(self, rule) -> dict[str, dict[str, str]] | None:
        if not rule.mount_workspace:
            return None
        mode = "ro" if rule.readonly_workspace else "rw"
        return {str(Path.cwd()): {"bind": "/workspace", "mode": mode}}
