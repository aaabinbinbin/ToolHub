# ToolHub：面向 CLI / IDE Agent 的 Agent Harness 平台开发文档

> 适用目标：配合智能工单项目，用于投递 **Agent 开发实习 / Agent Infra 实习 / 后端 + Agent 方向实习**。  
> 当前阶段：尚未实现，本文档作为项目开发执行文档。  
> 推荐开发周期：前置学习 4 天 + MVP 开发 8~10 天。  
> 最新定位：**ToolHub 不是单纯 MCP 注册中心，而是面向 CLI / IDE Agent 的 Agent Harness / Agent Tool Runtime 平台。**

---

## 0. 本版文档的关键调整

本版文档在原 Agent Harness 版本基础上重新整理，重点调整如下：

```text
1. 数据库主线从 SQLite 改为 PostgreSQL。
2. LangGraph checkpoint 从 SqliteSaver 改为 PostgresSaver。
3. HTTPToolAdapter 和 CLIToolAdapter 纳入 MVP，而不是只预留接口。
4. understand_intent 和 summarize_result 节点改为 LLM 驱动。
5. 新增 LLMClient、IntentService、ResultSummarizerService。
6. 新增 llm_calls 表，记录 LLM 调用链路。
7. 借鉴 Claude Code 这类现代 coding agent 的 Harness 思路，新增：
   - PermissionEngine
   - Run Mode
   - TOOLHUB.md InstructionLoader
8. Hooks、AgentProfile、ExecutionSnapshot、Replay 作为 P1 增强项。
```

---

# 第一部分：项目定位与核心思想

## 1. 项目名称

```text
ToolHub: Agent Harness & Tool Runtime Platform for CLI/IDE Agents
```

中文名称：

```text
ToolHub：面向 CLI / IDE Agent 的 Agent Harness 平台
```

一句话介绍：

```text
ToolHub 是一个面向 CLI / IDE Agent 的 Agent Harness 平台，提供工具注册、工具路由、权限控制、MCP / HTTP / CLI / Sandbox 工具适配、Docker 沙箱执行、Celery 异步任务调度、LangGraph 状态检查点、LLM 意图理解、LLM 结果总结、执行审计和可观测性能力。
```

---

## 2. 为什么不是“单纯 MCP 注册中心”

MCP 很重要，但不能把 ToolHub 的定位限制为 MCP Registry。

更准确的分层是：

```text
CLI / IDE Agent
  = 用户入口，例如 Claude Code、Codex CLI、Cursor、IDE Agent

MCP
  = 工具接入协议之一

Agent Harness
  = 管理工具、上下文、权限、执行环境、状态、审计和可观测性的运行时层
```

所以 ToolHub 应该定位为：

```text
ToolHub = Agent Harness / Agent Tool Runtime
MCP = ToolHub 支持的一种 Tool Adapter
```

这能避免项目被问成：

```text
现在很多 CLI Agent 自己已经支持 MCP，你这个 MCP 注册中心的意义是什么？
```

可以回答：

```text
ToolHub 不是重复实现 MCP Client，而是做 Agent Harness。
它解决的是 Agent 工具使用过程中的治理、权限、安全执行、异步任务、checkpoint、审计和可观测性问题。
MCP 只是其中一种 Tool Adapter。
```

---

## 3. 与智能工单项目的关系

| 项目 | 定位 | 展示能力 |
|---|---|---|
| 智能工单平台 | Agent 业务应用层 | 业务建模、RAG、工单流转、Agent 辅助处理、Java 后端工程 |
| ToolHub | Agent Harness / Agent Infra 层 | 工具治理、权限控制、沙箱执行、异步任务、状态恢复、执行审计 |

组合表达：

```text
智能工单平台证明我能做 Agent 业务应用落地。
ToolHub 证明我理解 Agent 背后的工具治理、安全执行、异步调度、状态恢复和可观测性等基础设施问题。
```

---

## 4. Claude Code 架构给 ToolHub 的参考

ToolHub 不复制 Claude Code，而是借鉴现代 coding agent 的 Agent Harness 设计思想。

可借鉴点：

```text
1. 多入口，但核心 Harness 独立。
2. 工具调用前必须经过权限治理。
3. Plan 与 Execute 分离。
4. 项目规则 / 记忆进入上下文。
5. 工具调用生命周期可以插入 Hooks。
6. Subagent 可抽象为 AgentProfile / WorkerProfile。
7. Checkpoint 不只保存对话状态，也要保存执行副作用。
8. 所有工具调用需要 trace、审计和可观测性。
```

本项目 MVP 先纳入：

```text
1. PermissionEngine
2. Run Mode
3. TOOLHUB.md InstructionLoader
```

P1 再做：

```text
1. HookRuntime
2. AgentProfile / WorkerProfile
3. ExecutionSnapshot
4. Replay / Resume 可视化
5. 更细粒度 allow / ask / deny 策略
```

---

# 第二部分：总体架构

## 5. 总体架构图

```mermaid
flowchart TD
    User[User / CLI Agent / IDE Agent] --> API[FastAPI API Server]

    API --> TaskService[TaskService]
    TaskService --> Celery[Celery Task Runtime]
    Celery --> Worker[Celery Worker]

    Worker --> Harness[AgentHarness Core]

    Harness --> InstructionLoader[TOOLHUB.md InstructionLoader]
    Harness --> LLMIntent[LLM IntentService]
    Harness --> ToolRouter[ToolRouter]
    Harness --> PermissionEngine[PermissionEngine]
    Harness --> AdapterDispatcher[ToolAdapterDispatcher]
    Harness --> LLMSummary[LLM ResultSummarizer]
    Harness --> Checkpoint[LangGraph + PostgresSaver]

    ToolRouter --> ToolRegistry[Tool Registry]
    ToolRegistry --> PG[(PostgreSQL)]

    AdapterDispatcher --> MCPAdapter[MCPToolAdapter]
    AdapterDispatcher --> HTTPAdapter[HTTPToolAdapter]
    AdapterDispatcher --> CLIAdapter[CLIToolAdapter]
    AdapterDispatcher --> SandboxAdapter[SandboxToolAdapter]

    MCPAdapter --> MCPServer[FastMCP / MCP Server]
    HTTPAdapter --> HTTPService[External HTTP API]
    CLIAdapter --> DockerSandbox[Docker Sandbox Runtime]
    SandboxAdapter --> DockerSandbox
    DockerSandbox --> Docker[Docker Container]

    Harness --> Events[task_events / tool_calls / llm_calls]
    Events --> PG
    Checkpoint --> PG

    PG --> Dashboard[Streamlit Observability Dashboard]
```

---

## 6. 核心执行链路

```text
用户提交任务
    ↓
TaskService 创建 task / run / trace
    ↓
Celery 异步执行
    ↓
AgentHarness.run()
    ↓
读取 TOOLHUB.md 项目规则
    ↓
LLM understand_intent 生成结构化意图
    ↓
ToolRouter 召回和选择工具
    ↓
PermissionEngine 检查 run_mode / risk_level / policy
    ↓
ToolAdapterDispatcher 分发工具调用
    ↓
MCP / HTTP / CLI / Sandbox Adapter 执行
    ↓
LLM summarize_result 总结结果
    ↓
PostgreSQL 保存 task_events / tool_calls / llm_calls / checkpoint
    ↓
Dashboard 展示执行链路
```

---

## 7. 分层架构

```text
API 层
  FastAPI Routers
  负责 HTTP 请求入口、参数接收、响应封装

Harness 层
  AgentHarness
  ExecutionContext
  RunConfig
  负责把上下文、LLM、工具路由、权限、工具执行、checkpoint、日志串起来

Context 层
  InstructionLoader
  TOOLHUB.md
  负责加载项目规则、工具约束和执行偏好

LLM 层
  LLMClient
  IntentService
  ResultSummarizerService
  负责意图理解和结果总结

Tool 层
  ToolRegistryService
  ToolRouterService
  ToolAdapterDispatcher
  MCPToolAdapter
  HTTPToolAdapter
  CLIToolAdapter
  SandboxToolAdapter

Security 层
  PermissionEngine
  CommandPolicy
  RiskPolicy
  负责工具调用权限、危险命令拦截和 run_mode 控制

Runtime 层
  Celery Task Runtime
  LangGraph Workflow
  PostgreSQL Checkpoint Runtime
  Docker Sandbox Runtime

Repository 层
  PostgreSQL Repository
  负责 tools / tasks / events / calls / checkpoints 数据读写

Dashboard 层
  Streamlit
  展示任务状态、工具健康、LLM 调用、工具调用、沙箱执行日志
```

---

# 第三部分：技术选型

## 8. 技术栈

```text
Web API:
  FastAPI
  Pydantic
  Uvicorn

Database:
  PostgreSQL
  psycopg / asyncpg
  SQLAlchemy 可选
  Alembic 可选

Task Queue:
  Redis
  Celery

Agent Workflow:
  LangGraph
  PostgresSaver

LLM:
  OpenAI-compatible API / Claude API / DeepSeek API / DashScope-compatible API
  通过统一 LLMClient 适配

Tool Protocol:
  MCP / FastMCP
  HTTP API
  CLI Command
  Docker Sandbox

Sandbox:
  Docker SDK for Python

Dashboard:
  Streamlit

Test:
  pytest
  httpx test client
```

---

## 9. 为什么用 PostgreSQL

本项目本地已有 PostgreSQL，所以直接使用 PostgreSQL 作为主数据库。

用途：

```text
1. 保存 Tool 元数据
2. 保存任务状态
3. 保存 task_events
4. 保存 tool_calls
5. 保存 sandbox_executions
6. 保存 llm_calls
7. 保存 tool_health_checks
8. 保存 LangGraph checkpoint
9. 后续可扩展 pgvector 做 Tool 语义检索
```

相比 SQLite，PostgreSQL 更适合这个项目：

```text
1. 更接近真实 Agent Infra 项目
2. 支持并发写入
3. JSONB 适合保存 tool_input / tool_output / LLM response
4. 后续可直接接 pgvector
5. 更适合 Celery worker 并发场景
6. 简历表达更接近生产环境
```

---

## 10. LLM 在本项目中的角色

LLM 负责最适合它的两件事：

```text
1. understand_intent:
   将用户自然语言转换为结构化意图、任务类型、风险判断和工具输入候选。

2. summarize_result:
   将工具执行结果、stdout/stderr、HTTP response、MCP response 总结成人类可读结果。
```

不交给 LLM 的部分：

```text
1. 权限判断最终结果
2. 高风险命令是否允许
3. 数据库写入
4. Docker 资源限制
5. Celery retry 规则
6. Tool 是否启用
7. 审计日志是否记录
```

原则：

```text
LLM 负责理解和总结。
系统负责治理、执行和审计。
```

---

# 第四部分：功能范围

## 11. MVP 必做功能

```text
1. PostgreSQL 数据库主线
   - 初始化数据库
   - tools / tasks / task_events / tool_calls / sandbox_executions / llm_calls / tool_health_checks
   - LangGraph PostgresSaver checkpoint

2. AgentHarness Core
   - ExecutionContext
   - RunConfig
   - AgentHarness.run()
   - task_id / run_id / trace_id 管理

3. TOOLHUB.md InstructionLoader
   - 读取项目根目录 TOOLHUB.md
   - 作为 LLM prompt 上下文
   - 提供默认规则

4. LLM IntentService
   - understand_intent 节点调用 LLM
   - 输出结构化 JSON
   - 记录 llm_calls

5. Tool Registry
   - 注册 Tool
   - 查询 Tool
   - 搜索 Tool
   - 启用 / 禁用 Tool
   - 删除 Tool
   - 健康检查

6. Tool Router
   - 基于 intent + tools 做规则召回
   - 支持 name / tags / description 匹配
   - 可结合 LLM intent 选择工具
   - 返回 selected_tool + reason

7. PermissionEngine
   - 支持 run_mode
   - 支持 risk_level
   - HIGH 风险工具在非 FULL_EXECUTE 下拒绝或进入 WAITING_APPROVAL
   - 记录权限事件

8. Tool Adapter Layer
   - MCPToolAdapter
   - HTTPToolAdapter
   - CLIToolAdapter
   - SandboxToolAdapter
   - ToolAdapterDispatcher

9. Docker Sandbox Runtime
   - 执行 Python / CLI 命令
   - 限制 CPU / 内存 / 网络 / 超时
   - 捕获 stdout / stderr / exit_code
   - 保存 sandbox_executions

10. Celery Task Runtime
   - 提交任务
   - 查询状态
   - 失败重试
   - task_events

11. LangGraph + PostgresSaver
   - load_instructions
   - understand_intent
   - select_tool
   - check_permission
   - execute_tool
   - summarize_result
   - 每步 checkpoint

12. LLM ResultSummarizerService
   - summarize_result 节点调用 LLM
   - 总结工具结果
   - 记录 llm_calls

13. Streamlit Dashboard
   - tasks
   - task_events
   - tool_calls
   - llm_calls
   - sandbox_executions
   - tool health
```

---

## 12. P1 增强功能

```text
1. HookRuntime
   - TaskCreated
   - BeforeToolCall
   - AfterToolCall
   - TaskSucceeded
   - TaskFailed

2. AgentProfile / WorkerProfile
   - planner-profile
   - code-runner-profile
   - ops-profile
   - readonly-profile

3. ExecutionSnapshot
   - 保存每步副作用快照
   - artifact_refs
   - generated command
   - tool input/output

4. Replay / Resume 可视化
   - 展示完整 trajectory
   - 支持从 checkpoint 恢复

5. Tool Router 增强
   - embedding 语义召回
   - pgvector
   - LLM rerank
   - Tool routing evaluation

6. 更细粒度 Permission Policy
   - ALLOW
   - ASK
   - DENY
   - 按 tool_type / command / endpoint / risk_level 控制

7. MCP 增强
   - streamable-http
   - SSE
   - tool list sync
   - tool schema 自动导入
```

---

## 13. P2 暂缓功能

```text
1. LoRA 微调 Tool Router
2. Kubernetes Job 沙箱
3. 多租户权限系统
4. 完整 Web 前端替代 Streamlit
5. Prometheus + Grafana
6. 浏览器自动化 Agent 环境
7. 复杂计费系统
8. 企业级 RBAC
```

---

# 第五部分：核心概念设计

## 14. Run Mode 设计

ToolHub 支持三种运行模式：

```text
PLAN_ONLY:
  只做意图理解、工具选择、执行计划生成。
  不执行真实工具。

SAFE_EXECUTE:
  允许 LOW / MEDIUM 风险工具。
  拒绝 HIGH 风险工具，或进入 WAITING_APPROVAL。

FULL_EXECUTE:
  允许高风险工具，但仍要经过 PermissionEngine 和命令安全检查。
```

请求体示例：

```json
{
  "user_input": "帮我运行 Python 代码 print(sum(range(10)))",
  "priority": "default",
  "run_mode": "SAFE_EXECUTE"
}
```

任务状态新增：

```text
WAITING_APPROVAL
APPROVED
DENIED
```

---

## 15. TOOLHUB.md 设计

项目根目录增加：

```text
TOOLHUB.md
```

作用：

```text
1. 描述当前项目背景
2. 说明可用工具
3. 说明禁止命令
4. 说明执行偏好
5. 说明输出格式
6. 提供 LLM understand_intent 和 summarize_result 的上下文
```

示例：

```markdown
# TOOLHUB.md

## 项目背景

这是一个 Agent Harness 平台，目标是安全调用 MCP、HTTP、CLI 和 Sandbox 工具。

## 安全规则

- 不允许删除宿主机文件
- 不允许执行 rm -rf /
- 不允许执行 curl | sh
- 高风险工具必须使用 FULL_EXECUTE

## 输出要求

- 最终结果需要说明调用了什么工具
- 如果工具失败，需要解释 stdout/stderr
- 如果任务被拒绝，需要说明是哪条规则拒绝
```

MVP 实现：

```text
InstructionLoader 在 AgentHarness.run() 开始时读取 TOOLHUB.md。
如果不存在，则使用默认系统规则。
```

---

## 16. PermissionEngine 设计

PermissionEngine 位于 ToolRouter 和 ToolAdapter 之间。

执行顺序：

```text
ToolRouter
    ↓
PermissionEngine
    ↓
ToolAdapterDispatcher
```

MVP 策略：

```text
LOW:
  默认允许

MEDIUM:
  默认允许，但记录审计事件

HIGH:
  如果 run_mode = FULL_EXECUTE，继续检查命令安全策略
  如果 run_mode = SAFE_EXECUTE，拒绝或进入 WAITING_APPROVAL
  如果 run_mode = PLAN_ONLY，不执行
```

返回结构：

```json
{
  "allowed": false,
  "decision": "DENY",
  "reason": "Tool risk_level is HIGH but run_mode is SAFE_EXECUTE.",
  "required_mode": "FULL_EXECUTE"
}
```

---

## 17. LLM IntentService 设计

### 17.1 输入

```text
1. user_input
2. TOOLHUB.md instructions
3. available tool summaries
4. run_mode
```

### 17.2 输出 JSON

```json
{
  "intent": "RUN_CODE",
  "task_type": "SANDBOX_EXECUTION",
  "language": "python",
  "risk_level": "HIGH",
  "required_tool_type": "SANDBOX",
  "tool_input_candidate": {
    "command": "python -c \"print(sum(range(10)))\""
  },
  "reason": "User asks to run Python code."
}
```

### 17.3 设计要求

```text
1. 必须要求 LLM 输出 JSON
2. JSON 解析失败要进入 fallback
3. fallback 可以用规则粗略识别
4. 每次调用必须写入 llm_calls
5. Prompt 中必须包含安全规则
6. LLM 不能决定最终是否允许执行，只能给出风险建议
```

---

## 18. LLM ResultSummarizerService 设计

### 18.1 输入

```text
1. user_input
2. intent
3. selected_tool
4. tool_result
5. stdout
6. stderr
7. exit_code
8. permission decision
```

### 18.2 输出

```json
{
  "final_answer": "Python 代码已在沙箱中执行完成，sum(range(10)) 的结果是 45。",
  "success": true,
  "summary": "调用 python-sandbox 工具成功，exit_code=0。",
  "warnings": []
}
```

### 18.3 设计要求

```text
1. 不直接编造工具结果
2. stdout/stderr 必须来自真实 ToolResult
3. 工具失败时要解释失败原因
4. 权限拒绝时要说明拒绝规则
5. 每次调用必须写入 llm_calls
```

---

# 第六部分：数据库设计 PostgreSQL

## 19. PostgreSQL 初始化建议

`.env.example`：

```env
APP_ENV=dev
DATABASE_URL=postgresql://postgres:postgres@localhost:5432/toolhub
REDIS_URL=redis://localhost:6379/0

LLM_PROVIDER=openai_compatible
LLM_BASE_URL=https://api.example.com/v1
LLM_API_KEY=your_api_key
LLM_MODEL=your-model-name
```

初始化命令示例：

```powershell
createdb toolhub
python scripts/init_db.py
```

因为你本地已有 PostgreSQL，`docker-compose.yml` 可以只保留 Redis。

---

## 20. 表结构

### 20.1 tools

```sql
CREATE TABLE IF NOT EXISTS tools (
    id UUID PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    description TEXT NOT NULL,
    tool_type TEXT NOT NULL CHECK (tool_type IN ('MCP', 'HTTP', 'CLI', 'SANDBOX')),
    endpoint TEXT,
    mcp_url TEXT,
    transport TEXT,
    version TEXT NOT NULL,
    input_schema JSONB,
    output_schema JSONB,
    tags JSONB NOT NULL DEFAULT '[]'::jsonb,
    risk_level TEXT NOT NULL DEFAULT 'LOW' CHECK (risk_level IN ('LOW', 'MEDIUM', 'HIGH')),
    status TEXT NOT NULL DEFAULT 'ACTIVE' CHECK (status IN ('ACTIVE', 'DISABLED', 'DELETED')),
    health_status TEXT NOT NULL DEFAULT 'UNKNOWN' CHECK (health_status IN ('UNKNOWN', 'UP', 'DOWN')),
    last_checked_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_tools_type ON tools(tool_type);
CREATE INDEX IF NOT EXISTS idx_tools_status ON tools(status);
CREATE INDEX IF NOT EXISTS idx_tools_risk ON tools(risk_level);
```

---

### 20.2 tasks

```sql
CREATE TABLE IF NOT EXISTS tasks (
    id UUID PRIMARY KEY,
    run_id UUID NOT NULL,
    trace_id UUID NOT NULL,
    user_input TEXT NOT NULL,
    run_mode TEXT NOT NULL DEFAULT 'SAFE_EXECUTE'
        CHECK (run_mode IN ('PLAN_ONLY', 'SAFE_EXECUTE', 'FULL_EXECUTE')),
    selected_tool_id UUID,
    priority TEXT NOT NULL DEFAULT 'default',
    status TEXT NOT NULL,
    current_step TEXT,
    retry_count INTEGER NOT NULL DEFAULT 0,
    max_retries INTEGER NOT NULL DEFAULT 3,
    error_message TEXT,
    result JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    started_at TIMESTAMPTZ,
    finished_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status);
CREATE INDEX IF NOT EXISTS idx_tasks_run_id ON tasks(run_id);
CREATE INDEX IF NOT EXISTS idx_tasks_trace_id ON tasks(trace_id);
```

---

### 20.3 task_events

```sql
CREATE TABLE IF NOT EXISTS task_events (
    id UUID PRIMARY KEY,
    task_id UUID NOT NULL REFERENCES tasks(id),
    run_id UUID NOT NULL,
    trace_id UUID NOT NULL,
    event_type TEXT NOT NULL,
    step TEXT,
    message TEXT,
    payload JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_task_events_task_id ON task_events(task_id);
CREATE INDEX IF NOT EXISTS idx_task_events_run_id ON task_events(run_id);
CREATE INDEX IF NOT EXISTS idx_task_events_trace_id ON task_events(trace_id);
```

事件类型：

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

---

### 20.4 tool_calls

```sql
CREATE TABLE IF NOT EXISTS tool_calls (
    id UUID PRIMARY KEY,
    task_id UUID REFERENCES tasks(id),
    run_id UUID NOT NULL,
    trace_id UUID NOT NULL,
    tool_id UUID NOT NULL REFERENCES tools(id),
    tool_name TEXT NOT NULL,
    tool_type TEXT NOT NULL,
    input JSONB,
    output JSONB,
    status TEXT NOT NULL,
    error_message TEXT,
    duration_ms INTEGER,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_tool_calls_task_id ON tool_calls(task_id);
CREATE INDEX IF NOT EXISTS idx_tool_calls_tool_id ON tool_calls(tool_id);
```

---

### 20.5 sandbox_executions

```sql
CREATE TABLE IF NOT EXISTS sandbox_executions (
    id UUID PRIMARY KEY,
    task_id UUID REFERENCES tasks(id),
    run_id UUID NOT NULL,
    trace_id UUID NOT NULL,
    tool_name TEXT,
    command TEXT NOT NULL,
    stdout TEXT,
    stderr TEXT,
    exit_code INTEGER,
    duration_ms INTEGER,
    timeout_seconds INTEGER,
    container_id TEXT,
    status TEXT NOT NULL,
    error_message TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_sandbox_task_id ON sandbox_executions(task_id);
```

---

### 20.6 llm_calls

```sql
CREATE TABLE IF NOT EXISTS llm_calls (
    id UUID PRIMARY KEY,
    task_id UUID REFERENCES tasks(id),
    run_id UUID NOT NULL,
    trace_id UUID NOT NULL,
    node_name TEXT NOT NULL,
    provider TEXT NOT NULL,
    model TEXT NOT NULL,
    prompt TEXT NOT NULL,
    response TEXT,
    input_tokens INTEGER,
    output_tokens INTEGER,
    duration_ms INTEGER,
    estimated_cost NUMERIC(12, 6),
    status TEXT NOT NULL,
    error_message TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_llm_calls_task_id ON llm_calls(task_id);
CREATE INDEX IF NOT EXISTS idx_llm_calls_node ON llm_calls(node_name);
```

---

### 20.7 tool_health_checks

```sql
CREATE TABLE IF NOT EXISTS tool_health_checks (
    id UUID PRIMARY KEY,
    tool_id UUID NOT NULL REFERENCES tools(id),
    status TEXT NOT NULL,
    latency_ms INTEGER,
    error_message TEXT,
    checked_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_health_tool_id ON tool_health_checks(tool_id);
```

---

### 20.8 tool_permissions

```sql
CREATE TABLE IF NOT EXISTS tool_permissions (
    id UUID PRIMARY KEY,
    tool_id UUID REFERENCES tools(id),
    action TEXT NOT NULL,
    effect TEXT NOT NULL CHECK (effect IN ('ALLOW', 'ASK', 'DENY')),
    condition JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

MVP 可以先不做复杂 policy，只使用 risk_level + run_mode 规则。

---

# 第七部分：API 设计

## 21. Task / Harness API

```text
POST /api/tasks/submit
GET  /api/tasks/{id}/status
GET  /api/tasks/{id}/events
POST /api/tasks/{id}/cancel
POST /api/tasks/{id}/resume
```

提交任务：

```json
{
  "user_input": "帮我运行 Python 代码 print(sum(range(10)))",
  "priority": "default",
  "run_mode": "SAFE_EXECUTE"
}
```

响应：

```json
{
  "task_id": "task_uuid",
  "run_id": "run_uuid",
  "trace_id": "trace_uuid",
  "status": "QUEUED"
}
```

---

## 22. Tool Registry API

```text
POST   /api/tools/register
GET    /api/tools/search?q=
GET    /api/tools/{id}
PATCH  /api/tools/{id}/enable
PATCH  /api/tools/{id}/disable
DELETE /api/tools/{id}
GET    /api/tools/{id}/health
```

注册 MCP Tool：

```json
{
  "name": "calculator",
  "description": "A calculator MCP tool that can add, subtract and multiply numbers.",
  "tool_type": "MCP",
  "mcp_url": "http://localhost:9001/mcp",
  "transport": "http",
  "version": "1.0.0",
  "tags": ["math", "calculator", "mcp"],
  "risk_level": "LOW"
}
```

注册 HTTP Tool：

```json
{
  "name": "http-weather",
  "description": "Call weather HTTP API.",
  "tool_type": "HTTP",
  "endpoint": "https://api.example.com/weather",
  "version": "1.0.0",
  "input_schema": {
    "type": "object",
    "properties": {
      "city": {"type": "string"}
    },
    "required": ["city"]
  },
  "tags": ["http", "weather", "api"],
  "risk_level": "LOW"
}
```

注册 CLI Tool：

```json
{
  "name": "git-status",
  "description": "Run git status in a sandboxed workspace.",
  "tool_type": "CLI",
  "endpoint": "git status",
  "version": "1.0.0",
  "tags": ["git", "cli", "readonly"],
  "risk_level": "MEDIUM"
}
```

注册 Sandbox Tool：

```json
{
  "name": "python-sandbox",
  "description": "Run simple Python code in a Docker sandbox.",
  "tool_type": "SANDBOX",
  "endpoint": "docker://python:3.11-slim",
  "version": "1.0.0",
  "tags": ["python", "sandbox", "code"],
  "risk_level": "HIGH"
}
```

---

## 23. Sandbox API

```text
POST /api/sandbox/execute
GET  /api/sandbox/executions/{id}
GET  /api/sandbox/executions?task_id=
```

请求：

```json
{
  "tool_name": "python-sandbox",
  "command": "python -c \"print(sum(range(10)))\"",
  "timeout": 30
}
```

响应：

```json
{
  "execution_id": "exec_uuid",
  "stdout": "45\n",
  "stderr": "",
  "exit_code": 0,
  "duration_ms": 812,
  "status": "SUCCESS"
}
```

---

## 24. Metrics API

```text
GET /api/metrics/summary
GET /api/metrics/tasks
GET /api/metrics/tools
GET /api/metrics/tool-calls
GET /api/metrics/llm-calls
GET /api/metrics/sandbox
GET /api/metrics/errors
```

MVP 可以让 Streamlit 直接读 PostgreSQL，API 可逐步补齐。

---

# 第八部分：推荐项目结构

```text
toolhub/
├── README.md
├── TOOLHUB.md
├── pyproject.toml
├── .env.example
├── docker-compose.yml
├── docs/
│   └── toolhub_agent_harness_development_plan.md
├── app/
│   ├── main.py
│   ├── api/
│   │   ├── tools.py
│   │   ├── sandbox.py
│   │   ├── tasks.py
│   │   ├── harness.py
│   │   └── metrics.py
│   ├── harness/
│   │   ├── agent_harness.py
│   │   ├── execution_context.py
│   │   └── run_config.py
│   ├── context/
│   │   └── instruction_loader.py
│   ├── llm/
│   │   ├── llm_client.py
│   │   ├── intent_service.py
│   │   └── result_summarizer_service.py
│   ├── security/
│   │   ├── permission_engine.py
│   │   └── command_policy.py
│   ├── schemas/
│   │   ├── tool.py
│   │   ├── sandbox.py
│   │   ├── task.py
│   │   ├── harness.py
│   │   ├── llm.py
│   │   └── permission.py
│   ├── services/
│   │   ├── tool_registry_service.py
│   │   ├── tool_router_service.py
│   │   ├── sandbox_service.py
│   │   ├── task_service.py
│   │   ├── trace_service.py
│   │   └── checkpoint_service.py
│   ├── tools/
│   │   ├── dispatcher.py
│   │   ├── tool_call.py
│   │   └── adapters/
│   │       ├── base.py
│   │       ├── mcp_adapter.py
│   │       ├── http_adapter.py
│   │       ├── cli_adapter.py
│   │       └── sandbox_adapter.py
│   ├── repositories/
│   │   ├── db.py
│   │   ├── tool_repository.py
│   │   ├── task_repository.py
│   │   ├── event_repository.py
│   │   ├── tool_call_repository.py
│   │   ├── sandbox_repository.py
│   │   ├── llm_call_repository.py
│   │   └── health_repository.py
│   ├── infra/
│   │   ├── docker_sandbox.py
│   │   ├── celery_app.py
│   │   ├── redis_client.py
│   │   ├── mcp_client.py
│   │   └── langgraph_app.py
│   ├── workers/
│   │   └── task_worker.py
│   └── common/
│       ├── config.py
│       ├── exceptions.py
│       ├── logging.py
│       └── time_utils.py
├── examples/
│   ├── fastmcp_tools/
│   │   └── calculator_server.py
│   └── http_tools/
│       └── simple_echo_server.py
├── dashboard/
│   └── streamlit_app.py
├── scripts/
│   ├── init_db.py
│   ├── run_api.ps1
│   ├── run_worker.ps1
│   ├── run_dashboard.ps1
│   └── demo_flow.ps1
└── tests/
    ├── test_tool_registry.py
    ├── test_tool_router.py
    ├── test_permission_engine.py
    ├── test_http_adapter.py
    ├── test_cli_adapter.py
    ├── test_sandbox.py
    ├── test_llm_nodes.py
    ├── test_task_flow.py
    └── test_agent_harness.py
```

---

# 第九部分：核心模块设计

## 25. AgentHarness

职责：

```text
1. 接收 AgentTask
2. 创建 ExecutionContext
3. 加载 TOOLHUB.md
4. 调用 LLMIntentService
5. 调用 ToolRouter
6. 调用 PermissionEngine
7. 调用 ToolAdapterDispatcher
8. 调用 LLMResultSummarizer
9. 写入 task_events / tool_calls / llm_calls
10. 管理 run_id / trace_id
```

接口：

```python
class AgentHarness:
    def run(self, task: AgentTask) -> AgentRunResult:
        pass

    def resume(self, run_id: str) -> AgentRunResult:
        pass

    def cancel(self, run_id: str) -> None:
        pass
```

MVP：

```text
run() 必须实现。
resume() / cancel() 可先预留。
```

---

## 26. ExecutionContext

```python
from pydantic import BaseModel
from typing import Any

class ExecutionContext(BaseModel):
    task_id: str
    run_id: str
    trace_id: str
    user_input: str
    run_mode: str
    project_instructions: str | None = None
    current_step: str | None = None
    intent: dict[str, Any] | None = None
    selected_tool_id: str | None = None
    selected_tool_name: str | None = None
    selected_tool_type: str | None = None
    permission_decision: dict[str, Any] | None = None
    tool_input: dict[str, Any] | None = None
    tool_result: dict[str, Any] | None = None
    final_result: str | None = None
    error_message: str | None = None
```

---

## 27. LLMClient

职责：

```text
1. 统一调用 OpenAI-compatible / Claude / DeepSeek / DashScope-compatible API
2. 支持 model / base_url / api_key 配置
3. 返回 text / json
4. 统计 tokens / duration
5. 写入 llm_calls
```

接口：

```python
class LLMClient:
    def complete(self, prompt: str, model: str | None = None) -> LLMResult:
        pass

    def complete_json(self, prompt: str, model: str | None = None) -> dict:
        pass
```

---

## 28. ToolAdapterDispatcher

职责：

```text
1. 根据 tool_type 找到对应 Adapter
2. 统一调用 call()
3. 统一记录 tool_calls
4. 统一处理异常
```

接口：

```python
class ToolAdapterDispatcher:
    def dispatch(self, tool: Tool, tool_input: dict, context: ExecutionContext) -> ToolCallResult:
        pass
```

---

## 29. HTTPToolAdapter

职责：

```text
1. 调用普通 HTTP API
2. 支持 GET / POST
3. 支持 headers
4. 支持 query params
5. 支持 JSON body
6. 支持 timeout
7. 保存 tool_calls
```

安全要求：

```text
1. endpoint 必须是 http:// 或 https://
2. 默认 timeout <= 30s
3. 不允许访问 localhost / 127.0.0.1 / 内网地址，除非配置 allow_private_network=true
4. 不允许无限重试
5. response 体积需要限制
```

MVP 支持：

```text
GET
POST JSON
timeout
status_code
response_text
response_json
```

---

## 30. CLIToolAdapter

职责：

```text
1. 执行白名单 CLI 命令
2. 默认通过 DockerSandbox 执行
3. 不允许裸跑宿主机命令
4. 保存 stdout / stderr / exit_code
5. 保存 tool_calls 和 sandbox_executions
```

安全要求：

```text
1. CLI Tool 必须注册 endpoint
2. endpoint 只能是白名单命令模板
3. 实际执行参数必须经过 schema 校验
4. 默认进入 DockerSandbox
5. 禁止危险命令
```

示例：

```text
git status
python -m pytest
node --version
```

不允许：

```text
rm -rf /
curl | sh
wget | sh
chmod 777 /
shutdown
reboot
```

---

## 31. LangGraph Workflow

节点：

```text
load_instructions
    ↓
understand_intent
    ↓
select_tool
    ↓
check_permission
    ↓
execute_tool
    ↓
summarize_result
```

State：

```python
from typing import TypedDict, Any

class AgentTaskState(TypedDict):
    task_id: str
    run_id: str
    trace_id: str
    user_input: str
    run_mode: str
    project_instructions: str | None
    intent: dict[str, Any] | None
    selected_tool_id: str | None
    selected_tool_name: str | None
    selected_tool_type: str | None
    permission_decision: dict[str, Any] | None
    tool_input: dict[str, Any] | None
    tool_result: dict[str, Any] | None
    status: str
    error: str | None
    step: str
    final_answer: str | None
```

节点职责：

```text
load_instructions:
  读取 TOOLHUB.md。

understand_intent:
  调用 LLMIntentService，输出结构化 intent。

select_tool:
  调用 ToolRouterService，根据 intent + user_input 选择工具。

check_permission:
  调用 PermissionEngine，判断是否允许执行。

execute_tool:
  调用 ToolAdapterDispatcher，执行 MCP / HTTP / CLI / Sandbox 工具。

summarize_result:
  调用 LLMResultSummarizerService，总结结果。
```

---

# 第十部分：开发计划

## 32. 前置学习计划

### Day 1：Python + FastAPI + Pydantic

```text
目标：
  能写 FastAPI CRUD，并理解 Pydantic schema。

重点：
  APIRouter
  Depends
  Exception Handler
  BaseModel
  类型注解
  async/await
```

---

### Day 2：PostgreSQL + Docker SDK + Celery

```text
目标：
  能连接 PostgreSQL，能用 Docker SDK 执行命令，能提交 Celery 异步任务。

重点：
  psycopg / asyncpg
  PostgreSQL JSONB
  Docker SDK containers.create / exec_run
  Celery delay / apply_async / retry
```

---

### Day 3：LangGraph + MCP / FastMCP + LLMClient

```text
目标：
  能写 3~5 节点 LangGraph，能启动 FastMCP Server，能封装 LLMClient。

重点：
  StateGraph
  PostgresSaver
  FastMCP @mcp.tool
  structured JSON output
```

---

### Day 4：Agent Harness 架构设计

```text
目标：
  定好 API、表结构、模块边界、Demo 流程。

交付：
  README 初稿
  TOOLHUB.md 初稿
  数据库初始化脚本
  Demo 脚本草稿
```

---

## 33. MVP 开发计划

### Day 0：项目初始化 + PostgreSQL

```text
□ 创建项目结构
□ 创建 .env.example
□ 创建 PostgreSQL 连接配置
□ 创建 app/repositories/db.py
□ 创建 scripts/init_db.py
□ 创建所有基础表
□ 添加 /health endpoint
□ 添加 TOOLHUB.md
□ FastAPI 能启动
□ PostgreSQL 初始化成功
```

验收：

```text
□ uvicorn app.main:app --reload 能启动
□ GET /health 返回 OK
□ python scripts/init_db.py 能创建表
□ /docs 能打开
```

---

### Day 1：Tool Registry + Tool 类型

```text
□ 实现 tools 表 Repository
□ 实现 ToolRegisterRequest
□ 支持 MCP / HTTP / CLI / SANDBOX 四类 Tool
□ 实现 register / get / search / enable / disable / delete
□ 实现 health_status 字段
```

验收：

```text
□ 能注册 MCP Tool
□ 能注册 HTTP Tool
□ 能注册 CLI Tool
□ 能注册 SANDBOX Tool
□ 能搜索 Tool
□ 禁用 Tool 后不会被选中
```

---

### Day 2：LLMClient + IntentService + TOOLHUB.md

```text
□ 实现 InstructionLoader
□ 实现 LLMClient
□ 实现 llm_calls 表写入
□ 实现 IntentService
□ understand_intent 输出 JSON
□ JSON 解析失败 fallback
```

验收：

```text
□ 能读取 TOOLHUB.md
□ 输入“帮我运行 Python 代码 print(1+1)”能输出 RUN_CODE intent
□ llm_calls 有记录
```

---

### Day 3：ToolRouter + PermissionEngine + Run Mode

```text
□ 实现 ToolRouterService
□ 实现 PermissionEngine
□ 实现 run_mode: PLAN_ONLY / SAFE_EXECUTE / FULL_EXECUTE
□ HIGH 风险工具在 SAFE_EXECUTE 下拒绝或 WAITING_APPROVAL
□ task_events 记录 permission decision
```

验收：

```text
□ calculate 任务能选 calculator
□ Python 代码任务能选 python-sandbox
□ SAFE_EXECUTE 下 HIGH 风险工具被拒绝或等待审批
□ FULL_EXECUTE 下可继续执行
```

---

### Day 4：四类 Tool Adapter

```text
□ 实现 BaseToolAdapter
□ 实现 ToolAdapterDispatcher
□ 实现 MCPToolAdapter
□ 实现 HTTPToolAdapter
□ 实现 CLIToolAdapter
□ 实现 SandboxToolAdapter
□ 实现 tool_calls 记录
```

验收：

```text
□ MCP calculator 可调用
□ HTTP echo/weather 示例可调用
□ CLI git status 示例可调用
□ Sandbox Python 命令可调用
□ 每次调用都有 tool_calls 记录
```

---

### Day 5：DockerSandbox + CLI/Sandbox 安全

```text
□ 实现 DockerSandbox.create()
□ 实现 DockerSandbox.execute()
□ 实现 DockerSandbox.destroy()
□ 实现 DockerSandbox.run_once()
□ 增加危险命令检查
□ 增加 timeout
□ 增加 mem_limit / network_disabled / pids_limit
□ 写入 sandbox_executions
```

验收：

```text
□ python -c "print(sum(range(10)))" 返回 45
□ 错误命令返回 stderr
□ 超时命令会终止
□ 危险命令被拒绝
□ sandbox_executions 有记录
```

---

### Day 6：Celery Task Runtime + LangGraph + PostgresSaver

```text
□ 配置 Redis
□ 配置 Celery
□ 实现 TaskService.submit_task
□ 实现 task_worker
□ 实现 LangGraph workflow
□ 接入 PostgresSaver
□ 每个节点写 task_events
□ 任务状态更新
```

验收：

```text
□ 提交任务立即返回 task_id / run_id / trace_id
□ Worker 异步执行
□ 任务状态 QUEUED -> RUNNING -> SUCCESS / FAILED
□ LangGraph checkpoint 写入 PostgreSQL
```

---

### Day 7：ResultSummarizer + 完整 AgentHarness 链路

```text
□ 实现 ResultSummarizerService
□ summarize_result 调用 LLM
□ 工具失败时总结 stderr
□ 权限拒绝时总结拒绝原因
□ AgentHarness.run 完整串联所有模块
```

验收：

```text
□ 完整任务能从 user_input 跑到 final_answer
□ llm_calls 记录 intent 和 summary 两次调用
□ task_events 记录完整链路
```

---

### Day 8：Streamlit Dashboard

```text
□ 展示任务总数
□ 展示成功率 / 失败率
□ 展示最近任务
□ 展示 task_events
□ 展示 tool_calls
□ 展示 llm_calls
□ 展示 sandbox_executions
□ 展示 tool health
```

验收：

```text
□ streamlit run dashboard/streamlit_app.py 能启动
□ 能看到完整任务链路
□ 能看到 LLM 调用耗时和错误
□ 能看到工具调用和沙箱日志
```

---

### Day 9~10：README + Demo + 测试

```text
□ 完成 README
□ 完成 TOOLHUB.md 示例
□ 完成 demo_flow.ps1
□ 补充 pytest
□ 录制 demo 视频
□ 整理简历描述
□ 整理博客大纲
```

验收：

```text
□ 新机器按 README 可启动
□ demo_flow.ps1 可跑通主链路
□ 简历项目描述可直接使用
```

---

# 第十一部分：Demo 设计

## 34. Demo 1：HTTP Tool

```text
1. 启动 simple_echo_server.py
2. 注册 HTTP Tool
3. 提交任务：“调用 echo 工具返回 hello”
4. LLMIntentService 识别 HTTP_CALL
5. ToolRouter 选择 HTTP Tool
6. PermissionEngine 允许
7. HTTPToolAdapter 调用 API
8. ResultSummarizer 总结结果
```

---

## 35. Demo 2：CLI Tool

```text
1. 注册 git-status CLI Tool
2. 提交任务：“查看当前项目 git 状态”
3. LLMIntentService 识别 CLI_EXECUTION
4. ToolRouter 选择 git-status
5. PermissionEngine 判断 MEDIUM 风险
6. CLIToolAdapter 通过 DockerSandbox 执行 git status
7. 返回 stdout/stderr
8. ResultSummarizer 总结
```

---

## 36. Demo 3：Sandbox Tool

```text
1. 注册 python-sandbox
2. 提交任务：“运行 Python 代码 print(sum(range(10)))”
3. 选择 python-sandbox
4. FULL_EXECUTE 模式允许执行
5. DockerSandbox 执行
6. stdout = 45
7. Dashboard 展示 tool_calls / sandbox_executions / llm_calls
```

---

## 37. Demo 4：权限拒绝

```text
1. SAFE_EXECUTE 模式提交高风险命令
2. ToolRouter 选择 HIGH risk Tool
3. PermissionEngine 拒绝
4. 任务状态变为 DENIED 或 WAITING_APPROVAL
5. ResultSummarizer 解释拒绝原因
6. Dashboard 展示 permission event
```

---

# 第十二部分：安全设计

## 38. 禁止事项

```text
1. 不允许用户提交 stdio MCP command
2. 不允许裸跑宿主机 CLI 命令
3. CLI 默认走 DockerSandbox
4. 不允许 Docker 容器挂载宿主机敏感目录
5. 不允许容器默认开启网络
6. 不允许无限时执行命令
7. 不允许无限内存
8. 不允许直接执行 rm -rf / 等危险命令
9. 不允许 HTTPToolAdapter 默认访问内网地址
10. 不允许 LLM 决定最终权限
```

---

## 39. Docker 沙箱默认策略

```text
network_disabled = true
mem_limit = 256m
read_only = true
pids_limit = 128
cap_drop = ["ALL"]
security_opt = ["no-new-privileges"]
timeout = 30
```

---

## 40. 危险命令示例

```text
rm -rf /
mkfs
shutdown
reboot
:(){ :|:& };:
dd if=
curl | sh
wget | sh
chmod 777 /
```

---

# 第十三部分：README 要求

## 41. README 结构

```text
# ToolHub

## 1. 项目简介
## 2. 为什么需要 Agent Harness
## 3. CLI / MCP / Harness 的关系
## 4. Claude Code 架构启发
## 5. 核心功能
## 6. 架构图
## 7. 技术栈
## 8. 快速开始
## 9. PostgreSQL 初始化
## 10. API 文档
## 11. Demo 流程
## 12. TOOLHUB.md 项目规则
## 13. Tool Adapter 设计
## 14. PermissionEngine 设计
## 15. Docker Sandbox 安全策略
## 16. LangGraph + PostgresSaver 状态恢复
## 17. Celery Task Runtime
## 18. LLM Intent / Summary 节点
## 19. Dashboard 展示
## 20. 后续优化
```

README 必须强调：

```text
ToolHub 不是简单 CRUD 项目，也不是单纯 MCP 注册中心，而是围绕 CLI / IDE Agent 执行链路中的上下文加载、LLM 意图理解、工具治理、权限控制、安全执行、任务恢复和可观测性设计的 Agent Harness 平台。
```

---

# 第十四部分：测试计划

## 42. 单元测试

```text
□ ToolRepository
□ TaskRepository
□ EventRepository
□ ToolCallRepository
□ LLMCallRepository
□ ToolRegistryService
□ ToolRouterService
□ PermissionEngine
□ CommandPolicy
□ HTTPToolAdapter
□ CLIToolAdapter
□ SandboxToolAdapter
□ LLMIntentService JSON parse fallback
□ ResultSummarizerService
□ InstructionLoader
```

---

## 43. 集成测试

```text
□ PostgreSQL init_db
□ Tool 注册 -> 查询 -> 搜索 -> 禁用 -> 删除
□ LLMIntentService -> ToolRouter
□ PermissionEngine run_mode 判断
□ HTTPToolAdapter 调用 echo server
□ CLIToolAdapter 调用 git status
□ SandboxToolAdapter 执行 Python
□ Celery submit -> worker -> task success
□ LangGraph workflow 完整执行
□ PostgresSaver checkpoint 写入
□ Dashboard 查询数据
```

---

## 44. Demo 验收

```text
□ 注册 MCP Tool
□ 注册 HTTP Tool
□ 注册 CLI Tool
□ 注册 SANDBOX Tool
□ 提交 HTTP 任务
□ 提交 CLI 任务
□ 提交 Sandbox 任务
□ 权限拒绝任务
□ 查询 task status
□ 查询 task events
□ 查询 tool_calls
□ 查询 llm_calls
□ 查看 sandbox_executions
□ Dashboard 能看到完整链路
```

---

# 第十五部分：简历写法

## 45. Agent Infra 岗位版本

```text
ToolHub：面向 CLI / IDE Agent 的 Agent Harness 平台
- 设计 Agent Harness 执行框架，将任务拆分为项目规则加载、LLM 意图理解、工具路由、权限检查、工具执行和 LLM 结果总结等阶段，并通过 LangGraph + PostgreSQL Checkpointer 保存执行状态。
- 实现 Tool Registry 与 Tool Adapter 层，统一管理 MCP、HTTP、CLI、Sandbox 四类工具，支持工具注册、检索、健康检查、风险分级、启停控制和调用审计。
- 设计 PermissionEngine 与 Run Mode 机制，支持 PLAN_ONLY / SAFE_EXECUTE / FULL_EXECUTE 三种运行模式，对高风险工具和危险命令进行拦截或审批控制。
- 基于 Docker SDK 封装 Sandbox Runtime，为 Agent 生成命令提供隔离执行环境，支持 CPU、内存、网络、进程数和超时限制，并记录 stdout、stderr、exit_code 和执行耗时。
- 基于 Redis + Celery 构建 Task Runtime，支持 Agent 长任务异步调度、状态查询、失败重试和执行事件审计。
- 使用 Streamlit 构建 Observability Dashboard，展示任务状态、Tool 调用、LLM 调用、沙箱执行日志、失败率和平均耗时。
```

---

## 46. Agent 开发岗位版本

```text
ToolHub：Agent Tool Runtime 与 Harness 平台
- 使用 LangGraph 编排 Agent 执行流程，将任务拆分为 LLM 意图理解、工具选择、权限检查、工具执行和 LLM 结果总结多个节点，并通过 PostgreSQL checkpoint 保存中间状态。
- 设计 Tool Router，根据用户意图从 Tool Registry 中检索候选工具，并结合工具类型、标签、描述、健康状态和风险等级完成工具选择。
- 实现 MCP / HTTP / CLI / Sandbox 四类 ToolAdapter，将不同工具调用方式抽象为统一接口，降低 Agent 工具接入复杂度。
- 封装 Docker Sandbox Runtime，解决 Agent 生成命令直接运行带来的安全风险，支持资源限制、超时控制、异常隔离和执行审计。
- 设计 TOOLHUB.md 项目规则加载机制，将项目约束、安全规则和输出偏好注入 LLM 意图理解与结果总结节点。
```

---

# 第十六部分：面试讲解思路

不要这样讲：

```text
我用了 FastAPI、Celery、Docker、LangGraph、MCP。
```

建议这样讲：

```text
Agent 真正跑起来并不是只调用 LLM API，它还需要一层 Harness 来管理上下文、工具、权限、执行环境、状态和日志。

我做 ToolHub 的核心目标是实现一个 Agent Harness：

第一，上下文加载：通过 TOOLHUB.md 把项目规则、安全约束和输出偏好注入 LLM 节点。

第二，意图理解：通过 LLMIntentService 将用户自然语言转换为结构化 intent，但 LLM 不负责最终权限决策。

第三，工具治理：用 Tool Registry 管理 MCP、HTTP、CLI、Sandbox 四类工具，支持注册、检索、健康检查、启停控制和风险分级。

第四，工具路由：通过 Tool Router 根据 intent、tags、description、health_status 和 risk_level 选择合适工具。

第五，权限控制：通过 PermissionEngine 和 Run Mode 控制工具执行，高风险工具在 SAFE_EXECUTE 下会被拒绝或进入审批状态。

第六，安全执行：Agent 生成的命令不直接在宿主机执行，而是进入 DockerSandbox，限制 CPU、内存、网络、进程数和超时时间。

第七，状态恢复：长任务通过 Celery 异步执行，执行流程由 LangGraph 编排，并通过 PostgreSQL checkpointer 保存每一步状态。

第八，可观测性：所有 task_events、tool_calls、llm_calls、sandbox_executions 都会入库，并通过 Dashboard 展示完整链路。
```

---

# 第十七部分：最终验收清单

## 47. 功能验收

```text
□ FastAPI 服务能启动
□ PostgreSQL 表能初始化
□ Redis 能启动
□ Celery worker 能启动
□ TOOLHUB.md 能加载
□ LLMClient 能调用
□ understand_intent 使用 LLM
□ summarize_result 使用 LLM
□ llm_calls 有记录
□ Tool 支持 MCP / HTTP / CLI / SANDBOX
□ Tool 可以注册 / 搜索 / 启用 / 禁用 / 删除
□ ToolRouter 可以选择工具
□ PermissionEngine 可以根据 run_mode 拒绝高风险工具
□ MCPToolAdapter 可调用
□ HTTPToolAdapter 可调用
□ CLIToolAdapter 可调用并默认走 DockerSandbox
□ SandboxToolAdapter 可调用
□ DockerSandbox 可执行 Python 命令
□ DockerSandbox 可限制超时
□ task_events 有完整链路
□ tool_calls 有完整工具调用记录
□ sandbox_executions 有记录
□ LangGraph workflow 可执行
□ PostgresSaver checkpoint 可保存
□ Dashboard 可展示任务、工具、LLM、沙箱日志
```

---

## 48. 工程验收

```text
□ API / Harness / LLM / Security / Tool / Runtime / Repository 分层清楚
□ 配置集中管理
□ 错误处理统一
□ 日志清晰
□ 数据库初始化脚本可重复执行
□ README 完整
□ Demo 脚本可运行
□ 有基础 pytest
□ 能用一条 demo 流程展示项目价值
```

---

## 49. 简历验收

```text
□ 能讲清楚为什么需要 Agent Harness
□ 能讲清楚 CLI / MCP / Harness 的关系
□ 能讲清楚 Claude Code 架构对项目的启发
□ 能讲清楚 Tool Registry 的设计
□ 能讲清楚 Tool Adapter 的设计
□ 能讲清楚 PermissionEngine 和 Run Mode
□ 能讲清楚 LLM 节点负责什么、不负责什么
□ 能讲清楚 DockerSandbox 的安全策略
□ 能讲清楚 Celery 为什么用于长任务
□ 能讲清楚 LangGraph + PostgreSQL checkpoint 如何支持恢复
□ 能讲清楚 Dashboard 展示了哪些指标
□ 能讲清楚和智能工单项目的关系
```

---

# 第十八部分：最终建议

第一阶段目标不是做一个完整商业化平台，而是做一个能支撑面试表达的 Agent Harness MVP。

推荐主线：

```text
PostgreSQL
    ↓
AgentHarness Core
    ↓
TOOLHUB.md InstructionLoader
    ↓
LLM IntentService
    ↓
Tool Registry
    ↓
Tool Router
    ↓
PermissionEngine + Run Mode
    ↓
ToolAdapterDispatcher
    ↓
MCP / HTTP / CLI / Sandbox Adapter
    ↓
Docker Sandbox Runtime
    ↓
Celery Task Runtime
    ↓
LangGraph + PostgresSaver
    ↓
LLM ResultSummarizer
    ↓
Observability Dashboard
    ↓
README + Demo + 简历包装
```

做到这个程度后，这个项目就可以和智能工单项目形成互补：

```text
智能工单平台：
  证明你能做 Agent 业务应用。

ToolHub：
  证明你理解 CLI / IDE Agent 背后的 Agent Harness，包括上下文加载、LLM 意图理解、工具治理、权限控制、安全执行、任务调度、状态恢复和可观测性。
```

一句话总结：

```text
MCP 是 ToolHub 的一种工具接入协议；Agent Harness 才是 ToolHub 的真正项目主线。
```
