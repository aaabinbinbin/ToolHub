# TOOLHUB.md

## 项目背景

ToolHub 是一个面向 CLI / IDE Agent 的 Agent Harness 平台。它通过统一运行时管理 MCP、HTTP、CLI 和 Sandbox 四类工具，并提供工具路由、权限控制、执行审计日志和可观测性能力。

## 项目目标

- 为 Agent 提供统一、安全、可审计的工具运行时。
- 把自然语言任务拆成意图理解、工具路由、权限判断、工具执行和结果总结等节点。
- 所有长任务必须进入后台任务系统执行，避免阻塞 API 请求。
- 所有关键步骤都要写入 PostgreSQL，方便 Dashboard 追踪。

## 安全规则

- 不允许删除宿主机文件。
- 不允许执行破坏性宿主机命令。
- 不允许根据用户输入直接启动任意本地进程。
- 对 Agent 生成的代码和命令，优先使用沙箱执行。
- 高风险工具默认需要明确权限控制，除非当前运行模式允许执行。
- HTTP 工具必须防 SSRF，禁止访问 localhost、内网地址和云元数据地址。
- CLI 工具只能通过规则 ID 和结构化参数执行，不允许直接拼接 shell 命令。
- Sandbox 工具必须限制超时、内存、进程数和网络访问。
- LLM 只能提出候选 tool_input，最终安全判断由 Harness、Policy 和 Adapter 完成。

## 执行偏好

- 所有工具调用都应可审计，并记录 task_events、tool_calls、llm_calls 和 sandbox_executions。
- 使用 `PLAN_ONLY`、`SAFE_EXECUTE`、`FULL_EXECUTE` 三种运行模式决定允许执行的程度。
- 意图理解、工具路由、权限判断和结果总结等中间结果应尽量保持结构化，优先使用 JSON 格式。
- 任务最终输出应写入 `tasks.result.summary.final_answer`。
- 权限拒绝、无工具、工具失败都必须给出明确原因和下一步建议。
- 不要声称执行了实际没有执行的工具。

## 输出偏好

- API 返回保持结构化 JSON。
- 面向用户的最终答案使用简洁中文。
- 错误信息优先说明失败节点、失败原因和可操作建议。
