from __future__ import annotations

import time

import docker
from docker.errors import DockerException, ImageNotFound

from app.common.config import get_settings
from app.repositories.db import get_connection
from app.repositories.sandbox_execution_repository import SandboxExecutionRepository
from app.schemas.sandbox import SandboxRunRequest, SandboxRunResult
from app.security.command_policy import CommandPolicy


class DockerSandbox:
    """基于 Docker SDK 的一次性沙箱运行时。

    CLI / Sandbox 工具不直接在宿主机执行，而是创建短生命周期容器：
    创建容器 -> 启动 -> 等待完成或超时 -> 采集日志 -> 删除容器。
    """

    def __init__(self) -> None:
        self.settings = get_settings()
        self.client = docker.from_env()
        self.command_policy = CommandPolicy()

    def create(self, request: SandboxRunRequest):
        """创建受资源限制的容器，但暂不启动。"""
        self.command_policy.validate(request.command)
        return self.client.containers.create(
            image=request.image,
            command=request.command,
            working_dir=request.workdir,
            volumes=request.volumes,
            detach=True,
            mem_limit=request.mem_limit or self.settings.sandbox_mem_limit,
            network_disabled=request.network_disabled,
            pids_limit=request.pids_limit or self.settings.sandbox_pids_limit,
        )

    def execute(self, container, timeout_seconds: int) -> tuple[str, str, int | None, str]:
        """启动容器并等待结果；超时时主动终止容器。"""
        container.start()
        try:
            wait_result = container.wait(timeout=timeout_seconds)
            exit_code = int(wait_result.get("StatusCode", 1))
            status = "SUCCESS" if exit_code == 0 else "FAILED"
        except Exception:
            container.kill()
            exit_code = None
            status = "TIMEOUT"

        stdout = container.logs(stdout=True, stderr=False).decode("utf-8", errors="replace")
        stderr = container.logs(stdout=False, stderr=True).decode("utf-8", errors="replace")
        return stdout, stderr, exit_code, status

    def destroy(self, container) -> None:
        """清理容器，避免本地残留临时运行环境。"""
        try:
            container.remove(force=True) # 强制删除容器
        except DockerException:
            pass # 忽略删除失败（可能已被手动删除）

    def run_once(self, request: SandboxRunRequest) -> SandboxRunResult:
        """完整执行一次沙箱命令，并写入 sandbox_executions。"""
        timeout_seconds = min(
            int(request.timeout_seconds),
            int(self.settings.sandbox_timeout_seconds),
        )
        started_at = time.perf_counter()
        container = None

        try:
            # 创建容器（内部会做命令安全检查）
            container = self.create(request)
            # 执行并等待结果
            stdout, stderr, exit_code, status = self.execute(container, timeout_seconds)
            # 构建成功结果
            result = SandboxRunResult(
                command=" ".join(request.command),
                stdout=stdout,
                stderr=stderr,
                exit_code=exit_code,
                duration_ms=int((time.perf_counter() - started_at) * 1000),
                timeout_seconds=timeout_seconds,
                container_id=container.id,
                status=status,
                error_message="沙箱执行超时" if status == "TIMEOUT" else None,
            )
        except ImageNotFound as exc:
            # 处理镜像不存在的情况
            result = self._failed_result(request, started_at, f"镜像不存在或未拉取：{exc}")
        except Exception as exc:
            # 处理其他异常（包括 CommandPolicy 抛出的 ValueError）
            result = self._failed_result(
                request,
                started_at,
                f"{exc.__class__.__name__}: {exc}",
            )
        finally:
            # 无论如何都要清理容器
            if container is not None:
                self.destroy(container)

        # 如果有任务追踪信息，将执行结果写入数据库
        if request.run_id is not None and request.trace_id is not None:
            with get_connection() as connection:
                SandboxExecutionRepository(connection).create(
                    result=result,
                    task_id=request.task_id,
                    run_id=request.run_id,
                    trace_id=request.trace_id,
                    tool_name=request.tool_name,
                )

        return result

    def _failed_result(
        self,
        request: SandboxRunRequest,
        started_at: float,
        error_message: str,
    ) -> SandboxRunResult:
        return SandboxRunResult(
            command=" ".join(request.command),
            stdout="",
            stderr="",
            exit_code=None,
            duration_ms=int((time.perf_counter() - started_at) * 1000),
            timeout_seconds=request.timeout_seconds,
            container_id=None,
            status="FAILED",
            error_message=error_message,
        )
