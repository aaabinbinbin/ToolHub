from __future__ import annotations

from pathlib import Path


DEFAULT_INSTRUCTIONS = """# TOOLHUB.md

## 项目背景

ToolHub 是一个面向 CLI / IDE Agent 的 Agent Harness 平台，用于安全地路由和执行工具。

## 安全规则

- 不允许删除宿主机文件。
- 不允许在没有明确许可的情况下执行破坏性命令。
- 对 Agent 生成的代码和命令，优先使用沙箱执行。
"""


class InstructionLoader:
    """加载 ToolHub 项目级指令。

    AgentHarness 在执行任务前需要读取项目规则、安全约束和输出偏好。
    当前约定从项目根目录的 `TOOLHUB.md` 读取；如果文件不存在，则使用默认安全规则。
    """

    def __init__(self, project_root: Path | None = None) -> None:
        """创建指令加载器。

        Args:
            project_root: 项目根目录。不传时使用当前工作目录。
        """
        self.project_root = project_root or Path.cwd()
        self._cached_path: Path | None = None
        self._cached_mtime_ns: int | None = None
        self._cached_content: str | None = None

    def load(self) -> str:
        """读取 `TOOLHUB.md` 内容。

        Returns:
            项目指令文本；当文件不存在时返回默认安全规则。
        """
        instruction_path = self.project_root / "TOOLHUB.md"
        if not instruction_path.exists():
            return DEFAULT_INSTRUCTIONS

        mtime_ns = instruction_path.stat().st_mtime_ns
        if (
            self._cached_path == instruction_path
            and self._cached_mtime_ns == mtime_ns
            and self._cached_content is not None
        ):
            return self._cached_content

        content = instruction_path.read_text(encoding="utf-8")
        self._cached_path = instruction_path
        self._cached_mtime_ns = mtime_ns
        self._cached_content = content
        return content
