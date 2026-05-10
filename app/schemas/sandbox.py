from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True)
class SandboxRunRequest:
    """Docker 沙箱执行请求。"""

    command: list[str]
    image: str
    timeout_seconds: int
    tool_name: str | None = None
    task_id: UUID | None = None
    run_id: UUID | None = None
    trace_id: UUID | None = None
    workdir: str | None = None # 容器内工作目录
    volumes: dict[str, dict[str, str]] | None = None # 只读挂载数据卷
    mem_limit: str | None = None # 内存限制
    network_disabled: bool = True # 是否可以联网
    pids_limit: int | None = None # 限制进程数
    language: str | None = None
    artifact_paths: list[str] | None = None


@dataclass(frozen=True)
class SandboxRunResult:
    """Docker 沙箱执行结果。"""

    command: str
    stdout: str
    stderr: str
    exit_code: int | None
    duration_ms: int
    timeout_seconds: int
    container_id: str | None
    status: str
    error_message: str | None = None
    language: str | None = None
    artifacts: list[dict[str, str]] | None = None
