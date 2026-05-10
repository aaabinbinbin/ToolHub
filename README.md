# ToolHub

ToolHub 是一个面向 CLI / IDE Agent 的 Agent Tool Runtime / Agent Harness MVP。它把用户输入转换成结构化意图，完成工具路由、权限检查、安全执行、后台任务调度、状态检查点、结果总结和可观测性展示。

补充文档：

- [架构说明](docs/architecture.md)
- [后续完善计划](docs/toolhub_improvement_plan.md)
- [简历与面试材料](docs/resume_and_interview.md)

## 当前基线状态

当前项目已经完成 Agent Harness MVP 的主链路，可以作为后续完善的基线：

- API 服务可以启动，并提供 `/health` 和 Swagger 文档
- PostgreSQL / Redis 可通过 Docker Compose 作为本地运行依赖
- 数据库结构通过 Alembic migration 管理
- Tool Registry 支持 MCP / HTTP / CLI / Sandbox 四类工具元数据
- 支持从 OpenAPI spec 导入 HTTP 工具
- 工具注册会写入 `tool_versions` 版本快照，并根据调用历史刷新质量指标
- IntentService 可以将自然语言任务转换为结构化 intent 和 tool_input
- ToolRouter 可以输出 top-k candidates，并融合 intent、工具类型、schema、关键词、健康状态、质量指标和可选 LLM rerank 做解释型路由
- PermissionEngine 支持 `PLAN_ONLY`、`SAFE_EXECUTE`、`FULL_EXECUTE` 三种 run mode
- HIGH 风险工具在 `SAFE_EXECUTE` 下会进入 `WAITING_APPROVAL`，可通过审批 API 继续或拒绝
- CLI / Sandbox 工具默认通过 DockerSandbox 隔离执行，Sandbox 支持 Python / Node.js 运行时骨架
- Celery worker 可以异步执行后台任务
- LangGraph workflow 可以串联 instruction loading、intent、planning、routing、permission、execution、observation、summary
- Harness 支持 LLM planner 优先的多步执行；LLM 不可用时会退回确定性规则
- Harness 支持任务级 `max_steps`、`max_retries`、`timeout_seconds`，并支持失败后基于 observation 有边界地修正参数重试
- 任务支持取消，工具调用支持 replay，方便复现失败输入和调试工具行为
- Trace API 可以按 `trace_id` 聚合 task、events、tool_calls、llm_calls、sandbox_executions 和 approvals
- `PLAN_ONLY` 模式只生成计划和总结，不会执行工具
- PostgreSQL 中会记录 `tasks`、`task_events`、`tool_calls`、`llm_calls`、`sandbox_executions`
- Streamlit Dashboard Console 可以查看 Overview、Trace、Task、Routing、Replay 和原始审计表
- 当前测试基线：`55 passed`

当前仍然是 MVP，不应包装成生产级平台。项目边界建议这样理解：

- 已经具备完整 Agent Harness 主链路：注册、路由、权限、执行、审计、trace、replay 和 Console。
- 当前不是生产级 SaaS，也不建议宣传成企业级多租户平台。
- Dashboard 是功能型 Console，不是独立前端产品。
- ToolRouter 已具备 top-k、schema-aware、quality-aware 和 LLM rerank 接口，但 embedding / pgvector 语义召回还没有作为强依赖接入。
- 审批和治理模型已具备骨架，但真实登录、完整 RBAC、组织级权限体系仍属于后续增强项。

## 短期完善目标

后续重点不再是证明 demo 能跑，而是把它打磨成更像真实 Agent Infra 的项目：

1. 接入 embedding / pgvector 语义召回，增强大量工具场景下的检索能力。
2. 将 Streamlit Console 进一步产品化，或替换为独立前端。
3. 补齐真实登录、RBAC、组织 / workspace 级权限治理。
4. 扩展 trace 指标、错误分类、SSE / WebSocket 实时事件流。
5. 增加更完整的集成测试、安全测试、permission eval 和恶意输入 eval。
6. 准备更多真实第三方 MCP / HTTP 工具接入案例。

详细分步方案见 [docs/toolhub_improvement_plan.md](docs/toolhub_improvement_plan.md)。

## 核心能力

- Tool Registry：注册、搜索、启用、禁用和删除 MCP / HTTP / CLI / Sandbox 工具
- OpenAPI Import：从 OpenAPI JSON 导入 HTTP 工具
- Tool Versions：注册工具时保存版本快照，并维护 success_rate / avg_duration_ms / quality_score
- LLM IntentService：将用户自然语言转换为 intent 和 tool_input
- StepPlanner：LLM 优先生成多步计划，系统负责清洗、限步和规则兜底
- ToolRouter + PermissionEngine：根据意图、工具类型、schema、质量指标、风险等级和 run_mode 选择并检查工具；LLM rerank 只给候选排序建议
- ToolAdapter：统一调用 HTTP、CLI、Sandbox 和 MCP 工具
- DockerSandbox：隔离执行 CLI / Python / Node.js，记录 stdout、stderr、exit_code、耗时和 artifact 引用
- Celery Task Runtime：任务提交后进入 Redis 队列，由 worker 后台执行
- LangGraph + PostgresSaver：编排 Harness 节点并写入 PostgreSQL checkpoint
- ResultSummarizer：将工具结果总结为 `final_answer`
- Dashboard：展示 task_events、tool_calls、llm_calls、sandbox_executions 和工具健康

## 技术栈

- FastAPI
- PostgreSQL
- Redis
- Celery
- LangGraph
- Docker SDK
- OpenAI-compatible SDK
- Alembic
- Streamlit
- pytest

## 本地依赖

需要先准备：

- Python 3.12+
- uv
- Docker Desktop
- PostgreSQL / Redis 容器

项目可以只启动 PostgreSQL / Redis 做本地开发：

```bash
docker compose up -d postgres redis
```

也可以直接启动完整本地服务：

```bash
docker compose up --build
```

完整 compose 会启动：

- `postgres`
- `redis`
- `api`
- `worker`
- `dashboard`

PostgreSQL 本机连接信息：

```text
host: localhost
port: 15432
database: toolhub
username: postgres
password: postgres
```

Redis：

```text
redis://localhost:6379/0
```

## 安装依赖

```bash
uv sync
```

## 初始化数据库

数据库结构由 Alembic migration 管理。初始化脚本会先确保数据库存在，再执行
`alembic upgrade head`：

```bash
.\.venv\Scripts\python.exe .\scripts\init_db.py
```

也可以直接使用 Alembic：

```bash
.\.venv\Scripts\alembic.exe upgrade head
```

## 启动 API

```bash
.\.venv\Scripts\uvicorn.exe app.main:app --host 127.0.0.1 --port 8000
```

访问：

```text
http://127.0.0.1:8000/docs
http://127.0.0.1:8000/health
http://127.0.0.1:8000/health/ready
```

## 启动 Celery Worker

Windows 本地建议使用 solo pool：

```bash
.\.venv\Scripts\celery.exe -A app.workers.celery_app worker --pool=solo --loglevel=INFO --concurrency=1
```

## 启动 Dashboard

如果默认 8501 被占用，可以使用 18501：

```bash
.\.venv\Scripts\streamlit.exe run dashboard/streamlit_app.py --server.port=18501
```

访问：

```text
http://localhost:18501
```

Dashboard 当前包含：

- Overview：任务成功率、失败数、最近任务
- Trace：按 `trace_id` 查看完整时间线和聚合审计数据
- Task：查看 `run_config`、取消状态、steps、observations、summary
- Routing：调试 top-k candidates、`score_breakdown`、`matched_signals` 和 rerank metadata
- Replay：从历史 `tool_call_id` 发起 replay，支持覆盖输入
- Raw Tables：查看工具调用、LLM 调用、沙箱执行和工具健康数据

## Demo

最终演示脚本会串起路由解释、HTTP 调用、MCP 调用、工具 replay、高风险权限预检和多步后台任务。运行前需要先启动 API；如果要看多步任务真正执行，还需要启动 Celery worker。Dashboard 可选，但推荐一起启动用于查看 trace。

```powershell
.\scripts\final_demo.ps1 -ApiBaseUrl http://127.0.0.1:8000 -DashboardUrl http://localhost:18501
```

脚本会完成：

- 初始化数据库并注册 canonical demo tools
- 调用 `/api/router/select` 展示 top-k candidates、score 和选择原因
- 直接执行 HTTP echo 工具并输出 `trace_id`
- 直接执行 MCP calculator 工具并输出结果
- 基于历史 `tool_call_id` 发起 replay
- 使用 `/api/harness/plan` 演示 `SAFE_EXECUTE` 下高风险 Sandbox 进入 `ASK`
- 提交多步 Agent task，轮询最终状态并输出 `final_answer`
- 打印 Trace API 和 Dashboard 入口，方便到 Console 中查看完整链路

仍然可以只注册 demo 工具：

```powershell
.\.venv\Scripts\python.exe .\scripts\seed_demo_tools.py
```

canonical demo 工具包括：

| 工具名 | 类型 | 当前用途 |
|---|---|---|
| `toolhub-demo-mcp-calculator` | MCP | MCP 调用链路演示 |
| `toolhub-demo-http-echo` | HTTP | HTTPToolAdapter 内置 echo |
| `toolhub-demo-http-public-api` | HTTP | 通过 SSRF 防护调用 public HTTPS echo API |
| `toolhub-demo-cli-git-status` | CLI | DockerSandbox 内执行安全 `git status --short` |
| `toolhub-demo-cli-git-diff` | CLI | DockerSandbox 内执行安全 `git diff` |
| `toolhub-demo-cli-git-log` | CLI | DockerSandbox 内执行配置化 `git log --oneline -n` |
| `toolhub-demo-python-sandbox` | SANDBOX | DockerSandbox 内执行 Python 代码 |

## 主要 API

### 注册工具

```http
POST /api/tools/register
```

### 同步 MCP 工具

ToolHub 现在提供 MCP client 封装，可以将 MCP server 暴露的 tools 同步到 Tool Registry。

同步 mock calculator：

```powershell
.\.venv\Scripts\python.exe .\scripts\sync_mcp_tools.py --mcp-url mock://calculator --transport mock --name-prefix synced-demo --tag demo
```

同步真实 MCP server 时使用对应 transport：

```powershell
# Streamable HTTP
.\.venv\Scripts\python.exe .\scripts\sync_mcp_tools.py --mcp-url https://example.com/mcp --transport streamable-http --name-prefix remote

# SSE
.\.venv\Scripts\python.exe .\scripts\sync_mcp_tools.py --mcp-url https://example.com/sse --transport sse --name-prefix remote

# stdio: command 放在 stdio:// 后，参数用 args 重复传入
.\.venv\Scripts\python.exe .\scripts\sync_mcp_tools.py --mcp-url "stdio://python?args=-m&args=my_mcp_server" --transport stdio --name-prefix local
```

同步后的 MCP tool 会使用：

- `mcp_url` 保存 server 地址
- `transport` 保存连接方式
- `endpoint` 保存远端 MCP tool name
- `input_schema` / `output_schema` 保存远端 schema

### 配置 CLI Policy

CLI 工具不执行自由文本 shell 命令，而是通过配置化 rule 生成 argv。默认配置位于：

```text
config/cli_policy.json
```

内置 rule pack 位于：

```text
config/cli_policies/
```

可以通过环境变量覆盖：

```env
CLI_POLICY_PATH=config/cli_policy.json
CLI_POLICY_DIR=config/cli_policies
```

当前内置/配置化 demo 规则：

| rule_id | 说明 |
|---|---|
| `cli://git/status-short` | 只读 `git status --short` |
| `cli://git/diff` | 只读 `git diff`，支持 `staged` 和 `path` 参数 |
| `cli://git/log-oneline` | 只读 `git log --oneline -n`，支持 `max_count` 参数 |

CLI Adapter 只接受 `rule_id` 和结构化 `args`，并继续通过 DockerSandbox 执行。

### 从 OpenAPI 导入 HTTP 工具

```powershell
.\.venv\Scripts\python.exe .\scripts\import_openapi_tools.py .\examples\openapi.json --base-url https://api.example.com --name-prefix example
```

也可以调用 API：

```http
POST /api/openapi/import
```

导入后会为每个 OpenAPI operation 创建 HTTP 工具，并写入 `tool_versions` 版本快照。

### 搜索工具

```http
GET /api/tools/search?q=git
```

### 预演 Harness

```http
POST /api/harness/plan
```

只执行意图理解、工具路由和权限检查，不执行工具。ToolRouter 会结合工具
`input_schema` 校验 IntentService 生成的 `tool_input`，并在路由结果中返回
`candidate_details`、`score_breakdown`、`matched_signals`、`schema_match`、`missing_fields` 和 `rejection_reason`。

### 直接测试工具路由

```http
POST /api/router/select
```

请求可以显式传入 `tool_input`，用于调试 schema-aware 路由：

```json
{
  "user_input": "请计算 1 + 2",
  "intent": "CALCULATE",
  "suggested_tool_type": "MCP",
  "top_k": 5,
  "enable_llm_rerank": false,
  "tool_input": {
    "expression": "1 + 2"
  }
}
```

如果候选工具缺少必填字段或包含未声明字段，Router 不会选择该工具执行。
质量指标只在已经相关的候选之间排序，不会单独触发工具命中。

### 路由评估

```powershell
.\.venv\Scripts\python.exe .\scripts\eval_tool_routing.py --top-k 5
```

评估样例位于：

```text
evals/tool_routing_cases.jsonl
```

脚本会输出 `accuracy`、`top_k_recall` 和 `no_tool_precision`。

### 提交后台任务

```http
POST /api/tasks
```

后台任务会先进入 `make_plan` 节点。当前 planner 的执行策略是：

- 优先调用 LLM，根据用户目标、intent 和可用工具摘要生成 `steps`
- 系统对 LLM 输出做结构化清洗、工具类型归一化、CLI `rule_id` 归一化和最大步数限制
- LLM 不可用或输出不可用时，退回确定性规则，保证 git / sandbox 等核心 demo 稳定
- `PLAN_ONLY` 只返回计划和 summary，不会进入工具路由和执行节点

请求示例：

```json
{
  "user_input": "请查看 git status",
  "run_mode": "SAFE_EXECUTE",
  "priority": "default",
  "run_config": {
    "max_steps": 3,
    "max_retries": 1,
    "timeout_seconds": 300
  }
}
```

响应示例：

```json
{
  "task_id": "...",
  "run_id": "...",
  "trace_id": "...",
  "status": "QUEUED"
}
```

多步 CLI 示例：

```json
{
  "user_input": "请查看 git status 和 diff",
  "run_mode": "SAFE_EXECUTE",
  "priority": "default"
}
```

该请求会生成多个计划步骤，任务结果中包含：

- `result.plan`
- `result.steps`
- `result.observations`
- `result.stop_reason`

### 审批高风险任务

HIGH 风险工具在 `SAFE_EXECUTE` 下不会直接执行，而是进入 `WAITING_APPROVAL`。

查询待审批请求：

```http
GET /api/approvals/pending
```

审批通过：

```http
POST /api/approvals/{approval_id}/approve
```

```json
{
  "decided_by": "local-user",
  "decision_reason": "允许本次沙箱执行"
}
```

审批通过后，任务会切换到 `FULL_EXECUTE` 并重新入队执行。

审批拒绝：

```http
POST /api/approvals/{approval_id}/reject
```

```json
{
  "decided_by": "local-user",
  "decision_reason": "本次请求不允许执行"
}
```

### 查询任务

```http
GET /api/tasks/{task_id}
GET /api/tasks/{task_id}/events
POST /api/tasks/{task_id}/cancel
POST /api/tool-calls/{tool_call_id}/replay
GET /api/traces/{trace_id}
```

### 查询 Trace 链路

```http
GET /api/traces/{trace_id}
```

Trace 响应会聚合：

- `tasks`
- `task_events`
- `tool_calls`
- `llm_calls`
- `sandbox_executions`
- `approval_requests`
- `timeline`
- `summary.error_types`

这用于排查一次 Agent 执行为什么选了某个工具、在哪个节点失败、是否触发审批、是否产生 replay。

## 运行模式

ToolHub 支持三种 run_mode：

- `PLAN_ONLY`：只规划，不执行工具
- `SAFE_EXECUTE`：允许低/中风险工具执行，拒绝高风险工具
- `FULL_EXECUTE`：允许高风险工具进入执行阶段

## 审计表

核心审计数据保存在 PostgreSQL：

- `tasks`
- `task_events`
- `tool_calls`
- `sandbox_executions`
- `llm_calls`
- `tool_health_checks`

Dashboard 会从这些表中展示完整链路。

## 测试

```bash
.\.venv\Scripts\pytest.exe
```

当前测试覆盖：

- HTTP SSRF / 危险请求头策略
- CLI rule_id + 结构化参数策略
- ToolInputNormalizer
- ResultSummarizer fallback
- ToolRouter 弱匹配 NO_TOOL
