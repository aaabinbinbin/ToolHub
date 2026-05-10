# ToolHub 简历与面试材料

## 简历项目名

ToolHub：面向 CLI / IDE Agent 的 Agent Tool Runtime / Harness MVP

## 一句话介绍

构建了一个 Agent 工具运行时平台，将 MCP、HTTP、CLI 和 Sandbox 工具统一接入，并围绕工具路由、权限治理、安全执行、审计追踪和 Trace Console 形成完整 Agent Harness 链路。

## 简历描述版本

可以写成下面这种，不夸成生产级平台：

```text
ToolHub：面向 CLI / IDE Agent 的 Agent Tool Runtime / Harness MVP。基于 FastAPI、Celery、PostgreSQL、Redis、LangGraph 和 Docker SDK 构建，支持 MCP / HTTP / CLI / Sandbox 四类工具的统一注册、路由、权限检查、安全执行和审计追踪。实现 schema-aware + quality-aware ToolRouter、ALLOW / ASK / DENY 权限模型、Docker 隔离执行、任务级 retry/cancel/replay、Trace 聚合 API 和 Streamlit Console，用于展示 Agent 工具调用的完整链路和排障过程。
```

如果简历空间有限，可以压缩成：

```text
实现 ToolHub Agent Tool Runtime MVP，统一接入 MCP / HTTP / CLI / Sandbox 工具，支持 schema-aware 路由、权限审批、Docker 沙箱执行、任务 retry/cancel/replay、全链路审计和 Trace Console，可追踪一次 Agent 任务从规划、路由、权限到工具执行的完整过程。
```

## 推荐要点

- 统一工具注册和调用：MCP / HTTP / CLI / Sandbox
- ToolRouter：top-k candidates、schema 校验、质量指标、LLM rerank 建议
- 权限治理：`PLAN_ONLY` / `SAFE_EXECUTE` / `FULL_EXECUTE`，`ALLOW / ASK / DENY`
- 安全执行：CLI / Sandbox 走 Docker 隔离，CLI 只接受配置化 rule
- 运行时能力：任务级 `max_steps`、`max_retries`、`timeout_seconds`、cancel、replay
- 可观测性：`task_events`、`tool_calls`、`llm_calls`、`sandbox_executions`、Trace API
- 工程化：Alembic migration、docker compose、healthcheck、pytest、routing eval

## 不建议夸大的说法

不要写：

- 生产级多租户 Agent 平台
- 企业级 RBAC 完整权限系统
- 完整替代 LangChain / Dify / MCP Host
- 完整自主 ReAct Agent
- 完整语义检索系统

更稳妥的说法：

- MVP
- runtime / harness
- governance prototype
- traceable tool execution
- explainable routing

## 面试讲解提纲

### 1. 为什么做这个项目？

Agent 真正落地时，问题不只是“能不能调用工具”，而是：

- 工具从哪里来？
- 怎么选择合适工具？
- 高风险工具怎么管？
- CLI / 代码执行怎么隔离？
- 失败后怎么定位？
- 面向用户怎么解释一次工具调用链路？

ToolHub 解决的是 Agent 工具运行时和治理问题。

### 2. LLM 负责什么，不负责什么？

LLM 负责建议：

- intent
- plan
- rerank
- retry 时修正 tool_input
- summary

系统负责控制：

- schema 校验
- permission
- sandbox
- policy
- trace
- final tool selection

可以强调：LLM 不直接决定权限，也不能绕过沙箱。

### 3. ToolRouter 怎么设计？

ToolRouter 不是只做关键词匹配，而是返回 top-k candidates，并给每个候选分项打分：

- tool type signal
- intent signal
- name / tag / description keyword
- schema match
- health status
- success rate
- avg duration
- quality score
- risk level

LLM rerank 只在 top-k 里调整排序建议，最终仍经过系统校验。

### 4. 为什么有沙箱还要 policy？

沙箱降低破坏面，但不等于权限系统：

- 沙箱可能配置错误
- 不是所有工具都在沙箱里执行，例如 HTTP / MCP
- 高风险动作仍需要审批边界
- CLI 需要限制命令模板和参数，而不是接受任意 shell
- 审计系统需要知道为什么允许或拒绝

所以沙箱是隔离层，policy 是治理层。

### 5. Trace 怎么帮助排障？

每次任务都有 `trace_id`，可以聚合：

- task 状态
- event timeline
- route result
- permission result
- tool_calls
- llm_calls
- sandbox_executions
- approvals

面试时可以打开 Dashboard 的 Trace 页，讲一条任务从输入到最终结果的完整链路。

### 6. 项目目前边界是什么？

可以坦诚说明：

- 当前是 MVP，不是生产级 SaaS
- 语义召回 / pgvector 还没作为强依赖接入
- Dashboard 是功能型 Console，还不是独立前端产品
- RBAC 和真实登录体系还没做完整
- 重点在 Agent 工具运行时、安全边界和可追踪执行链路

这种边界讲清楚，反而比强行包装更可信。

## 演示路径

推荐演示顺序：

1. `scripts/final_demo.ps1`
2. 打开 Dashboard Console
3. 查看 Routing 页，展示 top-k 和 score_breakdown
4. 查看 Trace 页，展示 timeline 和 error_types
5. 查看 Replay 页，展示某次工具调用可以重放
6. 讲解 Sandbox / Permission 为什么是双层边界

## 面试官可能追问

### 为什么不用现成 MCP Host？

MCP Host 主要解决工具协议接入，ToolHub 更关注工具运行时治理：路由、权限、审计、沙箱和 trace。

### 为什么不让 LLM 直接选工具？

直接让 LLM 选工具不可控，也不好审计。ToolHub 让 LLM 给建议，但由系统做 schema、policy 和 sandbox 校验。

### 如果工具很多，当前路由是否够用？

当前已经有 top-k、schema、质量指标和 rerank 接口。后续可以接 pgvector / embedding 做语义召回，但不会改变后面的 schema 和 permission 校验链路。

### replay 有什么意义？

replay 能复现某次工具调用的输入和结果，便于调试工具、复现失败、比较 override input 的行为。这对 Agent 工具系统排障很重要。
