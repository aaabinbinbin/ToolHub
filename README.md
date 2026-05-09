# ToolHub

ToolHub 是一个面向 CLI / IDE Agent 的 Agent Harness 平台。它把用户输入转换成结构化意图，完成工具路由、权限检查、安全执行、后台任务调度、状态检查点、结果总结和可观测性展示。

## 当前基线状态

当前项目已经完成 Agent Harness MVP 的主链路，可以作为后续完善的基线：

- API 服务可以启动，并提供 `/health` 和 Swagger 文档
- PostgreSQL / Redis 可通过 Docker Compose 作为本地运行依赖
- Tool Registry 支持 MCP / HTTP / CLI / Sandbox 四类工具元数据
- IntentService 可以将自然语言任务转换为结构化 intent 和 tool_input
- ToolRouter 可以根据 intent、工具类型、名称、标签和描述选择候选工具
- PermissionEngine 支持 `PLAN_ONLY`、`SAFE_EXECUTE`、`FULL_EXECUTE` 三种 run mode
- CLI / Sandbox 工具默认通过 DockerSandbox 隔离执行
- Celery worker 可以异步执行后台任务
- LangGraph workflow 可以串联 instruction loading、intent、routing、permission、execution、summary
- PostgreSQL 中会记录 `tasks`、`task_events`、`tool_calls`、`llm_calls`、`sandbox_executions`
- Streamlit Dashboard 可以查看任务、事件、工具调用、LLM 调用和沙箱执行日志
- 当前测试基线：`13 passed`

当前仍然是 MVP，不应包装成生产级平台。主要缺口：

- MCP Adapter 仍以 demo 能力为主，还没有完整 MCP client / tool sync
- Harness 仍是单步线性链路，还没有多步 Agent loop
- CLI policy 仍是代码内置规则，还没有配置化策略包
- 权限系统仍以 `risk_level + run_mode` 为主，还没有审批流
- Dashboard 偏观测表格，还不是完整 Console
- Demo 覆盖面偏窄，需要补齐 MCP / HTTP / CLI / Sandbox 四类稳定链路

## 短期完善目标

后续优先把项目从“能跑通的 MVP”完善成“可展示、可试用的 Agent Tool Runtime / Harness MVP”：

1. 补齐四类真实样例工具：MCP、HTTP、CLI、Sandbox。
2. 实现真实 MCP client，支持同步 MCP tools 和调用真实 MCP tool。
3. 将 CLI policy 从硬编码改为 YAML / JSON 配置。
4. 升级 ToolRouter，使其理解工具 `input_schema` 并能解释选择原因。
5. 增加多步 Agent Harness，支持连续调用多个工具并记录 observations。
6. 增加 `ALLOW / ASK / DENY` 权限决策和高风险审批流。
7. 将 Dashboard 增强为基础 Console，支持工具管理、任务提交、trace 查看和审批处理。
8. 补充测试、评估集和稳定 Demo，作为简历和面试展示素材。

详细分步方案见 [docs/toolhub_improvement_plan.md](docs/toolhub_improvement_plan.md)。

## 核心能力

- Tool Registry：注册、搜索、启用、禁用和删除 MCP / HTTP / CLI / Sandbox 工具
- LLM IntentService：将用户自然语言转换为 intent 和 tool_input
- ToolRouter + PermissionEngine：根据意图、工具类型、风险等级和 run_mode 选择并检查工具
- ToolAdapter：统一调用 HTTP、CLI、Sandbox 和 MCP demo 工具
- DockerSandbox：隔离执行 CLI / Python，记录 stdout、stderr、exit_code 和耗时
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
- Streamlit
- pytest

## 本地依赖

需要先准备：

- Python 3.12+
- uv
- Docker Desktop
- PostgreSQL / Redis 容器

项目默认使用 Docker Compose 中的 PostgreSQL 和 Redis：

```bash
docker compose up -d postgres redis
```

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

```bash
.\.venv\Scripts\python.exe .\scripts\init_db.py
```

## 启动 API

```bash
.\.venv\Scripts\uvicorn.exe app.main:app --host 127.0.0.1 --port 8000
```

访问：

```text
http://127.0.0.1:8000/docs
http://127.0.0.1:8000/health
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

## Demo

先注册或复用四类 demo 工具：

```powershell
.\.venv\Scripts\python.exe .\scripts\seed_demo_tools.py
```

当前 seed 会准备以下 canonical demo 工具：

| 工具名 | 类型 | 当前用途 |
|---|---|---|
| `toolhub-demo-mcp-calculator` | MCP | calculator demo，后续 Step 3 替换为真实 MCP client |
| `toolhub-demo-http-echo` | HTTP | HTTPToolAdapter 内置 mock echo |
| `toolhub-demo-http-public-api` | HTTP | 通过 SSRF 防护调用 public HTTPS echo API |
| `toolhub-demo-cli-git-status` | CLI | DockerSandbox 内执行安全 `git status --short` |
| `toolhub-demo-cli-git-diff` | CLI | DockerSandbox 内执行安全 `git diff` |
| `toolhub-demo-cli-git-log` | CLI | DockerSandbox 内执行配置化 `git log --oneline -n` |
| `toolhub-demo-python-sandbox` | SANDBOX | DockerSandbox 内执行 Python 代码 |

运行完整 demo：

```powershell
.\scripts\demo_flow.ps1
```

脚本会完成：

- 初始化数据库
- 注册或复用四类 canonical demo 工具
- 提交 `git status` 后台任务
- 轮询任务状态
- 打印 `final_answer`
- 打印任务事件链路

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

可以通过环境变量覆盖：

```env
CLI_POLICY_PATH=config/cli_policy.json
```

当前内置/配置化 demo 规则：

| rule_id | 说明 |
|---|---|
| `cli://git/status-short` | 只读 `git status --short` |
| `cli://git/diff` | 只读 `git diff`，支持 `staged` 和 `path` 参数 |
| `cli://git/log-oneline` | 只读 `git log --oneline -n`，支持 `max_count` 参数 |

CLI Adapter 只接受 `rule_id` 和结构化 `args`，并继续通过 DockerSandbox 执行。

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
`candidate_details`、`schema_match`、`missing_fields` 和 `rejection_reason`。

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
  "tool_input": {
    "expression": "1 + 2"
  }
}
```

如果候选工具缺少必填字段或包含未声明字段，Router 不会选择该工具执行。

### 提交后台任务

```http
POST /api/tasks
```

请求示例：

```json
{
  "user_input": "请查看 git status",
  "run_mode": "SAFE_EXECUTE",
  "priority": "default"
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

### 查询任务

```http
GET /api/tasks/{task_id}
GET /api/tasks/{task_id}/events
```

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
