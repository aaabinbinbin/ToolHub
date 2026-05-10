# ToolHub 数据库表设计说明

本文档说明 ToolHub 当前 PostgreSQL 数据库中的基础表结构。表结构以 Alembic migration 为准，当前初始版本位于 `migrations/versions/20260509_0001_initial_schema.py`，治理字段扩展位于 `migrations/versions/20260509_0002_governance_and_redaction.py`，工具版本与运行时元数据扩展位于 `migrations/versions/20260509_0003_tool_versions.py`，任务运行控制与 replay 字段位于 `migrations/versions/20260509_0004_runtime_controls.py`。

## 总体说明

ToolHub 的数据库主要用于保存 Agent Harness 执行链路中的核心数据：

- 工具元数据：`tools`
- Agent 任务状态：`tasks`
- 任务事件日志：`task_events`
- 工具调用审计：`tool_calls`
- 沙箱执行日志：`sandbox_executions`
- LLM 调用日志：`llm_calls`
- 工具健康检查：`tool_health_checks`
- 工具权限策略：`tool_permissions`
- 人工审批请求：`approval_requests`
- 工具版本快照：`tool_versions`

当前数据库使用 PostgreSQL，核心原因是项目需要大量保存 JSONB 类型的半结构化数据，例如工具输入输出、LLM 响应、事件 payload、权限条件等。

## 表关系概览

```text
tools
  ├── tool_calls.tool_id
  ├── tool_health_checks.tool_id
  └── tool_permissions.tool_id

tasks
  ├── task_events.task_id
  ├── tool_calls.task_id
  ├── sandbox_executions.task_id
  └── llm_calls.task_id
  └── approval_requests.task_id
```

`run_id` 和 `trace_id` 会贯穿任务、事件、工具调用、沙箱执行和 LLM 调用，用于串联一次完整 Agent Harness 执行链路。

---

## 1. tools

### 用途

`tools` 表用于保存 Tool Registry 中注册的工具元数据。ToolHub 通过这张表统一管理 MCP、HTTP、CLI、SANDBOX 四类工具。

### 字段说明

| 字段 | 类型 | 约束 | 说明 |
|---|---|---|---|
| `id` | `UUID` | Primary Key | 工具唯一 ID |
| `name` | `TEXT` | Not Null, Unique | 工具名称，注册时不可重复 |
| `description` | `TEXT` | Not Null | 工具描述，用于搜索、路由和 LLM 上下文 |
| `tool_type` | `TEXT` | Not Null, Check | 工具类型，只允许 `MCP`、`HTTP`、`CLI`、`SANDBOX` |
| `endpoint` | `TEXT` | Nullable | HTTP、CLI 或 Sandbox 工具入口，例如 URL、命令名、Docker image |
| `mcp_url` | `TEXT` | Nullable | MCP Server 地址 |
| `transport` | `TEXT` | Nullable | MCP transport 类型，例如 `http`、`sse`、`streamable-http` |
| `version` | `TEXT` | Not Null | 工具版本 |
| `input_schema` | `JSONB` | Nullable | 工具输入 schema |
| `output_schema` | `JSONB` | Nullable | 工具输出 schema |
| `tags` | `JSONB` | Not Null, Default `[]` | 工具标签数组，用于搜索和路由 |
| `risk_level` | `TEXT` | Not Null, Check, Default `LOW` | 风险等级，只允许 `LOW`、`MEDIUM`、`HIGH` |
| `status` | `TEXT` | Not Null, Check, Default `ACTIVE` | 工具状态，只允许 `ACTIVE`、`DISABLED`、`DELETED` |
| `health_status` | `TEXT` | Not Null, Check, Default `UNKNOWN` | 健康状态，只允许 `UNKNOWN`、`UP`、`DOWN` |
| `last_checked_at` | `TIMESTAMPTZ` | Nullable | 最近一次健康检查时间 |
| `created_at` | `TIMESTAMPTZ` | Not Null, Default `now()` | 创建时间 |
| `updated_at` | `TIMESTAMPTZ` | Not Null, Default `now()` | 更新时间 |

### 索引

| 索引 | 字段 | 用途 |
|---|---|---|
| `idx_tools_type` | `tool_type` | 按工具类型筛选 |
| `idx_tools_status` | `status` | 按启用状态筛选 |
| `idx_tools_risk` | `risk_level` | 按风险等级筛选 |
| `idx_tools_tags_gin` | `tags` | 使用 GIN 索引加速 JSONB tags 精确匹配 |

---

## 2. tasks

### 用途

`tasks` 表用于保存用户提交的 Agent 任务及其当前执行状态。后续 Celery worker 和 AgentHarness 会围绕这张表更新任务生命周期。

### 字段说明

| 字段 | 类型 | 约束 | 说明 |
|---|---|---|---|
| `id` | `UUID` | Primary Key | 任务唯一 ID |
| `run_id` | `UUID` | Not Null | 一次 Harness run 的 ID |
| `trace_id` | `UUID` | Not Null | 全链路 trace ID |
| `user_input` | `TEXT` | Not Null | 用户原始输入 |
| `run_mode` | `TEXT` | Not Null, Check, Default `SAFE_EXECUTE` | 运行模式，只允许 `PLAN_ONLY`、`SAFE_EXECUTE`、`FULL_EXECUTE` |
| `selected_tool_id` | `UUID` | Nullable | ToolRouter 最终选择的工具 ID |
| `priority` | `TEXT` | Not Null, Default `default` | 任务优先级，例如 `high_priority`、`default`、`low_priority` |
| `run_config` | `JSONB` | Not Null, Default `{}` | 任务级运行控制，例如 `max_steps`、`max_retries`、`timeout_seconds` |
| `cancel_requested` | `BOOLEAN` | Not Null, Default `false` | 是否已收到取消请求 |
| `cancel_reason` | `TEXT` | Nullable | 取消任务的原因 |
| `cancelled_at` | `TIMESTAMPTZ` | Nullable | 任务取消时间 |
| `status` | `TEXT` | Not Null | 任务状态 |
| `current_step` | `TEXT` | Nullable | 当前执行步骤，例如 `understand_intent`、`select_tool` |
| `retry_count` | `INTEGER` | Not Null, Default `0` | 当前重试次数 |
| `max_retries` | `INTEGER` | Not Null, Default `3` | 最大重试次数 |
| `error_message` | `TEXT` | Nullable | 失败时的错误信息 |
| `result` | `JSONB` | Nullable | 任务最终结果 |
| `created_at` | `TIMESTAMPTZ` | Not Null, Default `now()` | 创建时间 |
| `updated_at` | `TIMESTAMPTZ` | Not Null, Default `now()` | 更新时间 |
| `started_at` | `TIMESTAMPTZ` | Nullable | 开始执行时间 |
| `finished_at` | `TIMESTAMPTZ` | Nullable | 结束时间 |

### 常见状态

```text
PENDING
QUEUED
RUNNING
SUCCESS
FAILED
RETRYING
CANCELLED
PAUSED
WAITING_APPROVAL
```

### 索引

| 索引 | 字段 | 用途 |
|---|---|---|
| `idx_tasks_status` | `status` | 查询某类状态的任务 |
| `idx_tasks_run_id` | `run_id` | 按 run 查询任务 |
| `idx_tasks_trace_id` | `trace_id` | 按 trace 查询执行链路 |

---

## 3. task_events

### 用途

`task_events` 表用于记录任务执行过程中的事件日志。它是可观测性和审计链路的核心表。

### 字段说明

| 字段 | 类型 | 约束 | 说明 |
|---|---|---|---|
| `id` | `UUID` | Primary Key | 事件唯一 ID |
| `task_id` | `UUID` | Not Null, FK `tasks(id)` | 所属任务 ID |
| `run_id` | `UUID` | Not Null | 所属 Harness run ID |
| `trace_id` | `UUID` | Not Null | 全链路 trace ID |
| `event_type` | `TEXT` | Not Null | 事件类型 |
| `step` | `TEXT` | Nullable | 发生事件的执行步骤 |
| `message` | `TEXT` | Nullable | 人类可读的事件说明 |
| `payload` | `JSONB` | Nullable | 事件附加数据 |
| `created_at` | `TIMESTAMPTZ` | Not Null, Default `now()` | 事件创建时间 |

### 事件类型示例

```text
TASK_CREATED
TASK_QUEUED
TASK_STARTED
INSTRUCTION_LOADED
LLM_INTENT_STARTED
LLM_INTENT_FINISHED
TOOL_ROUTING_STARTED
TOOL_SELECTED
PERMISSION_CHECK_STARTED
PERMISSION_ALLOWED
PERMISSION_DENIED
TOOL_CALL_STARTED
TOOL_CALL_FINISHED
LLM_SUMMARY_STARTED
LLM_SUMMARY_FINISHED
TASK_SUCCESS
TASK_FAILED
TASK_RETRYING
TASK_CANCELLED
```

### 索引

| 索引 | 字段 | 用途 |
|---|---|---|
| `idx_task_events_task_id` | `task_id` | 查询某个任务的事件流 |
| `idx_task_events_run_id` | `run_id` | 查询某次 run 的事件 |
| `idx_task_events_trace_id` | `trace_id` | 查询完整 trace |

---

## 4. tool_calls

### 用途

`tool_calls` 表用于记录每一次工具调用。无论底层工具是 MCP、HTTP、CLI 还是 Sandbox，都应该写入这张表。

### 字段说明

| 字段 | 类型 | 约束 | 说明 |
|---|---|---|---|
| `id` | `UUID` | Primary Key | 工具调用唯一 ID |
| `task_id` | `UUID` | Nullable, FK `tasks(id)` | 所属任务 ID |
| `run_id` | `UUID` | Not Null | 所属 Harness run ID |
| `trace_id` | `UUID` | Not Null | 全链路 trace ID |
| `tool_id` | `UUID` | Not Null, FK `tools(id)` | 被调用的工具 ID |
| `tool_name` | `TEXT` | Not Null | 工具名称冗余字段，便于审计展示 |
| `tool_type` | `TEXT` | Not Null | 工具类型冗余字段 |
| `input` | `JSONB` | Nullable | 工具调用输入 |
| `output` | `JSONB` | Nullable | 工具调用输出 |
| `status` | `TEXT` | Not Null | 调用状态，例如 `SUCCESS`、`FAILED` |
| `error_message` | `TEXT` | Nullable | 调用失败时的错误信息 |
| `duration_ms` | `INTEGER` | Nullable | 调用耗时，单位毫秒 |
| `replay_of_tool_call_id` | `UUID` | Nullable, FK `tool_calls(id)` | 如果本次调用来自 replay，记录源 tool_call |
| `replay_reason` | `TEXT` | Nullable | replay 原因或调试说明 |
| `created_at` | `TIMESTAMPTZ` | Not Null, Default `now()` | 创建时间 |

### 索引

| 索引 | 字段 | 用途 |
|---|---|---|
| `idx_tool_calls_task_id` | `task_id` | 查询某个任务的工具调用 |
| `idx_tool_calls_tool_id` | `tool_id` | 查询某个工具的调用历史 |

---

## 5. sandbox_executions

### 用途

`sandbox_executions` 表用于记录 Docker Sandbox 中的命令执行情况。SandboxAdapter 和 DockerSandbox 执行命令后，应把 stdout、stderr、exit code、耗时等信息写入此表。

### 字段说明

| 字段 | 类型 | 约束 | 说明 |
|---|---|---|---|
| `id` | `UUID` | Primary Key | 沙箱执行唯一 ID |
| `task_id` | `UUID` | Nullable, FK `tasks(id)` | 所属任务 ID |
| `run_id` | `UUID` | Not Null | 所属 Harness run ID |
| `trace_id` | `UUID` | Not Null | 全链路 trace ID |
| `tool_name` | `TEXT` | Nullable | 触发执行的工具名称 |
| `command` | `TEXT` | Not Null | 实际执行的命令 |
| `stdout` | `TEXT` | Nullable | 标准输出 |
| `stderr` | `TEXT` | Nullable | 标准错误 |
| `exit_code` | `INTEGER` | Nullable | 进程退出码 |
| `duration_ms` | `INTEGER` | Nullable | 执行耗时，单位毫秒 |
| `timeout_seconds` | `INTEGER` | Nullable | 超时时间，单位秒 |
| `container_id` | `TEXT` | Nullable | Docker 容器 ID |
| `status` | `TEXT` | Not Null | 执行状态，例如 `SUCCESS`、`FAILED`、`TIMEOUT` |
| `error_message` | `TEXT` | Nullable | 执行失败时的错误信息 |
| `created_at` | `TIMESTAMPTZ` | Not Null, Default `now()` | 创建时间 |

### 索引

| 索引 | 字段 | 用途 |
|---|---|---|
| `idx_sandbox_task_id` | `task_id` | 查询某个任务的沙箱执行记录 |

---

## 6. llm_calls

### 用途

`llm_calls` 表用于记录 AgentHarness 中所有 LLM 调用，包括意图理解、结果总结等节点。

### 字段说明

| 字段 | 类型 | 约束 | 说明 |
|---|---|---|---|
| `id` | `UUID` | Primary Key | LLM 调用唯一 ID |
| `task_id` | `UUID` | Nullable, FK `tasks(id)` | 所属任务 ID |
| `run_id` | `UUID` | Not Null | 所属 Harness run ID |
| `trace_id` | `UUID` | Not Null | 全链路 trace ID |
| `node_name` | `TEXT` | Not Null | 调用发生的节点，例如 `understand_intent`、`summarize_result` |
| `provider` | `TEXT` | Not Null | LLM Provider，例如 `openai_compatible`、`dashscope` |
| `model` | `TEXT` | Not Null | 模型名称 |
| `prompt` | `TEXT` | Not Null | 实际发送给模型的 prompt |
| `response` | `TEXT` | Nullable | 模型返回内容 |
| `input_tokens` | `INTEGER` | Nullable | 输入 token 数 |
| `output_tokens` | `INTEGER` | Nullable | 输出 token 数 |
| `duration_ms` | `INTEGER` | Nullable | 调用耗时，单位毫秒 |
| `estimated_cost` | `NUMERIC(12, 6)` | Nullable | 预估调用成本 |
| `status` | `TEXT` | Not Null | 调用状态，例如 `SUCCESS`、`FAILED` |
| `error_message` | `TEXT` | Nullable | 调用失败时的错误信息 |
| `created_at` | `TIMESTAMPTZ` | Not Null, Default `now()` | 创建时间 |

### 索引

| 索引 | 字段 | 用途 |
|---|---|---|
| `idx_llm_calls_task_id` | `task_id` | 查询某个任务的 LLM 调用 |
| `idx_llm_calls_node` | `node_name` | 按节点统计 LLM 调用 |

---

## 7. tool_health_checks

### 用途

`tool_health_checks` 表用于记录工具健康检查历史。`tools.health_status` 保存当前健康状态，此表保存每次检查的明细。

### 字段说明

| 字段 | 类型 | 约束 | 说明 |
|---|---|---|---|
| `id` | `UUID` | Primary Key | 健康检查记录 ID |
| `tool_id` | `UUID` | Not Null, FK `tools(id)` | 被检查的工具 ID |
| `status` | `TEXT` | Not Null | 检查结果，例如 `UP`、`DOWN` |
| `latency_ms` | `INTEGER` | Nullable | 健康检查耗时，单位毫秒 |
| `error_message` | `TEXT` | Nullable | 检查失败时的错误信息 |
| `checked_at` | `TIMESTAMPTZ` | Not Null, Default `now()` | 检查时间 |

### 索引

| 索引 | 字段 | 用途 |
|---|---|---|
| `idx_health_tool_id` | `tool_id` | 查询某个工具的健康检查历史 |

---

## 8. tool_permissions

### 用途

`tool_permissions` 表用于保存工具权限策略。MVP 阶段可以先不实现复杂 policy，只使用 `risk_level + run_mode` 的规则；后续可以把更细粒度策略写入此表。

### 字段说明

| 字段 | 类型 | 约束 | 说明 |
|---|---|---|---|
| `id` | `UUID` | Primary Key | 权限策略 ID |
| `tool_id` | `UUID` | Nullable, FK `tools(id)` | 关联工具 ID；为空时可表示全局规则 |
| `action` | `TEXT` | Not Null | 动作名称，例如 `execute`、`register`、`health_check` |
| `effect` | `TEXT` | Not Null, Check | 策略结果，只允许 `ALLOW`、`ASK`、`DENY` |
| `condition` | `JSONB` | Nullable | 策略条件，例如 run_mode、risk_level、命令模式 |
| `created_at` | `TIMESTAMPTZ` | Not Null, Default `now()` | 创建时间 |

---

## 9. approval_requests

### 用途

`approval_requests` 表用于保存高风险工具调用的人工审批请求。当 `PermissionEngine`
返回 `ASK` 时，Harness 会创建或复用待审批请求，并将任务状态置为
`WAITING_APPROVAL`。

### 字段说明

| 字段 | 类型 | 约束 | 说明 |
|---|---|---|---|
| `id` | `UUID` | Primary Key | 审批请求 ID |
| `task_id` | `UUID` | Not Null, FK `tasks(id)` | 所属任务 ID |
| `run_id` | `UUID` | Not Null | 所属 Harness run ID |
| `trace_id` | `UUID` | Not Null | 全链路 trace ID |
| `tool_id` | `UUID` | Nullable, FK `tools(id)` | 申请执行的工具 ID |
| `requested_action` | `TEXT` | Not Null | 申请动作，例如 `execute:python-sandbox` |
| `reason` | `TEXT` | Not Null | 需要审批的原因 |
| `status` | `TEXT` | Not Null, Check | `PENDING`、`APPROVED`、`REJECTED`、`EXPIRED` |
| `requested_by` | `TEXT` | Nullable | 审批请求发起者 |
| `decided_by` | `TEXT` | Nullable | 审批处理人 |
| `decision_reason` | `TEXT` | Nullable | 审批通过或拒绝原因 |
| `created_at` | `TIMESTAMPTZ` | Not Null, Default `now()` | 创建时间 |
| `decided_at` | `TIMESTAMPTZ` | Nullable | 审批处理时间 |

### 索引

| 索引 | 字段 | 用途 |
|---|---|---|
| `idx_approval_requests_task_id` | `task_id` | 查询某个任务的审批请求 |
| `idx_approval_requests_status` | `status` | 查询待审批请求 |

---

## 设计约定

### UUID

所有核心表主键均使用 `UUID`。应用层负责生成 UUID，便于跨进程、异步任务和后续分布式场景扩展。

### JSONB

以下字段使用 `JSONB` 保存半结构化数据：

- `tools.input_schema`
- `tools.output_schema`
- `tools.tags`
- `tasks.result`
- `task_events.payload`
- `tool_calls.input`
- `tool_calls.output`
- `tool_permissions.condition`

### run_id 与 trace_id

`task_id` 表示用户提交的任务；`run_id` 表示一次 Harness 执行；`trace_id` 用于贯穿完整调用链路。后续 Dashboard 可以通过 `trace_id` 展示完整执行轨迹。

### 时间字段

所有时间字段使用 `TIMESTAMPTZ`，避免本地时区、容器时区和部署环境时区不一致导致排查困难。
