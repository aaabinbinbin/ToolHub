# ToolHub 后续完善计划

> 本文档用于规划 ToolHub 从当前 MVP / Demo 形态继续完善为可展示、可试用、可扩展的 Agent Tool Runtime / Agent Harness 平台。  
> 规划方式按“要完成的能力模块”组织，不按具体日期或开发事件排期。

---

## 1. 当前判断

ToolHub 当前已经具备一个 Agent Harness 的基础骨架：

- FastAPI API 服务
- Tool Registry
- LLM IntentService
- ToolRouter
- PermissionEngine
- MCP / HTTP / CLI / Sandbox Adapter 抽象
- Docker Sandbox
- Celery 后台任务
- LangGraph + PostgresSaver checkpoint
- PostgreSQL 审计表
- Streamlit Dashboard
- 基础 pytest 覆盖

但它现在仍然容易被看成“玩具 demo”，主要原因不是技术栈不够，而是下面几类能力还没有形成闭环：

- 真实工具生态不足，MCP 仍是 calculator demo。
- Harness 仍是单步线性链路，没有多步 Agent loop。
- 权限系统只有 `risk_level + run_mode`，缺少审批、策略和用户维度。
- Dashboard 偏数据库观测，不像一个真正的控制台。
- 工具路由仍是规则打分，没有语义召回、schema 匹配和评估集。
- Demo 只展示单点能力，没有形成“用户提交任务 -> 可控执行 -> 可追踪结果”的完整产品故事。

后续目标不是单纯堆功能，而是让项目从“能跑通”变成“能解释清楚价值、能被真实接入、能被稳定演示”。

---

## 2. 产品定位

### 2.1 推荐定位

```text
ToolHub = 面向 CLI / IDE Agent 的 Agent Tool Runtime / Agent Harness Console
```

它不应该只是：

```text
MCP 注册中心
工具 CRUD 后台
简单任务执行 demo
```

它应该强调：

```text
统一接入工具，统一治理权限，统一安全执行，统一记录审计，统一展示 Agent 工具调用链路。
```

### 2.2 核心用户

- 正在构建 CLI Agent / IDE Agent 的开发者
- 需要把 MCP、HTTP API、CLI 命令、Sandbox 能力统一交给 Agent 使用的团队
- 关心 Agent 工具调用安全、权限、审计和可观测性的工程团队

### 2.3 核心价值

- Agent 不直接碰危险工具，所有调用先进入 ToolHub。
- 工具能注册、发现、路由、调用、禁用、审计。
- 高风险操作有权限策略和审批边界。
- 所有任务有 `task_id / run_id / trace_id`，可追溯、可调试。
- CLI / Sandbox 执行默认隔离，避免宿主机被 Agent 直接操作。

---

## 3. 总体完善方向

后续完善分成七条主线：

1. 真实工具生态
2. 多步 Agent Harness
3. 权限与审批体系
4. 控制台与用户体验
5. 可观测性与调试能力
6. 工程化与部署能力
7. 测试、评估与演示资产

每条主线都应该有明确的“完成后看起来不像 demo”的验收标准。

---

## 4. 真实工具生态

### 4.1 目标

让 ToolHub 不再只靠 calculator、echo、git status 证明能力，而是能接入一组真实、有代表性的工具。

### 4.2 需要完成的内容

#### MCP 工具接入

- 实现真实 MCP client。
- 支持连接 MCP server。
- 支持拉取 `tools/list`。
- 支持读取 MCP tool 的 name、description、input schema。
- 支持按 MCP tool schema 发起调用。
- 支持记录 MCP 调用输入、输出、错误、耗时。
- 支持 MCP server 健康检查。

#### HTTP 工具接入

- HTTP 工具支持 OpenAPI / JSON Schema 描述。
- 注册 HTTP 工具时校验 endpoint、method、headers、body schema。
- 支持 GET / POST / PUT / PATCH / DELETE。
- 支持 query params、path params、JSON body。
- 支持响应体截断、敏感响应头脱敏。
- 保持 SSRF 防护、重定向防护、私网访问限制。

#### CLI 工具接入

- 将当前硬编码 CLI rule 改成配置化规则。
- 支持从 YAML / JSON / 数据库加载 CLI command policy。
- 每条 CLI rule 包含：
  - rule_id
  - description
  - argv_template
  - params schema
  - risk_level
  - effect: `ALLOW / ASK / DENY`
  - sandbox image
  - timeout / mem_limit / network policy
- 默认提供一组安全只读规则：
  - `git status`
  - `git diff`
  - `git log`
  - `pytest --collect-only`
  - `python --version`

#### Sandbox 工具接入

- 支持 Python code runner。
- 支持 Node.js code runner。
- 支持只读 workspace 挂载。
- 支持可配置网络开关。
- 支持执行产物收集，例如 stdout、stderr、生成文件列表。
- 支持执行超时、内存限制、进程数限制。

### 4.3 验收标准

- 能注册并调用至少 2 个真实 MCP server 工具。
- 能注册并调用至少 3 个真实 HTTP API 工具。
- CLI rule 不再写死在代码里。
- Sandbox 能运行 Python 和 Node.js 示例。
- 每类工具都有成功、失败、权限拒绝三类演示案例。

---

## 5. 多步 Agent Harness

### 5.1 目标

把当前“一次意图理解 -> 一次工具调用 -> 一次总结”的线性流程，升级成可执行多步任务的 Agent Harness。

### 5.2 需要完成的内容

#### Agent Loop

新增循环结构：

```text
load_instructions
  -> understand_goal
  -> make_plan
  -> select_tool
  -> check_permission
  -> execute_tool
  -> observe_result
  -> decide_next_step
  -> summarize_result
```

`decide_next_step` 根据执行结果决定：

- 继续调用下一个工具
- 重试当前工具
- 请求用户确认
- 结束并总结
- 失败退出

#### Plan 与 Execute 分离

- `PLAN_ONLY` 模式只生成计划，不执行工具。
- `SAFE_EXECUTE` 模式允许低风险步骤自动执行。
- `FULL_EXECUTE` 模式仍需经过 policy，不等于无条件执行。

#### Step 级状态

新增或扩展状态结构：

- `steps`
- `current_step_index`
- `max_steps`
- `observations`
- `artifacts`
- `approval_requests`
- `stop_reason`

#### 失败恢复

- 工具失败后支持有限次数重试。
- 重试前允许 LLM 根据错误修正 tool_input。
- 对确定不可恢复的错误直接失败。
- 对权限错误进入 `DENIED` 或 `WAITING_APPROVAL`。

### 5.3 验收标准

- 一个任务可以连续调用多个工具。
- Dashboard 能看到每一步的输入、输出和决策。
- 工具失败后能重试或给出明确 stop reason。
- `PLAN_ONLY` 能输出完整执行计划而不产生工具调用。
- 多步任务最终 summary 能引用真实 observation，而不是泛泛回答。

---

## 6. 工具路由升级

### 6.1 目标

让 ToolRouter 从“关键词打分”升级成可解释、可评估、可扩展的工具选择系统。

### 6.2 需要完成的内容

#### Schema-aware Routing

- 路由时读取工具 input_schema。
- 检查 LLM 生成的 tool_input 是否满足工具 schema。
- 优先选择 schema 匹配度更高的工具。
- 工具参数缺失时返回缺失字段说明。

#### 语义召回

- 增加 tool embedding 字段。
- 使用 PostgreSQL + pgvector 存储工具向量。
- 支持按 user_input / intent summary 做语义召回。
- 语义召回结果与规则打分融合。

#### LLM Rerank

- 对 top-k 候选工具调用 LLM rerank。
- Rerank prompt 必须包含工具描述、schema、风险等级、历史成功率。
- LLM 只给建议，最终选择仍由系统校验。

#### 历史成功率加权

- 统计工具调用成功率、平均耗时、最近失败原因。
- 路由时降低长期失败或健康状态 DOWN 的工具权重。
- Dashboard 展示工具质量指标。

#### 路由评估集

- 建立 `evals/tool_routing_cases.jsonl`。
- 每条样例包含 user_input、expected_tool_type、expected_tool_name。
- 提供评估脚本计算 accuracy、top-k recall、no-tool precision。

### 6.3 验收标准

- 路由评估集不少于 30 条。
- 能输出 top-k 候选及选择原因。
- 对无匹配工具的请求能稳定返回 `NO_TOOL`。
- 工具 schema 不匹配时不会强行调用。

---

## 7. 权限与审批体系

### 7.1 目标

把权限系统从简单的风险等级判断，升级为可配置、可审计、可人工介入的治理系统。

### 7.2 需要完成的内容

#### Policy 模型

策略支持以下维度：

- tool_type
- tool_id
- action
- risk_level
- run_mode
- user_id
- workspace_id
- command rule
- HTTP domain
- network access
- filesystem mount

策略结果：

```text
ALLOW
ASK
DENY
```

#### 审批流

- 高风险工具可进入 `WAITING_APPROVAL`。
- 支持审批通过、拒绝、过期。
- 审批记录写入 `task_events`。
- 审批通过后任务可继续执行。

#### Secret 管理

- 工具注册时不直接保存明文 token。
- 支持环境变量引用或 secret reference。
- tool_calls / llm_calls / task_events 中自动脱敏。
- Dashboard 不展示敏感值。

#### 权限解释

每次权限判断都要给出：

- 命中的 policy
- 决策结果
- 拒绝或审批原因
- 用户下一步可操作建议

### 7.3 验收标准

- HIGH 风险工具在 SAFE_EXECUTE 下进入审批或拒绝。
- 审批通过后任务能继续执行。
- 策略命中原因能在 Dashboard 看到。
- 敏感字段不会出现在普通日志和 Dashboard 中。

---

## 8. 控制台与用户体验

### 8.1 目标

让 Dashboard 从“表格观测页”升级成真正的 ToolHub Console。

### 8.2 需要完成的内容

#### 工具管理

- 工具列表
- 工具详情
- 注册工具
- 编辑工具
- 启用 / 禁用工具
- 删除工具
- 触发健康检查
- 查看工具调用历史

#### 任务工作台

- 提交任务
- 选择 run_mode
- 查看任务状态
- 实时事件流
- 查看每一步输入输出
- 查看 final_answer
- 失败任务重跑
- 取消运行中任务

#### 审批中心

- 待审批任务列表
- 审批详情
- 允许 / 拒绝
- 审批原因输入
- 审批历史

#### 调试视图

- LangGraph checkpoint 查看
- task_events 时间线
- tool_calls 详情
- llm_calls prompt / response 查看
- sandbox stdout / stderr 查看

### 8.3 技术建议

短期可以继续用 Streamlit 完善内部控制台。

如果要做成更像产品的体验，建议新增独立前端：

- React / Vue
- API client
- SSE / WebSocket 实时事件
- Tailwind 或成熟组件库

### 8.4 验收标准

- 用户可以不打开 Swagger 完成工具注册和任务提交。
- 用户可以在控制台看到任务实时执行进度。
- 用户可以从失败任务直接定位失败节点和失败原因。
- 用户可以处理高风险工具审批。

---

## 9. 可观测性与调试能力

### 9.1 目标

让 ToolHub 不只是“记录数据”，而是能帮助定位 Agent 为什么选错工具、为什么失败、为什么被拒绝。

### 9.2 需要完成的内容

#### Trace 视图

围绕 `trace_id` 展示完整链路：

- task
- task_events
- llm_calls
- tool_calls
- sandbox_executions
- checkpoints

#### 指标统计

- 任务成功率
- 任务失败率
- 权限拒绝率
- 无工具命中率
- 平均耗时
- P95 耗时
- LLM token 用量
- 工具调用成功率
- Sandbox 超时率

#### 日志与错误分类

错误类型标准化：

- `NO_TOOL`
- `PERMISSION_DENIED`
- `TOOL_SCHEMA_INVALID`
- `TOOL_EXECUTION_FAILED`
- `SANDBOX_TIMEOUT`
- `LLM_JSON_PARSE_FAILED`
- `LLM_PROVIDER_FAILED`
- `CHECKPOINT_FAILED`

#### Replay / Resume

- 支持查看某次任务的状态快照。
- 支持从某个 checkpoint 恢复执行。
- 支持复制某次 tool_input 重跑工具调用。

### 9.3 验收标准

- 任意失败任务能在 1 分钟内定位失败节点。
- Dashboard 能按 trace_id 串起完整链路。
- 错误类型可统计、可筛选。
- 至少支持工具调用级别 replay。

---

## 10. 工程化与部署能力

### 10.1 目标

让项目从“本地能跑”变成“别人按文档能跑、服务能稳定启动、配置能管理”。

### 10.2 需要完成的内容

#### 配置管理

- `.env.example` 补全所有配置项。
- 区分 dev / test / prod 配置。
- 启动时校验关键配置。
- LLM mock 模式显式配置，不隐式依赖 placeholder key。

#### 数据库迁移

- 引入 Alembic。
- 将 `SCHEMA_SQL` 迁移为版本化 migration。
- 支持升级、回滚、初始化。

#### 服务启动

- 完善 `docker-compose.yml`：
  - postgres
  - redis
  - api
  - worker
  - dashboard
- 提供一键本地启动脚本。
- 提供健康检查。

#### API 质量

- 统一错误响应格式。
- 增加 pagination。
- 增加 request_id / trace_id middleware。
- 增加 API 文档示例。
- 增加 OpenAPI tag 和 description。

#### 安全默认值

- `.env` 保持不入库。
- Dashboard 不展示数据库连接串明文。
- HTTP 私网访问默认拒绝。
- Sandbox 网络默认关闭。
- CLI 默认只读 workspace。

### 10.3 验收标准

- 新机器按 README 可以启动完整环境。
- 数据库变更不再靠手写大段 SQL 覆盖。
- API / worker / dashboard 都有健康检查。
- 关键配置缺失时启动失败并给出明确原因。

---

## 11. 测试、评估与演示资产

### 11.1 目标

让项目质量可证明，演示可重复，面试讲解有抓手。

### 11.2 需要完成的内容

#### 单元测试

重点覆盖：

- ToolRouter
- PermissionEngine
- HTTPPolicy
- CLICommandPolicy
- ToolInputNormalizer
- ResultSummarizer fallback
- IntentService fallback
- schema validation

#### 集成测试

重点覆盖：

- 工具注册到调用全链路
- HTTP 工具调用
- CLI 工具沙箱执行
- Sandbox Python / Node 执行
- 权限拒绝
- 任务提交到 worker 完成
- task_events / tool_calls / llm_calls 落库

#### 安全测试

重点覆盖：

- HTTP SSRF
- HTTP redirect 到内网
- 危险请求头
- CLI shell 注入
- 路径穿越
- Sandbox 超时
- 过大响应体截断
- secret 脱敏

#### Eval

新增评估集：

- tool routing eval
- permission decision eval
- summarizer faithfulness eval
- malicious input eval

#### Demo 脚本

至少准备 5 条演示链路：

1. HTTP 工具成功调用
2. MCP 工具成功调用
3. CLI 只读工具成功调用
4. Sandbox 代码执行成功
5. 高风险工具被拒绝或进入审批

### 11.3 验收标准

- 测试数不少于 50 条。
- Demo 脚本可重复执行。
- 每条 Demo 都能在 Dashboard 看到完整链路。
- README 中有“演示路径”和“常见问题排查”。

---

## 12. 推荐优先级

### P0：先去掉玩具感

- 真实 MCP client
- 配置化 CLI policy
- 多步 Agent loop 雏形
- Console 支持任务提交和实时事件
- Demo 扩展到 5 条完整链路

### P1：做成可试用平台

- Schema-aware ToolRouter
- 审批流
- Secret 脱敏
- 工具健康检查定时任务
- SSE / WebSocket 任务事件流
- Alembic migration
- 集成测试和安全测试

### P2：做成更强的 Agent Infra 项目

- pgvector 语义召回
- LLM rerank
- Replay / Resume
- 多用户 / workspace
- 更完整的 RBAC
- 独立 React / Vue 控制台
- Prometheus / Grafana 指标

---

## 13. 建议的数据模型扩展

后续可以逐步增加以下表或字段。

### tools 扩展

- `owner`
- `workspace_id`
- `schema_hash`
- `metadata`
- `quality_score`
- `success_rate`
- `avg_duration_ms`

### tool_versions

用于保存工具版本历史：

- `tool_id`
- `version`
- `input_schema`
- `output_schema`
- `config`
- `created_at`

### approval_requests

用于高风险操作审批：

- `task_id`
- `run_id`
- `tool_id`
- `requested_action`
- `reason`
- `status`
- `requested_by`
- `approved_by`
- `created_at`
- `decided_at`

### policy_rules

用于替代纯代码权限判断：

- `scope`
- `effect`
- `condition`
- `priority`
- `enabled`

### artifacts

用于保存工具执行产物引用：

- `task_id`
- `run_id`
- `step`
- `artifact_type`
- `uri`
- `metadata`

---

## 14. README 与对外表达需要调整的重点

README 后续应该弱化“接口列表”，强化“为什么需要 ToolHub”。

推荐结构：

1. ToolHub 是什么
2. 为什么 Agent 需要 Harness
3. MCP / HTTP / CLI / Sandbox 如何统一接入
4. 权限与安全执行如何保证
5. 一条完整任务链路长什么样
6. 快速开始
7. Demo 场景
8. Dashboard 截图与说明
9. 架构图
10. 后续 Roadmap

对外一句话：

```text
ToolHub 是一个面向 CLI / IDE Agent 的工具运行时平台，用统一的 Harness 管理工具注册、工具路由、权限审批、安全执行、任务调度、checkpoint 和可观测性。
```

---

## 15. 最小可展示完成态

如果只追求短期展示效果，至少做到下面这些：

- 用户能在控制台注册工具。
- 用户能在控制台提交自然语言任务。
- 系统能选择工具并说明原因。
- 工具调用前能展示权限判断。
- 高风险工具能被拒绝或等待审批。
- 工具执行结果能被总结成 final_answer。
- Dashboard 能展示完整 trace。
- Demo 能覆盖 MCP、HTTP、CLI、Sandbox 四类工具。

达到这个状态后，ToolHub 就不再像一个“玩具 demo”，而更像一个缩小版 Agent Infra 产品。

---

## 16. 分步落地方案

本章节把前面的能力规划拆成可以逐步执行的开发步骤。每一步都应该做到“可以独立验收”，避免一次性铺太大。

### Step 1：整理当前基线与演示目标

目标：

把当前项目状态、已有能力、缺口和目标 Demo 固化下来，避免后续开发方向发散。

要做什么：

- 跑通现有测试，确认当前基线稳定。
- 跑通现有 demo_flow，记录当前能展示的链路。
- 整理当前支持的工具类型、运行模式、任务状态和审计表。
- 明确短期最小展示目标：
  - MCP 工具能真实接入
  - HTTP 工具能调用真实 API
  - CLI 工具能通过配置化 policy 执行只读命令
  - Sandbox 能执行 Python / Node 示例
  - Dashboard 能看到完整 trace

涉及文件：

- `README.md`
- `TOOLHUB.md`
- `scripts/demo_flow.ps1`
- `docs/toolhub_improvement_plan.md`

交付物：

- README 中新增“当前能力”和“短期目标”。
- demo_flow 能稳定跑通现有主链路。

验收标准：

- `pytest` 全部通过。
- 新人按 README 可以理解 ToolHub 当前能做什么、下一步要补什么。

完成记录：

- 2026-05-09 已完成当前基线确认。
- 单元测试结果：`13 passed`。
- 本地依赖状态：PostgreSQL 和 Redis 容器运行中。
- API 基线：`127.0.0.1:8000` 在当前 Windows 环境绑定失败，临时使用 `127.0.0.1:18000` 验证通过。
- Worker 基线：Celery worker 可以连接 Redis 并消费 `toolhub.run_agent_task`。
- Demo 基线：`scripts/demo_flow.ps1 -ApiBaseUrl http://127.0.0.1:18000` 可以提交 `git status` 后台任务，最终任务状态为 `SUCCESS`。
- 任务链路：实际产生 `TASK_SUBMITTED`、`TASK_STARTED`、`INSTRUCTIONS_LOADED`、`INTENT_UNDERSTOOD`、`TOOL_SELECTED`、`PERMISSION_ALLOWED`、`TOOL_EXECUTED`、`RESULT_SUMMARIZED`、`TASK_COMPLETED` 等事件。
- 已在 README 中新增“当前基线状态”和“短期完善目标”。

发现的问题：

- PowerShell 控制台中文输出存在编码显示问题。
- demo 脚本的轮询输出不够稳，任务实际成功后脚本可能先打印出不完整结果；后续应优化轮询和最终状态展示。
- 当前数据库中已存在多条历史 demo 工具，ToolRouter 会优先选择健康状态和得分更高的历史工具；Step 2 需要整理 demo seed，避免工具样例越来越乱。

---

### Step 2：把 Demo 工具补齐为四类真实样例

目标：

先让 ToolHub 看起来不是只会跑 `git status` 或 calculator，而是能覆盖 MCP / HTTP / CLI / Sandbox 四类工具。

要做什么：

- 准备 MCP 示例工具：
  - calculator
  - notes / memory / simple search 任选一个真实 MCP server
- 准备 HTTP 示例工具：
  - echo
  - public API 查询
  - mock business API
- 准备 CLI 示例工具：
  - git status
  - git diff
  - git log
- 准备 Sandbox 示例工具：
  - Python 代码执行
  - Node.js 代码执行
- 为每个工具补充：
  - name
  - description
  - tags
  - input_schema
  - output_schema
  - risk_level

涉及模块：

- `app/schemas/tool.py`
- `app/repositories/tool_repository.py`
- `app/services/tool_registry_service.py`
- `scripts/demo_flow.ps1`

交付物：

- 新增工具注册脚本或 demo seed 脚本。
- README 中列出四类工具示例。

验收标准：

- 一键脚本可以注册四类示例工具。
- `/api/tools/search` 能查到这些工具。
- Dashboard 工具健康页能展示这些工具。

完成记录：

- 2026-05-09 已新增 `scripts/seed_demo_tools.py`，用于注册或复用 canonical demo 工具。
- 当前 seed 覆盖 MCP / HTTP / CLI / Sandbox 四类工具：
  - `toolhub-demo-mcp-calculator`
  - `toolhub-demo-http-echo`
  - `toolhub-demo-http-public-api`
  - `toolhub-demo-cli-git-status`
  - `toolhub-demo-cli-git-diff`
  - `toolhub-demo-python-sandbox`
- 每个 demo 工具都补充了 `input_schema`、`output_schema`、`tags` 和 `risk_level`。
- 已更新 `scripts/demo_flow.ps1`，改为调用 `seed_demo_tools.py`，并在任务输入中明确使用 `toolhub-demo-cli-git-status`。
- 已新增 `tests/test_seed_demo_tools.py`，验证 demo seed 覆盖四类工具且定义可通过 `ToolRegisterRequest` 校验。
- README 已新增 demo seed 使用方式和 canonical demo 工具表。

当前边界：

- MCP 仍使用当前 adapter 的 calculator demo path，真实 MCP client 在 Step 3 完成。
- CLI 当前只注册底层 policy 已支持的 `git status` 和 `git diff`；`git log` 等更多命令放到 Step 4 配置化 CLI policy 后补齐。
- Sandbox 当前只注册 Python runner；Node.js runner 需要等 Sandbox Adapter 支持多语言后补齐。

---

### Step 3：实现真实 MCP Client 接入

目标：

把当前 `MCPToolAdapter` 从 calculator demo 升级为真实 MCP 调用能力。

要做什么：

- 增加 MCP client 封装。
- 支持连接 MCP server。
- 支持拉取 MCP server 的 tools list。
- 将 MCP tool 的 schema 同步到 ToolHub 的 tools 表。
- `MCPToolAdapter.call()` 根据 tool metadata 调用真实 MCP tool。
- 记录 MCP 调用的输入、输出、错误和耗时。
- MCP 连接失败时给出清晰错误。

涉及模块：

- `app/tools/adapters/mcp_adapter.py`
- `app/tools/dispatcher.py`
- `app/schemas/tool.py`
- `app/repositories/tool_repository.py`
- `app/repositories/tool_call_repository.py`

建议新增模块：

- `app/tools/mcp_client.py`
- `app/services/mcp_sync_service.py`

交付物：

- `MCPToolAdapter` 不再只支持 calculator。
- 新增 MCP sync API 或脚本。
- 至少接入一个真实 MCP server。

验收标准：

- 能从 MCP server 同步工具列表。
- 能通过 ToolHub 调用 MCP tool。
- tool_calls 中能看到 MCP 调用记录。
- MCP 调用失败时任务状态和事件链路正确。

完成记录：

- 2026-05-09 已引入官方 Python MCP SDK：`mcp==1.27.1`。
- 已新增 `app/tools/mcp_client.py`，封装 MCP client，支持：
  - `mock`
  - `stdio`
  - `sse`
  - `streamable-http`
- 已更新 `app/tools/adapters/mcp_adapter.py`：
  - 不再只判断 calculator 工具名
  - 使用 `tool.mcp_url`、`tool.transport` 和 `tool.endpoint` 调用远端 MCP tool
  - 支持通过 `tool_input.arguments` 或普通 tool_input 字段传递 MCP arguments
- 已新增 `app/services/mcp_sync_service.py`：
  - 可以从 MCP server 拉取 tools list
  - 可以将远端 MCP tool 注册进 ToolHub Tool Registry
  - 同步后的 `endpoint` 保存远端 MCP tool name
- 已新增 `scripts/sync_mcp_tools.py`：
  - 支持从命令行同步 MCP tools
  - 支持 `--mcp-url`、`--transport`、`--name-prefix`、`--tag`、`--risk-level`
- 已更新 `scripts/seed_demo_tools.py`：
  - canonical MCP demo 工具现在使用 `endpoint=calculator`
- 已新增 `tests/test_mcp_client_adapter_sync.py`：
  - 覆盖 mock MCP call
  - 覆盖 MCP adapter 参数传递
  - 覆盖 MCP sync service 注册远端工具
- README 已新增 MCP 工具同步说明。

当前边界：

- 已具备真实 MCP SDK client 封装，但本地自动化测试仍使用 `mock://calculator`，避免测试依赖外部 MCP server。
- `stdio://` URL 约定为：命令放在 host 位置，参数通过 `args` 或 `arg` query 重复传入，例如 `stdio://python?args=-m&args=my_mcp_server`。
- MCP server 的鉴权 header、OAuth 等高级能力暂未接入，后续可放到权限/Secret 管理阶段。

---

### Step 4：把 CLI Policy 从硬编码改成配置化

目标：

让 CLI 工具从“代码里写死几个命令”变成“可配置、可审计、可扩展”的命令策略。

要做什么：

- 设计 CLI policy 配置格式。
- 支持从 YAML / JSON 文件加载 CLI rules。
- 每条 rule 包含：
  - `rule_id`
  - `description`
  - `effect`
  - `risk_level`
  - `image`
  - `argv_template`
  - `params`
  - `workdir`
  - `readonly_workspace`
  - `network_disabled`
  - `timeout_seconds`
- 保留当前默认安全规则作为 fallback。
- 给配置加载增加单元测试。
- 错误提示中返回命中的 rule_id 或拒绝原因。

涉及模块：

- `app/security/cli_policy.py`
- `app/tools/adapters/cli_adapter.py`
- `app/common/config.py`

建议新增文件：

- `config/cli_policy.yaml`
- `tests/test_cli_policy_config.py`

交付物：

- CLI rules 可通过配置扩展。
- git status / git diff / git log 均通过配置执行。

验收标准：

- 未配置危险命令时无法执行。
- 传入未知参数会被拒绝。
- 路径穿越、shell 注入仍被拦截。
- CLI 工具仍默认通过 DockerSandbox 执行。

完成记录：

- 2026-05-09 已新增 `config/cli_policy.json`，将 CLI 规则迁出硬编码策略。
- 已新增配置项 `CLI_POLICY_PATH`，默认值为 `config/cli_policy.json`。
- 已更新 `app/security/cli_policy.py`：
  - 启动时先加载内置只读规则作为兜底
  - 如果配置文件存在，则读取 JSON rules 并覆盖/扩展内置规则
  - 支持配置 rule 的 `params`、`workdir`、`mount_workspace`、`readonly_workspace`、`network_disabled`、`timeout_seconds` 等字段
  - 继续只接受 `rule_id` 和结构化 `args`，不接受自由 shell 拼接
- 当前配置化规则包括：
  - `cli://git/status-short`
  - `cli://git/diff`
  - `cli://git/log-oneline`
- 已更新 `scripts/seed_demo_tools.py`，新增 `toolhub-demo-cli-git-log`。
- 已新增 `tests/test_cli_policy_config.py`：
  - 覆盖从配置加载 `git log`
  - 覆盖配置缺失时使用默认规则
  - 覆盖自定义 JSON rule
  - 覆盖无效配置拒绝加载
- README 已新增 CLI Policy 配置说明。

当前边界：

- 本阶段采用 JSON 配置，避免引入 YAML 解析依赖；后续如果需要 YAML，可以在不改变规则模型的情况下增加解析入口。
- 配置文件会覆盖同名内置 rule，因此改配置时需要通过测试确认 argv 模板仍是安全只读命令。

---

### Step 5：升级 ToolRouter 为 schema-aware 路由

目标：

让路由不只看关键词和工具类型，还能判断 tool_input 是否满足工具 schema。

要做什么：

- 在路由候选中加入 input_schema 匹配检查。
- 对 LLM 生成的 tool_input 做 schema validation。
- 如果缺少必要参数，返回缺失字段说明。
- 如果 schema 不匹配，不执行工具。
- 路由结果中增加：
  - candidate score detail
  - schema_match
  - missing_fields
  - rejection_reason

涉及模块：

- `app/services/tool_router_service.py`
- `app/harness/tool_input_normalizer.py`
- `app/schemas/routing.py`
- `app/schemas/tool.py`

建议新增模块：

- `app/services/schema_validation_service.py`

交付物：

- ToolRouter 返回更可解释的候选结果。
- schema 不匹配时任务进入 `NO_TOOL` 或 `FAILED_VALIDATION`，不强行执行。

验收标准：

- 工具参数缺失时不会调用工具。
- 路由响应能说明为什么选中或拒绝某个工具。
- 至少补充 10 条路由单元测试。

完成记录：

- 2026-05-09 已新增 `app/services/schema_validation_service.py`。
- 当前实现轻量 JSON Schema 子集校验，支持：
  - `type`
  - `required`
  - `properties`
  - `additionalProperties`
  - `const`
  - `enum`
  - `minimum`
  - `maximum`
- 已扩展 `ToolRouteRequest`：
  - 新增 `tool_input`
- 已扩展 `ToolRouteResult`：
  - 新增 `candidate_details`
  - 新增 `schema_match`
  - 新增 `missing_fields`
  - 新增 `rejection_reason`
- 已更新 `ToolRouterService`：
  - 路由时对每个候选工具执行 schema 校验
  - schema 匹配的候选优先于 schema 不匹配的候选
  - 所有候选都不匹配时返回 `selected_tool=None`，并说明缺失字段或错误原因
- 已更新调用点：
  - `/api/router/select`
  - `HarnessPlanService`
  - `AgentHarnessWorkflow`
- 已新增 `tests/test_schema_validation_service.py`。
- 已扩展 `tests/test_tool_router_service.py`，覆盖：
  - 缺少必填字段时不选择工具
  - schema 匹配候选优先于更高分但 schema 不匹配的候选
- README 已补充 schema-aware 路由说明。

当前边界：

- 当前校验器只覆盖项目已使用的 JSON Schema 子集，不是完整 JSON Schema 实现。
- 路由阶段的校验用于提前拒绝明显不匹配的工具；后续执行前仍建议引入更严格的 schema validation。
- 某些工具输入需要经过 `ToolInputNormalizer` 才能补齐字段，后续可以把 normalizer 前置到路由前，或为 Router 提供 normalized preview。

---

### Step 6：实现多步 Agent Harness 雏形

目标：

把当前单步链路升级为可以连续调用多个工具的 Agent loop。

要做什么：

- 在 HarnessState 中增加：
  - `plan`
  - `steps`
  - `current_step_index`
  - `observations`
  - `max_steps`
  - `stop_reason`
- 增加 `make_plan` 节点。
- 增加 `observe_result` 节点。
- 增加 `decide_next_step` 节点。
- 支持最多 N 步执行，默认可以先设为 3。
- 每一步工具调用都写入 task_events。
- summary 引用所有 observations。

涉及模块：

- `app/harness/workflow.py`
- `app/llm/intent_service.py`
- `app/llm/result_summarizer_service.py`
- `app/repositories/task_event_repository.py`

交付物：

- 一个任务可以执行多个工具步骤。
- task result 中保存 steps 和 observations。

验收标准：

- Demo 能完成“先查 git status，再查 git diff，再总结”的多步任务。
- 每一步都有单独的事件、工具调用和 observation。
- 超过 max_steps 后能停止并说明原因。

完成记录：

- 2026-05-09 已新增 `app/harness/step_planner.py`。
- 当前 `HarnessStepPlanner` 先使用确定性规则生成多步计划，避免在雏形阶段引入新的 LLM 规划不确定性。
- 已支持的多步 demo 规则：
  - 输入包含 `git status` 时生成 `cli://git/status-short` 步骤
  - 输入包含 `git diff` / `变更` / `差异` 时生成 `cli://git/diff` 步骤
  - 输入包含 `git log` / `提交历史` 时生成 `cli://git/log-oneline` 步骤
- 已更新 `AgentHarnessWorkflow`：
  - 新增 `make_plan`
  - 新增 `observe_result`
  - 新增 `decide_next_step`
  - 使用 LangGraph conditional edge 在还有后续步骤时回到 `select_tool`
  - 状态中新增 `plan`、`steps`、`current_step_index`、`max_steps`、`observations`、`stop_reason`
- 已更新 `task_worker`，最终 `tasks.result` 会包含：
  - `plan`
  - `steps`
  - `observations`
  - `stop_reason`
- 已新增 `tests/test_step_planner.py`，覆盖：
  - `git status + diff` 多步计划
  - `git log` 单步计划
  - 非 git 任务回退到 IntentService 的 `tool_input`
- README 已补充多步任务示例。

验证结果：

- `pytest`：`30 passed`。
- 已通过真实后台任务验证：提交 `请查看 git status 和 diff` 后，任务最终 `SUCCESS`，`result.steps` 为 2 条，`result.observations` 为 2 条，`stop_reason=所有计划步骤已完成。`

补充完成记录：

- 2026-05-09 已将 `HarnessStepPlanner` 从纯确定性规则升级为 LLM 优先规划：
  - `make_plan` 节点会把用户输入、intent、run_mode、max_steps 和当前可用工具摘要交给 LLM。
  - LLM 只负责生成 `steps` 建议，不执行工具、不决定权限。
  - 系统会清洗 LLM 输出，归一化 `intent`、`suggested_tool_type`、Sandbox `code` 字段和 CLI `rule_id + args`。
  - 当 LLM 调用失败、JSON 解析失败或步骤不可用时，退回原有确定性规则。
  - `plan` 中新增 `planner`、`fallback_used`、`warnings`、`raw_response`，便于 Dashboard 和面试讲解展示。
- 已补齐 `PLAN_ONLY`：
  - `PLAN_ONLY` 在 `make_plan` 后直接进入 summary，不会路由或执行工具。
  - 最终状态为 `PLANNED`，summary 会明确说明“只生成计划，不执行工具”。
- 测试已扩展：
  - LLM planner 可生成多步计划。
  - LLM 输出不可用时可回退到确定性规则。
  - ResultSummarizer 支持 `PLANNED`。
- 最新验证结果：
  - `pytest`：`37 passed`。
  - `PLAN_ONLY` 真实 LangGraph 链路验证通过：最终 `PLANNED`，planner=`llm-v1`，生成 2 个步骤，未执行工具。
  - `SAFE_EXECUTE` 真实多步 git 链路验证通过：最终 `SUCCESS`，planner=`llm-v1`，2 个步骤、2 条 observation。

当前边界：

- 当前 planner 已支持 LLM 优先规划，但仍是“LLM 建议 + 系统校验 + 规则兜底”的工程化版本，不允许 LLM 绕过 router、schema validation、permission 和 sandbox。
- 多步循环目前只在每一步 `SUCCESS` 时继续；遇到 `FAILED`、`DENIED`、`NO_TOOL` 会停止并进入总结。
- `max_steps` 默认 3，后续可以暴露为任务运行配置。
- 当前 observation 会保存每步 route、permission、tool_input、tool_result，数据量较大；后续可增加压缩或 artifact 引用。
- 还没有实现失败后由 LLM 根据 observation 修正参数并重试的 ReAct 风格循环。

---

### Step 7：补齐权限策略与审批流

目标：

把权限系统从简单 allow / deny 升级为 `ALLOW / ASK / DENY`，支持高风险操作审批。

要做什么：

- 扩展 PermissionDecision，支持 `ASK`。
- 增加 `WAITING_APPROVAL` 任务状态。
- 新增 approval request 数据模型。
- 高风险工具在 SAFE_EXECUTE 下进入审批或拒绝。
- 增加审批 API：
  - 创建审批请求
  - 查询待审批任务
  - 通过审批
  - 拒绝审批
- 审批通过后任务可以继续执行。
- 审批操作写入 task_events。

涉及模块：

- `app/security/permission_engine.py`
- `app/schemas/permission.py`
- `app/schemas/task.py`
- `app/repositories/db.py`
- `app/services/task_service.py`
- `app/workers/task_worker.py`

建议新增模块：

- `app/api/approvals.py`
- `app/services/approval_service.py`
- `app/repositories/approval_repository.py`

交付物：

- 权限判断支持 `ASK`。
- 高风险工具可以进入审批状态。

验收标准：

- SAFE_EXECUTE 下 HIGH 工具不会直接执行。
- 审批通过后任务能继续执行。
- 审批拒绝后任务进入 DENIED。
- Dashboard 或 API 能看到审批原因和审批人。

完成记录：

- 2026-05-09 已将权限决策扩展为可用的 `ALLOW / ASK / DENY`。
- 已更新 `PermissionEngine`：
  - `PLAN_ONLY` 仍然拒绝执行
  - `SAFE_EXECUTE + HIGH` 返回 `ASK`
  - `FULL_EXECUTE + HIGH` 允许继续执行
- 已新增 `approval_requests` 表，字段包括：
  - `task_id`
  - `run_id`
  - `trace_id`
  - `tool_id`
  - `requested_action`
  - `reason`
  - `status`
  - `requested_by`
  - `decided_by`
  - `decision_reason`
  - `created_at`
  - `decided_at`
- 已新增审批相关模块：
  - `app/schemas/approval.py`
  - `app/repositories/approval_repository.py`
  - `app/services/approval_service.py`
  - `app/api/approvals.py`
- 已新增审批 API：
  - `GET /api/approvals/pending`
  - `POST /api/approvals/{approval_id}/approve`
  - `POST /api/approvals/{approval_id}/reject`
- 已更新 `AgentHarnessWorkflow`：
  - 权限决策为 `ASK` 时创建或复用待审批请求
  - 任务进入 `WAITING_APPROVAL`
  - 不执行工具调用
  - 写入 `APPROVAL_REQUESTED`、`TASK_WAITING_APPROVAL` 等事件
- 已更新 `ApprovalService.approve`：
  - 审批通过后任务切换到 `FULL_EXECUTE`
  - 任务状态回到 `QUEUED`
  - 自动重新投递 Celery worker
- 已更新 `ApprovalService.reject`：
  - 审批拒绝后任务进入 `DENIED`
  - 写入审批拒绝事件
- 已更新 ResultSummarizer：
  - 支持 `WAITING_APPROVAL` summary_type
  - 等待审批时给出下一步审批建议
- 已新增测试：
  - `tests/test_permission_engine.py`
  - `tests/test_result_summarizer_service.py` 中新增等待审批 fallback 测试

验证结果：

- `pytest`：`34 passed`。
- 已通过真实后台任务验证：
  - 提交 `请运行 Python 代码 print(sum(range(10)))`
  - `SAFE_EXECUTE` 下任务进入 `WAITING_APPROVAL`
  - `GET /api/approvals/pending` 可以查到审批请求
  - 调用 approve API 后任务切换到 `FULL_EXECUTE` 并重新入队
  - 最终任务 `SUCCESS`，沙箱 stdout 为 `45`

当前边界：

- 审批通过当前采用“本次任务切换到 FULL_EXECUTE 并重新入队”的最小闭环方案。
- 暂未实现审批过期、审批范围、审批一次后复用、审批人权限校验。
- 当前审批 API 是本地开发形态，没有接入登录用户和 RBAC。

---

### Step 8：增强 Dashboard 为 Console

目标：

让用户不依赖 Swagger，也能完成工具管理、任务提交、链路查看和审批处理。

要做什么：

- 增加工具管理页：
  - 工具列表
  - 工具详情
  - 注册工具
  - 启用 / 禁用工具
  - 健康检查
- 增加任务提交页：
  - 输入 user_input
  - 选择 run_mode
  - 提交任务
  - 查看 task_id
- 增加任务详情页：
  - timeline
  - final_answer
  - route reason
  - permission decision
  - tool_calls
  - llm_calls
  - sandbox logs
- 增加审批页：
  - 待审批列表
  - 审批详情
  - 通过 / 拒绝

涉及模块：

- `dashboard/streamlit_app.py`
- `app/api/tasks.py`
- `app/api/tools.py`
- `app/api/approvals.py`

交付物：

- Streamlit Dashboard 从观测页变成基础 Console。

验收标准：

- 可以在 Console 中注册工具。
- 可以在 Console 中提交任务。
- 可以在 Console 中查看完整 trace。
- 可以在 Console 中处理审批。

---

### Step 9：增加实时事件流

目标：

让任务执行过程可以实时观察，而不是提交后反复刷新。

要做什么：

- 增加任务事件流 API。
- 短期可以用轮询。
- 更进一步可以用 SSE：
  - `GET /api/tasks/{task_id}/events/stream`
- worker 每写入 task_events 后前端能看到更新。
- Console 任务详情页自动刷新 timeline。

涉及模块：

- `app/api/tasks.py`
- `app/services/task_service.py`
- `dashboard/streamlit_app.py`

交付物：

- 任务执行过程中能看到实时事件变化。

验收标准：

- 提交任务后，不刷新页面也能看到事件逐步出现。
- 任务完成后状态自动更新为 SUCCESS / FAILED / DENIED / NO_TOOL。

---

### Step 10：强化可观测性和错误分类

目标：

让失败任务可以被快速定位，而不是只能看一堆原始 JSON。

要做什么：

- 定义标准错误类型：
  - `NO_TOOL`
  - `PERMISSION_DENIED`
  - `TOOL_SCHEMA_INVALID`
  - `TOOL_EXECUTION_FAILED`
  - `SANDBOX_TIMEOUT`
  - `LLM_JSON_PARSE_FAILED`
  - `LLM_PROVIDER_FAILED`
  - `CHECKPOINT_FAILED`
- task_events 中记录 error_type。
- tool_calls 中记录 error_type。
- Dashboard 支持按 error_type 筛选。
- Overview 增加：
  - P95 duration
  - no-tool rate
  - permission denied rate
  - sandbox timeout rate
  - LLM failed rate

涉及模块：

- `app/common/exceptions.py`
- `app/harness/workflow.py`
- `app/tools/dispatcher.py`
- `app/infra/docker_sandbox.py`
- `dashboard/streamlit_app.py`

交付物：

- 统一错误分类。
- Dashboard 可以按失败类型定位问题。

验收标准：

- 任意失败任务能看到明确失败节点、失败类型和下一步建议。
- Overview 能展示关键质量指标。

---

### Step 11：引入数据库迁移与启动编排

目标：

让项目从“本地脚本初始化”升级成更接近真实工程的启动方式。

要做什么：

- 引入 Alembic。
- 将当前 `SCHEMA_SQL` 拆成 migration。
- 保留 `scripts/init_db.py`，但改为调用 migration 或给出清晰职责。
- 完善 docker-compose：
  - postgres
  - redis
  - api
  - worker
  - dashboard
- 增加服务健康检查。
- `.env.example` 补全所有配置。
- LLM mock 模式改为显式配置，例如 `LLM_MOCK_ENABLED=true`。

涉及模块：

- `app/repositories/db.py`
- `scripts/init_db.py`
- `docker-compose.yml`
- `.env.example`
- `pyproject.toml`

建议新增目录：

- `migrations/`
- `alembic.ini`

交付物：

- 数据库结构版本化。
- 本地环境可以一键启动。

验收标准：

- 新机器按 README 能启动完整服务。
- 数据库变更有 migration 记录。
- API / worker / dashboard 都能健康检查。

完成记录：

- 2026-05-09 已引入 Alembic：`alembic==1.18.4`。
- 已新增：
  - `alembic.ini`
  - `migrations/env.py`
  - `migrations/script.py.mako`
  - `migrations/versions/20260509_0001_initial_schema.py`
- 已将原先由 `SCHEMA_SQL` 维护的初始表结构迁入 Alembic 初始 migration。
- 已更新 `app/repositories/db.py`：
  - `init_db()` 现在会先确保 database 存在，再执行 `alembic upgrade head`
  - 数据库 schema 不再以大段内联 SQL 作为主路径
- 已新增显式配置：
  - `LLM_MOCK_ENABLED`
  - `validate_settings()`
- 已更新 LLM mock 判断：
  - mock 模式由 `LLM_MOCK_ENABLED=true/false` 控制
  - 不再依赖 placeholder API key 隐式判断
- 已完善 `docker-compose.yml`：
  - `postgres`
  - `redis`
  - `api`
  - `worker`
  - `dashboard`
- 已新增：
  - `Dockerfile`
  - `.dockerignore`
- 已新增健康检查：
  - `/health/live`
  - `/health/ready`
  - Redis healthcheck
  - API healthcheck
  - worker healthcheck
  - dashboard healthcheck
- 已补充 `tests/test_config.py`，覆盖显式 LLM mock 配置和关闭 mock 时的配置校验。

验证结果：

- `scripts/init_db.py` 已成功执行 migration。
- 当前数据库 `alembic_version=20260509_0001`。
- `docker compose config --quiet` 通过。
- `pytest`：`40 passed`。

当前边界：

- 已尝试 `docker compose build api`，但当前环境访问 Docker Hub 拉取 `python:3.12-slim` 超时，未完成镜像构建验证。
- compose 编排和 Dockerfile 已落地，后续在网络可访问 Docker Hub 的环境下需要补一次完整 `docker compose up --build` 验证。

---

### Step 12：补齐测试与评估集

目标：

让项目质量可以被证明，面试时可以讲测试覆盖和安全边界。

要做什么：

- 单元测试补齐：
  - MCP adapter
  - CLI policy config
  - schema validation
  - PermissionEngine ASK
  - ApprovalService
  - multi-step workflow decision
- 集成测试补齐：
  - 工具注册 -> 路由 -> 权限 -> 执行 -> 总结
  - 权限拒绝链路
  - 审批通过链路
  - Sandbox 超时链路
- 安全测试补齐：
  - SSRF
  - redirect SSRF
  - shell injection
  - path traversal
  - secret redaction
- 新增 eval：
  - `evals/tool_routing_cases.jsonl`
  - `evals/permission_cases.jsonl`
  - `scripts/run_evals.py`

涉及模块：

- `tests/`
- `evals/`
- `scripts/`

交付物：

- 测试数提升到 50 条以上。
- 有可运行的路由评估脚本。

验收标准：

- `pytest` 全部通过。
- `run_evals.py` 输出 routing accuracy / no-tool precision。
- README 中展示测试和评估结果。

---

### Step 13：整理最终 Demo 与简历表达

目标：

把工程能力包装成清晰、可信、可演示的项目故事。

要做什么：

- 准备 5 条稳定 Demo：
  1. HTTP 工具成功调用
  2. MCP 工具成功调用
  3. CLI 只读工具成功调用
  4. Sandbox 代码执行成功
  5. 高风险工具被拒绝或审批
- 每条 Demo 都要能在 Console 看到完整 trace。
- README 增加 Demo 章节。
- README 增加架构图。
- README 增加“为什么不是玩具 demo”的说明。
- 整理简历描述，避免夸成生产级系统。

涉及文件：

- `README.md`
- `docs/toolhub_improvement_plan.md`
- `docs/architecture.md`
- `docs/resume_and_interview.md`
- `scripts/final_demo.ps1`

交付物：

- 可重复执行的 Demo。
- 简历项目描述。
- 面试讲解提纲。

验收标准：

- 5 条 Demo 均能稳定跑通。
- 面试时能讲清楚：
  - 为什么需要 Agent Harness
  - LLM 负责什么、不负责什么
  - 工具路由如何做
  - 权限如何治理
  - CLI / Sandbox 如何隔离
  - trace 如何帮助排障

完成记录：

- 2026-05-10 已完成最终展示材料收口。
- 新增 `scripts/final_demo.ps1`，覆盖路由解释、HTTP 调用、MCP 调用、tool_call replay、高风险 Sandbox 权限预检和多步后台任务。
- 新增 `docs/architecture.md`，用架构图和执行链路说明 ToolHub 的组件边界。
- 新增 `docs/resume_and_interview.md`，整理简历写法、推荐讲法、不能夸大的边界和常见追问。
- README 已更新为最终演示入口，避免继续使用早期单链路 demo 作为主要展示路径。

---

### Step 14：去 Demo 化与最终状态收口

目标：

把 ToolHub 从“能演示的 MVP”继续收口成“工程边界清楚、没有明显玩具感、可以作为实习项目认真讲解”的 Agent Infra 项目。

这里的重点不是继续堆功能，而是把当前仍像 demo 的部分隔离、替换或产品化。最终项目可以保留 examples 和 mock fallback，但主链路不能依赖 demo 工具证明价值。

#### 14.1 当前还不是最终状态的部分

##### 数据库变更管理

当前状态：

- 数据库表结构仍主要维护在 `app/repositories/db.py` 的 `SCHEMA_SQL` 中。
- 新增表和字段依赖初始化脚本，而不是版本化迁移。

最终状态：

- 引入 Alembic。
- 将当前所有表结构整理为初始 migration。
- 后续表结构变更都通过 migration 管理。
- `scripts/init_db.py` 的职责改为“执行迁移 / 初始化开发库”，不再维护大段 SQL。

为什么重要：

面试官看到 migration，会认为你理解真实后端系统的演进方式；如果一直是手写大段 SQL 初始化，容易被认为是课程 demo。

##### Mock 与 Demo 资产隔离

当前状态：

- `seed_demo_tools.py`、mock MCP calculator、mock HTTP echo、mock LLM response 都在主线叙事中占比较高。
- 这些能力对本地开发和测试有价值，但如果作为主卖点，会显得项目依赖 demo 场景。

最终状态：

- mock / demo 工具统一放到 `examples/`、`devtools/` 或明确的 demo 章节。
- README 主线强调 ToolHub 的 runtime / harness / governance 能力，而不是 calculator / echo。
- 至少准备 2-3 个真实工具接入案例：
  - 一个真实 MCP server
  - 一个真实 HTTPS API
  - 一个真实 CLI 只读工作流
- mock LLM 只作为本地无 key fallback，不作为核心能力描述。

##### 工具接入平台化

当前状态：

- MCP client 已具备真实 SDK 接入能力。
- CLI policy 已配置化，但仍是单个 JSON 文件。
- HTTP 工具还没有 OpenAPI import。
- Sandbox 主要覆盖 Python，artifact 收集、Node.js、文件挂载策略还不完整。
- 工具没有 owner、workspace、版本历史、质量指标。

最终状态：

- HTTP 支持 OpenAPI / JSON Schema 导入。
- CLI policy 从单文件升级为策略包或内置 rule pack + 本地覆盖。
- Sandbox 支持 Python / Node.js、执行产物收集、只读挂载策略和网络开关。
- 工具元数据支持 owner、workspace、version history、success_rate、avg_duration_ms、quality_score。

##### Agent Loop 完整性

当前状态：

- 已有 LLM-first planner、多步执行、observations 和 stop_reason。
- 但失败后不会基于 observation 修正参数重试。
- 没有 retry policy、resume、replay、取消任务和继续上一轮任务。
- `max_steps` 仍是默认固定值。

最终状态：

- 支持有限重试。
- 支持 LLM 根据 observation 修正下一步参数，但仍经过 router / schema / permission。
- 支持任务取消。
- 支持从 checkpoint 或 tool_call replay。
- `max_steps`、retry 次数、超时时间可以按任务或 workspace 配置。

推荐表述：

```text
当前是 LLM-planned multi-step harness，不应包装成完整 ReAct Agent Runtime。
下一步目标是 observation-driven replanning with bounded retries。
```

##### 工具路由质量

当前状态：

- ToolRouter 已经 schema-aware。
- 但主要仍是规则打分，没有 embedding 召回、LLM rerank 和系统化 eval。

最终状态：

- 增加 top-k candidates。
- 增加 pgvector / embedding 语义召回。
- 增加 LLM rerank，但最终选择仍由系统校验。
- 引入工具历史成功率、健康状态、平均耗时作为加权因子。
- 建立 routing eval，输出 accuracy、top-k recall、no-tool precision。

##### 权限和审计身份

当前状态：

- `ALLOW / ASK / DENY` 和审批流已经可用。
- 但没有 user / workspace / RBAC。
- 审批没有过期、审批范围和审批人权限校验。

最终状态：

- 引入 user_id / workspace_id。
- Policy 支持 user、workspace、tool、action、risk_level、run_mode 等维度。
- 审批支持过期时间、审批范围、本次执行 / 一段时间内复用。
- task_events / approval_requests 记录真实操作者身份。

##### Secret 管理与脱敏

当前状态：

- 还没有完整 secret reference 机制。
- tool_calls、llm_calls、task_events 的敏感字段脱敏不完整。

最终状态：

- 工具配置中只保存 `env:XXX`、`secret:xxx` 这类引用。
- 不保存明文 token。
- API、日志、Dashboard、事件 payload 自动脱敏。
- 增加 secret redaction 安全测试。

##### 部署与配置

当前状态：

- 本地可以运行 PostgreSQL / Redis。
- API / worker / dashboard 仍需要分别启动。
- LLM mock 依赖 placeholder key 判断，不够显式。

最终状态：

- docker compose 编排 postgres、redis、api、worker、dashboard。
- `.env.example` 覆盖全部配置。
- 增加 `LLM_MOCK_ENABLED=true/false`。
- 启动时校验关键配置，缺失时给出明确错误。
- API / worker / dashboard 都有 healthcheck。

#### 14.2 最终状态直达落地顺序

当前策略调整为：不再先做 Dashboard、观测页、测试数量和 demo 包装，而是直接把主系统能力做到接近最终状态。等核心架构稳定后，再补数据观测、测试评估和展示材料。

这个顺序的原因：

- Dashboard 和观测依赖底层数据模型稳定，先做容易返工。
- 测试和 eval 应该覆盖最终接口与最终行为，过早补齐会在大重构时反复修改。
- demo 脚本应该服务最终项目故事，而不是牵着架构走。

P0：核心工程底座一次到位

1. 引入 Alembic migration，替换 `SCHEMA_SQL` 主导的建表方式。
2. 将现有表结构整理成初始 migration。
3. 后续所有 schema 变更都通过 migration 追加。
4. 完整 docker compose 编排 postgres、redis、api、worker、dashboard。
5. 补齐 `.env.example`，增加显式 `LLM_MOCK_ENABLED`。
6. 启动时做关键配置校验。
7. API / worker / dashboard 都提供 healthcheck。

验收标准：

- 新机器可以通过 README 和 docker compose 启动完整系统。
- 数据库结构有版本记录，不再依赖手写大段初始化 SQL 作为主路径。
- mock LLM 是否启用由明确配置决定，而不是依赖 placeholder key。

P1：Secret、身份和策略模型一次成型

1. 增加 secret reference 模型，例如 `env:XXX_API_KEY`、`secret:xxx`。
2. 工具注册和工具配置不保存明文 token。
3. task_events、tool_calls、llm_calls、approval_requests payload 自动脱敏。
4. 引入 user_id / workspace_id。
5. Policy 支持 user、workspace、tool、action、risk_level、run_mode、command rule、HTTP domain、network、filesystem mount 等维度。
6. 审批支持过期时间、审批范围、本次执行 / 短期复用。
7. approval_requests 记录真实审批人和审批原因。

验收标准：

- 日志、事件、API 响应中不会泄露 token。
- 权限和审批不再只是本地开发形态，而有用户、工作区和范围概念。

P2：工具平台最终形态

1. mock / demo 工具移入 `examples/` 或 `devtools/`，主链路不再依赖 demo 证明能力。
2. HTTP 支持 OpenAPI / JSON Schema 导入。
3. CLI policy 从单个 JSON 文件升级为 rule pack + local override。
4. Sandbox 支持 Python / Node.js。
5. Sandbox 支持 artifact 收集、网络开关、只读挂载和资源限制。
6. 工具元数据增加 owner、workspace、版本历史、schema_hash、quality_score。
7. 记录 success_rate、avg_duration_ms、最近失败原因等工具质量指标。

验收标准：

- 可以接入真实 MCP server、真实 HTTPS API、真实只读 CLI workflow。
- 工具注册、版本、策略、质量指标形成平台化闭环。

完成记录：

- 2026-05-09 已完成 P2 工具平台化骨架。
- 已新增 migration：`migrations/versions/20260509_0003_tool_versions.py`。
- 已新增 `tool_versions` 表：
  - `tool_id`
  - `version`
  - `input_schema`
  - `output_schema`
  - `config`
  - `metadata`
- 工具注册时会自动写入版本快照。
- `tool_calls` 写入后会刷新工具质量指标：
  - `success_rate`
  - `avg_duration_ms`
  - `quality_score`
- 已新增 OpenAPI 导入能力：
  - `app/services/openapi_import_service.py`
  - `app/api/openapi_import.py`
  - `scripts/import_openapi_tools.py`
  - `POST /api/openapi/import`
- OpenAPI operation 会转换为 HTTP 工具，并生成 method / path_params / query params / JSON body schema。
- CLI policy 已从单文件升级为 rule pack + local override：
  - `CLI_POLICY_DIR=config/cli_policies`
  - `CLI_POLICY_PATH=config/cli_policy.json`
  - 新增 `config/cli_policies/core-git.json`
- Sandbox Adapter 已支持：
  - Python
  - Node.js
  - artifact path 元数据
- DockerSandbox / sandbox_executions / tool_calls 已支持 artifact 引用字段。
- demo 资产已增加 `examples/devtools` 入口，用于把 demo 辅助资产和主线能力叙事拆开。
- 已新增测试：
  - `tests/test_openapi_import_service.py`
  - `tests/test_tool_versions_and_quality.py`
  - `tests/test_sandbox_adapter.py`
  - CLI rule pack 目录加载测试

验证结果：

- 当前数据库 `alembic_version=20260509_0003`。
- `docker compose config --quiet` 通过。
- `pytest`：`48 passed`。

P3：Agent Harness 最终主链路

1. 保持 LLM planner 只给计划建议，系统继续负责 schema、router、permission、sandbox。
2. 增加 bounded retry。
3. 增加 observation-driven replanning。
4. 工具失败后允许 LLM 根据 observation 修正 tool_input，但每次修正后仍重新经过 schema 和权限。
5. 增加 task cancel。
6. 增加 replay / resume。
7. `max_steps`、retry 次数、timeout 支持任务级或 workspace 级配置。
8. PLAN_ONLY、SAFE_EXECUTE、FULL_EXECUTE 的行为和状态保持清晰。

验收标准：

- 一个任务可以规划、执行、失败、修正、重试、停止或继续。
- 每次自动修正都有边界，不会让 LLM 绕过权限和沙箱。

完成记录：

- 2026-05-09 已完成 P3 Agent Harness 最终主链路骨架。
- 新增 migration：`migrations/versions/20260509_0004_runtime_controls.py`。
- `tasks` 已新增任务级运行控制字段：
  - `run_config`
  - `cancel_requested`
  - `cancel_reason`
  - `cancelled_at`
- `tool_calls` 已新增 replay 追踪字段：
  - `replay_of_tool_call_id`
  - `replay_reason`
- `POST /api/tasks` 已支持任务级 `run_config`：
  - `max_steps`
  - `max_retries`
  - `timeout_seconds`
- 新增 `POST /api/tasks/{task_id}/cancel`，支持外部请求取消任务；运行中的 Harness 会在节点边界停止，未启动任务不会继续执行。
- Harness 失败分支已从“失败即结束”升级为 bounded retry：
  - 仅对工具执行失败做有限重试。
  - 每个 step 记录 `retry_count`。
  - 任务主表同步累计 `retry_count`。
- 新增 `HarnessReplanner`，工具失败后可基于 observation 修正当前 step 的 `tool_input`；修正后仍重新经过 ToolRouter、schema 归一化、PermissionEngine 和 Adapter 执行链路。
- 新增 `POST /api/tool-calls/{tool_call_id}/replay`，支持复制历史 tool_input 重放工具调用，也支持传入 `override_input` 做对照调试。
- 当前 replay 完成的是 tool_call 级别；checkpoint 级 resume 仍建议放到后续更完整的 LangGraph 控制台/调试视图中实现。
- 已新增测试：
  - `tests/test_runtime_controls.py`
  - `tests/test_tool_call_replay.py`

验证结果：

- 当前数据库 `alembic_version=20260509_0004`。
- `pytest`：`51 passed`。

P4：工具路由最终形态

1. ToolRouter 输出 top-k candidates 和选择解释。
2. 增加 pgvector / embedding 语义召回。
3. 增加 LLM rerank，rerank 只给建议，最终选择仍由系统校验。
4. 融合 schema match、keyword score、semantic score、health、success_rate、avg_duration_ms。
5. 对无工具场景稳定返回 `NO_TOOL`。

验收标准：

- 路由不再只是关键词打分。
- 能解释为什么选择、为什么拒绝、为什么无工具。

完成记录：

- 2026-05-10 已完成 P4 工具路由最终形态的主体落地。
- `ToolRouteResult` 已扩展为 top-k 解释型输出：
  - `candidates`
  - `candidate_details`
  - `score_breakdown`
  - `matched_signals`
  - `rank`
  - `rerank`
- ToolRouter 已融合以下确定性分项：
  - schema 门禁
  - suggested tool type
  - intent -> tool_type 映射
  - tool name / tags / description keyword match
  - health_status
  - success_rate
  - avg_duration_ms
  - quality_score
  - risk_level
- schema 现在作为硬门禁使用：schema 合法不再单独贡献相关性分，schema 不匹配的工具不会被选中。
- 质量分只用于已相关候选之间排序，不会单独触发路由，避免“高质量但无关”的工具误命中。
- 新增 `ToolRerankService`：
  - LLM 只允许在系统给出的 top-k 候选中排序。
  - LLM rerank 只作为加权建议，不替代 schema、router、permission 和 sandbox。
  - Harness 内部在具备 task/run/trace 审计 ID 时启用 rerank。
- `POST /api/router/select` 已支持：
  - `top_k`
  - `enable_llm_rerank`
  - `task_id`
  - `run_id`
  - `trace_id`
- 新增 routing eval 雏形：
  - `evals/tool_routing_cases.jsonl`
  - `scripts/eval_tool_routing.py`
  - 输出 `accuracy`、`top_k_recall`、`no_tool_precision`
- 当前 pgvector / embedding 尚未引入为强依赖。原因是它会增加数据库扩展、embedding provider 和环境配置复杂度；当前已先把综合打分、rerank 接口和 eval 入口落地，后续可以在这个结构上接 pgvector 语义召回。

验证结果：

- `pytest`：`53 passed`。
- `docker compose config --quiet` 通过。
- `scripts/eval_tool_routing.py --top-k 5` 在当前本地工具数据上输出：
  - `accuracy=1.0`
  - `top_k_recall=1.0`
  - `no_tool_precision=1.0`

P5：数据观测、Console、测试与展示

等 P0-P4 主系统能力稳定后再做：

1. Step 8 Dashboard Console。
2. Step 9 实时事件流。
3. Step 10 可观测性和错误分类。
4. Step 12 单元测试、集成测试、安全测试和 eval。
5. Step 13 最终 demo 脚本、README 架构图、简历描述和面试讲解提纲。

验收标准：

- Console 展示最终数据模型，而不是中间临时结构。
- 测试覆盖最终行为，而不是早期 demo 行为。
- Demo 展示真实最终能力，而不是为了证明单点功能能跑。

当前完成记录：

- 2026-05-10 已完成 Trace 聚合 API，作为 Console 和排障视图的底层数据接口。
- 新增 `GET /api/traces/{trace_id}`。
- 新增：
  - `app/api/traces.py`
  - `app/services/trace_service.py`
  - `app/schemas/trace.py`
  - `tests/test_trace_service.py`
- Trace API 会一次聚合：
  - `tasks`
  - `task_events`
  - `tool_calls`
  - `llm_calls`
  - `sandbox_executions`
  - `approval_requests`
- Trace 响应包含：
  - `summary`
  - `timeline`
  - `summary.error_types`
- 已补齐各 Repository 的 `list_by_trace_id` 查询方法。
- 已初步标准化错误分类：
  - `NO_TOOL`
  - `PERMISSION_DENIED`
  - `TOOL_EXECUTION_FAILED`
  - `SANDBOX_TIMEOUT`
  - `TASK_TIMEOUT`
  - `LLM_PROVIDER_FAILED`
  - `TASK_FAILED`
- 这一步先完成 API 层和聚合数据模型，后续 Dashboard Console 可以直接消费该接口展示 trace 时间线。
- 2026-05-10 已完成 Dashboard Console 功能型改造。
- `dashboard/streamlit_app.py` 已从单页表格观察页改为多 tab Console：
  - Overview：任务成功率、失败数、最近任务
  - Trace：按 `trace_id` 查看 summary、timeline 和各审计表聚合数据
  - Task：查看 `run_config`、取消状态、steps、observations、summary，并支持取消任务
  - Routing：调试 top-k candidates、`score_breakdown`、`matched_signals` 和 rerank metadata
  - Replay：从历史 `tool_call_id` 发起 replay，支持 override input
  - Raw Tables：查看工具调用、LLM 调用、沙箱执行和工具健康数据
- Dashboard 不再展示数据库连接串明文，只显示应用名称。
- 2026-05-10 已完成最终 Demo 与对外表达材料。
- 新增 `scripts/final_demo.ps1`：
  - 初始化数据库并 seed canonical demo tools。
  - 展示 ToolRouter top-k candidates、score 和 reason。
  - 执行 HTTP / MCP 工具并输出 trace 链接。
  - 基于历史 `tool_call_id` 发起 replay。
  - 演示 `SAFE_EXECUTE` 下高风险 Sandbox 权限预检进入 `ASK`。
  - 提交多步 Agent task，并在 worker 可用时轮询最终结果。
- 新增 `docs/architecture.md`：
  - 总体架构图。
  - Agent Harness 执行时序。
  - LLM 与系统控制边界。
  - 核心审计数据模型。
  - Trace Console 排障入口。
- 新增 `docs/resume_and_interview.md`：
  - 简历项目名和一段式描述。
  - 可强调的工程点。
  - 不建议夸大的边界。
  - 面试讲解提纲和常见追问。
- README 已增加架构、计划、简历材料链接，并将 Demo 入口切换到 `scripts/final_demo.ps1`。

验证结果：

- `pytest`：`55 passed`。
- `python -m compileall app dashboard scripts` 通过。
- `scripts/final_demo.ps1` PowerShell 语法检查通过。
- `docker compose config --quiet` 通过。
- `streamlit run dashboard/streamlit_app.py --server.port=18501` 启动成功。
- `http://localhost:18501` 返回 HTTP 200。

补充完成记录：

- 2026-05-09 已完成 P1 治理模型的一次性落地骨架。
- 已新增 migration：`migrations/versions/20260509_0002_governance_and_redaction.py`。
- 已扩展数据库字段：
  - `tools.owner_id`
  - `tools.workspace_id`
  - `tools.metadata`
  - `tools.schema_hash`
  - `tools.quality_score`
  - `tools.success_rate`
  - `tools.avg_duration_ms`
  - `tasks.user_id`
  - `tasks.workspace_id`
  - `task_events.user_id`
  - `task_events.workspace_id`
  - `tool_calls.user_id`
  - `tool_calls.workspace_id`
  - `llm_calls.user_id`
  - `llm_calls.workspace_id`
  - `approval_requests.workspace_id`
  - `approval_requests.approval_scope`
  - `approval_requests.expires_at`
  - `approval_requests.approved_until`
  - `tool_permissions` 多维策略字段：`workspace_id`、`user_id`、`tool_type`、`risk_level`、`run_mode`、`command_rule`、`http_domain`、`network_access`、`filesystem_mount`、`priority`、`enabled`
- 已新增 `app/security/secret_manager.py`：
  - 支持 `env:XXX` secret reference
  - 支持统一 payload 脱敏
- 已接入落库脱敏：
  - `task_events.payload`
  - `tool_calls.input`
  - `tool_calls.output`
  - `llm_calls.prompt`
  - `llm_calls.response`
  - `tasks.result`
  - `approval_requests.reason`
  - `approval_requests.decision_reason`
- HTTP Adapter 已支持在 headers / JSON body 中解析 `env:XXX` secret reference。
- PermissionEngine 已接入 `tool_permissions` 多维策略查询；没有命中策略时退回内置 risk/run_mode 规则。
- Approval 已支持：
  - `workspace_id`
  - `approval_scope`
  - `expires_at`
  - `approved_until`
  - 自动过滤和标记过期待审批请求
- Task 提交和 Harness 状态已带上 `user_id` / `workspace_id`。
- 已新增测试：
  - `tests/test_secret_redaction.py`
  - `tests/test_governance_schema.py`

验证结果：

- `scripts/init_db.py` 已成功升级到 `alembic_version=20260509_0002`。
- 已验证敏感 `Authorization` / `X-Api-Key` 写入 `task_events.payload` 前会被替换为 `***REDACTED***`。
- `pytest`：`44 passed`。

#### 14.3 最终简历项目边界

最终不要写成“生产级 Agent 平台”，建议定位为：

```text
ToolHub：面向 CLI / IDE Agent 的 Agent Tool Runtime / Harness MVP
```

可以强调：

- 统一工具注册、路由、权限、执行和审计。
- LLM 负责意图理解和计划建议，系统负责校验、权限和安全执行。
- 支持 MCP / HTTP / CLI / Sandbox 四类工具。
- 高风险工具支持审批流。
- 多步任务可追踪 plan、steps、observations、tool_calls、llm_calls。
- CLI / Sandbox 默认隔离执行，避免 Agent 直接操作宿主机。

不要夸大：

- 不说已经是生产级多租户平台。
- 不说已经完整替代 LangChain / Dify / MCP Host。
- 不说权限系统已经企业级。
- 不说 Agent loop 已经完整自我修复。

---

## 17. 建议执行顺序

当前执行策略改为：直接落地最终状态，先完成主系统能力，再做数据观测、Console、测试评估和最终展示。也就是说，短期内不要把主要精力放在 Dashboard 美化、测试数量堆叠和 demo 包装上。

```text
第一阶段：最终工程底座
1. Step 11 Alembic migration
2. Step 11 docker compose 完整编排
3. Step 14 显式配置与 LLM_MOCK_ENABLED
4. Step 14 healthcheck 与启动配置校验

第二阶段：最终安全与治理模型
5. Step 14 secret reference
6. Step 14 payload 脱敏
7. Step 14 user_id / workspace_id
8. Step 14 多维 policy 与审批范围

第三阶段：最终工具平台
9. Step 14 mock/demo 资产隔离
10. Step 14 HTTP OpenAPI import
11. Step 14 CLI rule pack + local override
12. Step 14 Sandbox Python / Node / artifact / 网络与挂载策略
13. Step 14 工具 owner / workspace / version / quality metrics

第四阶段：最终 Agent Harness
14. Step 14 bounded retry
15. Step 14 observation-driven replanning
16. Step 14 task cancel
17. Step 14 replay / resume
18. Step 14 任务级 max_steps / retry / timeout 配置

第五阶段：最终工具路由
19. Step 14 top-k candidates
20. Step 14 embedding / pgvector 语义召回
21. Step 14 LLM rerank
22. Step 14 融合 schema / semantic / health / success_rate 的综合打分

第六阶段：数据观测与产品体验
23. Step 8 Dashboard Console
24. Step 9 实时事件流
25. Step 10 可观测性指标和错误分类

第七阶段：测试、评估与最终展示
26. Step 12 单元测试、集成测试、安全测试
27. Step 12 routing / permission / malicious input eval
28. Step 13 最终 demo 脚本、README 架构图、简历表达和面试提纲
```

这个顺序的判断依据：

```text
1. 数据模型和部署方式不稳定时，先做 Dashboard 和测试会反复返工。
2. 工具、权限、Secret、Agent loop、Router 才是项目是否像真实 Agent Infra 的核心。
3. 观测系统应该展示最终链路，而不是临时过渡链路。
4. 测试和 eval 应该验证最终行为，而不是 demo 行为。
5. 最终 demo 应该是收尾产物，不应该决定系统架构。
```

完成第一到第五阶段后，再进入数据观测和测试阶段。完成全部阶段后，项目可以比较有底气地写进简历，定位为：

```text
ToolHub：面向 CLI / IDE Agent 的 Agent Tool Runtime / Harness MVP
```
