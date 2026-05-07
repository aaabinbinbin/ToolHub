# TOOLHUB.md

## 项目背景

ToolHub 是一个面向 CLI / IDE Agent 的 Agent Harness 平台。它通过统一运行时管理 MCP、HTTP、CLI 和 Sandbox 四类工具，并提供工具路由、权限控制、执行审计日志和可观测性能力。

## 安全规则

- 不允许删除宿主机文件。
- 不允许执行破坏性宿主机命令。
- 不允许根据用户输入直接启动任意本地进程。
- 对 Agent 生成的代码和命令，优先使用沙箱执行。
- 高风险工具默认需要明确权限控制，除非当前运行模式允许执行。

## 执行偏好

- 所有工具调用都应可审计，并记录 task_events、tool_calls、llm_calls 和 sandbox_executions。
- 使用 `PLAN_ONLY`、`SAFE_EXECUTE`、`FULL_EXECUTE` 三种运行模式决定允许执行的程度。
- 意图理解、工具路由、权限判断和结果总结等中间结果应尽量保持结构化，优先使用 JSON 格式。
