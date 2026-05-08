from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Literal


ParamType = Literal["bool", "enum", "int", "path", "string"]
Effect = Literal["ALLOW", "ASK", "DENY"]


@dataclass(frozen=True)
class CLIParamRule:
    """CLI 规则中的单个结构化参数定义。"""

    type: ParamType
    default: Any = None
    flag: str | None = None # 对应的命令行标志（如 --staged）
    choices: tuple[str, ...] = () # choices: 枚举值的白名单
    min_value: int | None = None
    max_value: int | None = None
    max_length: int = 120
    allow_absolute: bool = False
    allow_parent: bool = False


@dataclass(frozen=True)
class CLICommandRule:
    """一条可执行 CLI 规则。

    Adapter 只接受规则 ID 和结构化参数，再由规则生成 argv，避免直接执行 LLM 给出的命令字符串。
    """

    id: str
    description: str
    effect: Effect # 权限状态。ALLOW（直接执行）、ASK（需人工确认）、DENY（禁止）
    risk_level: str
    image: str
    argv_template: list[str] # 命令的固定部分（如 ["git", "diff"]）。
    params: dict[str, CLIParamRule] = field(default_factory=dict)
    workdir: str = "/workspace"
    mount_workspace: bool = True
    readonly_workspace: bool = True
    network_disabled: bool = True
    timeout_seconds: int = 10
    mem_limit: str | None = None
    pids_limit: int | None = None


@dataclass(frozen=True)
class CLICommandPlan:
    """CLI 规则解析后的执行计划。"""

    rule: CLICommandRule
    argv: list[str]
    display_command: str


class CLICommandPolicy:
    """CLI 工具规则策略。

    当前先内置少量安全只读规则；后续可以扩展为读取 config/cli_policy.yaml。
    """
    # todo 待后续扩展命令
    LEGACY_RULE_IDS = {
        "git status": "cli://git/status-short",
        "git status --short": "cli://git/status-short",
    }
    SHELL_TOKENS = {";", "&&", "||", "|", "`", "$(", ">", "<", "\n", "\r"}

    def __init__(self) -> None:
        self.rules = self._default_rules()

    def build_plan(
        self,
        *,
        endpoint: str | None,
        tool_input: dict[str, Any],
    ) -> CLICommandPlan:
        """根据 endpoint / rule_id 解析规则，并用结构化 args 生成 argv。"""
        # 获取规则 ID
        raw_rule_id = str(
            tool_input.get("rule_id") or tool_input.get("command") or endpoint or ""
        ).strip()
        rule_id = self.LEGACY_RULE_IDS.get(raw_rule_id, raw_rule_id)
        # Shell 语法拦截
        self._reject_shell_syntax(raw_rule_id)

        # 根据rule_id查找规则对象
        rule = self.rules.get(rule_id)
        if rule is None:
            raise ValueError(f"CLI rule is not allowed: {raw_rule_id}")
        # 校验规则权限
        if rule.effect != "ALLOW":
            raise ValueError(f"CLI rule is not executable without approval: {rule.id}")
        # 拿到参数
        args = tool_input.get("args") or {}
        if not isinstance(args, dict):
            raise ValueError("CLI args must be an object")
        # 获取对应规则的参数模板
        argv = list(rule.argv_template)
        # 将 argv_template（固定部分）和 _build_args 的结果（动态部分）拼在一起，形成最终的 argv。
        argv.extend(self._build_args(rule, args))
        return CLICommandPlan(
            rule=rule,
            argv=argv,
            display_command=self._display_command(rule.id, args),
        )

    def _build_args(self, rule: CLICommandRule, args: dict[str, Any]) -> list[str]:
        """负责将字典转换成 Shell 能懂的参数列表，同时做严格的类型检查。"""
        # 如果用户传了一个规则里没定义的参数，直接报错。这防止了用户通过隐藏参数攻击底层命令。
        unknown_args = set(args) - set(rule.params)
        if unknown_args:
            raise ValueError(f"CLI args contain unknown keys: {sorted(unknown_args)}")

        argv: list[str] = []
        for name, param_rule in rule.params.items():
            value = args.get(name, param_rule.default)
            # 参数为空，返回None
            if value is None:
                continue
            # 只有当值为 True 且有 flag 时，才往列表里加标志（如 --staged）
            if param_rule.type == "bool":
                if not isinstance(value, bool):
                    raise ValueError(f"CLI arg {name} must be boolean")
                if value and param_rule.flag:
                    argv.append(param_rule.flag)
            # 强制检查值是否在 choices 白名单内。
            elif param_rule.type == "enum":
                text = str(value)
                if text not in param_rule.choices:
                    raise ValueError(f"CLI arg {name} must be one of {param_rule.choices}")
                argv.append(text)
            # 转换为整数，并检查 min/max 边界。
            elif param_rule.type == "int":
                number = int(value)
                if param_rule.min_value is not None and number < param_rule.min_value:
                    raise ValueError(f"CLI arg {name} is too small")
                if param_rule.max_value is not None and number > param_rule.max_value:
                    raise ValueError(f"CLI arg {name} is too large")
                argv.append(str(number))
            # 这里加了"--"，这是 Unix 命令的标准做法，告诉后面的程序“后面全是参数，不要再解析选项了”，进一步增强安全性。
            elif param_rule.type == "path":
                argv.extend(["--", self._validate_path(name, str(value), param_rule)])
            # 校验命令长度
            elif param_rule.type == "string":
                argv.append(self._validate_string(name, str(value), param_rule))
        return argv

    def _validate_path(self, name: str, value: str, rule: CLIParamRule) -> str:
        """路径是最容易被利用进行“目录穿越攻击”的地方
        这里对路径进行校验：
        1.再次拦截 Shell 语法：防止文件名里藏命令。
        2.标准化：把 Windows 的反斜杠换成 /。
        3.长度限制：防止超长路径溢出。
        4.绝对路径检查：如果规则不允许（默认不允许），且路径以 / 或 C:/ 开头，直接拒绝。
        5.父目录检查：把路径按 / 拆开，如果里面有 ..，直接拒绝。这确保了用户只能访问当前工作目录下的文件。
        """
        self._reject_shell_syntax(value)
        normalized = value.replace("\\", "/")
        if not normalized or len(normalized) > rule.max_length:
            raise ValueError(f"CLI arg {name} path length is invalid")
        if not rule.allow_absolute and (
            normalized.startswith("/") or re.match(r"^[a-zA-Z]:/", normalized)
        ):
            raise ValueError(f"CLI arg {name} does not allow absolute path")
        parts = [part for part in normalized.split("/") if part]
        if not rule.allow_parent and ".." in parts:
            raise ValueError(f"CLI arg {name} does not allow parent path")
        return normalized

    def _validate_string(self, name: str, value: str, rule: CLIParamRule) -> str:
        """检查命令长度，不过会先检查非法字符"""
        self._reject_shell_syntax(value)
        if not value or len(value) > rule.max_length:
            raise ValueError(f"CLI arg {name} length is invalid")
        return value

    def _reject_shell_syntax(self, value: str) -> None:
        """如果 ID 里包含 ;、|、&& 等符号，直接报错。这防止了用户通过伪造 ID 来拼接恶意命令。"""
        if any(token in value for token in self.SHELL_TOKENS):
            raise ValueError("CLI input contains shell syntax and is not allowed")

    def _display_command(self, rule_id: str, args: dict[str, Any]) -> str:
        """展示 cli命令"""
        return f"{rule_id} {args}".strip()

    def _default_rules(self) -> dict[str, CLICommandRule]:
        """这里展示了如何配置两个具体的 Git 命令"""
        return {
            "cli://git/status-short": CLICommandRule(
                id="cli://git/status-short",
                description="查看 Git 工作区简短状态",
                effect="ALLOW",
                risk_level="LOW",
                image="alpine/git:latest",
                argv_template=[
                    "-c",
                    "safe.directory=/workspace",
                    "status",
                    "--short",
                ],
            ),
            "cli://git/diff": CLICommandRule(
                id="cli://git/diff",
                description="查看 Git diff，只读",
                effect="ALLOW",
                risk_level="LOW",
                image="alpine/git:latest",
                argv_template=["-c", "safe.directory=/workspace", "diff"],
                params={
                    "staged": CLIParamRule(type="bool", default=False, flag="--staged"),
                    "path": CLIParamRule(type="path", default="."),
                },
            ),
        }
