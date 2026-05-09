# ToolHub

ToolHub 是一个面向 CLI / IDE Agent 的 Agent Harness 平台。它把用户输入转换成结构化意图，完成工具路由、权限检查、安全执行、后台任务调度、状态检查点、结果总结和可观测性展示。

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

运行完整 demo：

```powershell
.\scripts\demo_flow.ps1
```

脚本会完成：

- 初始化数据库
- 注册 Day9/10 示例 CLI 和 Sandbox 工具
- 提交 `git status` 后台任务
- 轮询任务状态
- 打印 `final_answer`
- 打印任务事件链路

## 主要 API

### 注册工具

```http
POST /api/tools/register
```

### 搜索工具

```http
GET /api/tools/search?q=git
```

### 预演 Harness

```http
POST /api/harness/plan
```

只执行意图理解、工具路由和权限检查，不执行工具。

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

