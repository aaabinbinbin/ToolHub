# ToolHub 代码审查修复计划

## 修复日期

2026-05-10

## 修复概览

本次修复针对 ToolHub Agent Tool Runtime / Agent Harness 进行了系统性的代码审查和修复，重点解决以下问题：

1. Harness 状态流转 bug
2. 安全加固（Sandbox / HTTP / CLI）
3. 测试补齐
4. 路由评估扩展
5. 文档准确性

## 已修复的问题

### 1. Harness 状态流转修复

**问题**: `_record_event` 无条件把 `task.status` 写成 `RUNNING`，导致 `WAITING_APPROVAL` / `DENIED` / `CANCELLED` / `TIMEOUT` / `NO_TOOL` / `PLANNED` 状态被后续事件覆盖。

**修复**:
- `TaskRepository.update_status`: 新增 `protected_statuses` 保护，终端状态 + `WAITING_APPROVAL` + `RETRYING` 不会被 `RUNNING` 覆盖
- `TaskRepository`: 新增 `update_current_step` 方法，只更新 `current_step` 不修改 `status`
- `AgentHarnessWorkflow._record_event`: 改为使用 `update_current_step` 替代 `update_status(status="RUNNING")`
- `AgentHarnessWorkflow._terminal_guard`: 扩展 `NON_RUNNABLE_STATES` 包含所有不可执行状态
- 代码文件: `app/repositories/task_repository.py`, `app/harness/workflow.py`

### 2. PLAN_ONLY 防护

**问题**: 需要确保 PLAN_ONLY 下不产生 tool_calls/sandbox_executions。

**修复**:
- `_terminal_guard` 中 `NON_RUNNABLE_STATES` 包含 `PLANNED`
- `_next_after_plan` 在 `final_status == "PLANNED"` 时路由到 summarize（已有，已验证正确）
- 测试: `tests/test_plan_only_mode.py`

### 3. Approval 闭环验证

**确认**: 
- `create_or_get_pending` 复用已有待审批请求，不会重复创建
- `approve` 后切换到 `FULL_EXECUTE` 并重新入队
- `reject` 后进入 `DENIED`
- 审批通过后重新执行时，`PermissionEngine` 对 `FULL_EXECUTE + HIGH` 返回 `ALLOW`
- 测试: `tests/test_approval_resume.py`

### 4. 安全加固

**Docker Sandbox**:
- 新增 `SANDBOX_READ_ONLY` 配置（默认 true）：只读根文件系统
- 新增 `SANDBOX_NO_NEW_PRIVILEGES` 配置（默认 true）：禁止提权
- 新增 `SANDBOX_CAP_DROP_ALL` 配置（默认 true）：移除所有 Linux capabilities
- 新增 `SANDBOX_TMPFS_SIZE` 配置（默认 64m）：/tmp 挂载为 tmpfs 并设置 noexec,nosuid
- artifact_path 约束：只允许 `/workspace/output` 下的路径
- 代码文件: `app/common/config.py`, `app/infra/docker_sandbox.py`

**HTTP Adapter**:
- 新增云厂商元数据 hostname 拦截：`metadata.google.internal`, `169.254.169.254`, `metadata.tencentyun.com`, `100.100.100.200`
- 新增显式元数据 IP 检查：`169.254.169.254`, `100.100.100.200`
- 重定向时重新校验 URL（已有，验证正确）
- 代码文件: `app/security/http_policy.py`

**CLI Adapter**:
- 已通过 `CLICommandPolicy.build_plan` 强制 rule_id + 结构化参数（已有，验证正确）

### 5. 测试补齐

新增测试文件:
- `tests/test_task_cancel_service.py` — cancel_task 功能和终端状态保护
- `tests/test_task_submit_run_config.py` — run_config/user_id/workspace_id 传递 + Celery delay 时序
- `tests/test_task_submit_transaction.py` — 同事务内创建 task + event
- `tests/test_approval_resume.py` — 审批创建/复用/通过/拒绝
- `tests/test_plan_only_mode.py` — PLAN_ONLY 不执行工具
- `tests/test_harness_status_transition.py` — 状态保护验证
- `tests/test_tool_rerank_service.py` — rerank 服务及安全边界
- `tests/test_http_adapter_security.py` — SSRF/元数据/危险头测试
- `tests/test_sandbox_security.py` — 沙箱安全加固测试
- `tests/test_replanner_schema_recovery.py` — 重规划器 LLM fallback 测试
- `tests/test_final_demo_flow.py` — 完整权限矩阵测试

### 6. 路由评估扩展

- 评估样例从 6 条扩展到 52 条
- 新增危险输入样例（防止工具误匹配）
- 评估指标新增: `top1_accuracy`, `top3_recall`, `schema_reject_accuracy`, `dangerous_tool_avoidance_rate`
- 文件: `evals/tool_routing_cases.jsonl`, `scripts/eval_tool_routing.py`

## 验收步骤

1. 运行全部测试: `uv run pytest -q`
2. 运行路由评估: `python scripts/eval_tool_routing.py --top-k 5`
3. 启动服务: `docker compose up --build`
4. 运行演示: `scripts/final_demo.ps1`

## 项目边界（未改动）

以下属于后续增强，本次未做修改:
- pgvector / embedding 语义召回（README 中已标注为未实现）
- 真实登录 / RBAC / 组织级权限
- SSE / WebSocket 实时事件流
- 独立前端（当前为 Streamlit Console）
- 完整 JSON Schema 实现（当前为轻量子集）
- MCP server 鉴权 header / OAuth

## 当前测试基线

修复前: 55 passed
修复后: 104 passed
