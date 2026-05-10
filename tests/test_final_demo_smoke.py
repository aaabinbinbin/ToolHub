from __future__ import annotations

"""
final_demo 自动化冒烟测试。

覆盖 `scripts/final_demo.ps1` 的核心链路：
  1. 工具注册（seed demo tools）
  2. 工具路由选择
  3. 权限预检
  4. 任务提交与跟踪
  5. Trace 聚合查询
  6. 工具 replay
"""

from datetime import datetime, timezone
from uuid import UUID, uuid4

from app.repositories.db import get_connection, init_db
from app.repositories.task_repository import TaskRepository
from app.schemas.permission import PermissionDecisionType, RunMode
from app.schemas.task import TaskRunConfig, TaskSubmitRequest
from app.schemas.tool import (
    HealthStatus,
    RiskLevel,
    ToolRegisterRequest,
    ToolResponse,
    ToolStatus,
    ToolType,
)
from app.schemas.tool_call import ToolCallResult
from app.security.permission_engine import PermissionEngine
from app.services.task_service import TaskService
from app.services.tool_router_service import ToolRouterService
from app.services.tool_registry_service import ToolRegistryService
from app.services.trace_service import TraceService


# ── helpers ──────────────────────────────────────────────────────────


def _seed_demo_tools() -> None:
    """注册 canonical demo 工具到数据库。"""
    from app.repositories.tool_repository import ToolRepository

    tools = [
        ToolRegisterRequest(
            name="toolhub-demo-http-echo",
            description="HTTP echo 演示工具",
            tool_type=ToolType.HTTP,
            endpoint="mock://echo",
            version="1.0.0",
            tags=["demo", "http"],
            risk_level=RiskLevel.LOW,
        ),
        ToolRegisterRequest(
            name="toolhub-demo-mcp-calculator",
            description="MCP calculator 演示工具",
            tool_type=ToolType.MCP,
            endpoint="calculator",
            mcp_url="mock://calculator",
            version="1.0.0",
            tags=["demo", "mcp"],
            risk_level=RiskLevel.LOW,
        ),
        ToolRegisterRequest(
            name="toolhub-demo-cli-git-status",
            description="CLI git status 演示工具",
            tool_type=ToolType.CLI,
            endpoint="cli://git/status-short",
            version="1.0.0",
            tags=["demo", "cli", "git"],
            risk_level=RiskLevel.LOW,
        ),
        ToolRegisterRequest(
            name="toolhub-demo-python-sandbox",
            description="Python 沙箱演示工具",
            tool_type=ToolType.SANDBOX,
            endpoint="python",
            version="1.0.0",
            tags=["demo", "sandbox", "python"],
            risk_level=RiskLevel.HIGH,
        ),
    ]
    with get_connection() as connection:
        repo = ToolRepository(connection)
        for t in tools:
            try:
                repo.create(t)
            except Exception:
                connection.rollback()


def _make_tool_response(**kwargs) -> ToolResponse:
    """构造 ToolResponse 用于 PermissionEngine。"""
    now = datetime.now(timezone.utc)
    defaults = {
        "id": uuid4(),
        "name": "test-tool",
        "description": "test tool",
        "tool_type": ToolType.SANDBOX,
        "endpoint": "python",
        "mcp_url": None,
        "transport": None,
        "version": "1.0.0",
        "input_schema": None,
        "output_schema": None,
        "tags": [],
        "risk_level": RiskLevel.LOW,
        "status": ToolStatus.ACTIVE,
        "health_status": HealthStatus.UP,
        "last_checked_at": None,
        "created_at": now,
        "updated_at": now,
    }
    defaults.update(kwargs)
    return ToolResponse(**defaults)


# ── test cases ───────────────────────────────────────────────────────


def test_smoke_seed_and_search_tools() -> None:
    """冒烟：注册 demo 工具后可通过 search 查到。"""
    init_db()
    _seed_demo_tools()

    registry = ToolRegistryService()
    results = registry.search_tools("demo", include_disabled=False)
    assert len(results) >= 4, f"期望至少 4 个 demo 工具，实际 {len(results)}"


def test_smoke_router_select_http_echo() -> None:
    """冒烟：Router 能为 HTTP echo 请求选中正确工具。"""
    init_db()
    _seed_demo_tools()

    router = ToolRouterService()
    route = router.select_tool(
        user_input="调用 HTTP echo 接口",
        intent="HTTP_CALL",
        suggested_tool_type="HTTP",
        tool_input={"method": "GET", "params": {"q": "test"}},
        top_k=3,
    )
    assert route.selected_tool is not None, route.reason
    assert "http" in route.selected_tool.name.lower()
    assert route.score > 0


def test_smoke_router_select_mcp_calculator() -> None:
    """冒烟：Router 能为 MCP 计算请求选中 calculator 工具。"""
    init_db()
    _seed_demo_tools()

    router = ToolRouterService()
    route = router.select_tool(
        user_input="计算 1 + 2",
        intent="CALCULATE",
        suggested_tool_type="MCP",
        tool_input={"expression": "1 + 2"},
        top_k=3,
    )
    assert route.selected_tool is not None, route.reason
    assert "calculator" in route.selected_tool.name.lower()


def test_smoke_router_no_tool_for_unrelated_input() -> None:
    """冒烟：无关联输入应返回空工具。"""
    init_db()
    _seed_demo_tools()

    router = ToolRouterService()
    route = router.select_tool(
        user_input="帮我写一首诗关于春天",
        intent="GENERAL_QUERY",
        suggested_tool_type=None,
        tool_input={},
        top_k=3,
    )
    assert route.selected_tool is None, f"不应该匹配到工具: {route.selected_tool}"


def test_smoke_permission_safe_execute_high_asks() -> None:
    """冒烟：SAFE_EXECUTE + HIGH 风险工具 → ASK。"""
    engine = PermissionEngine()
    decision = engine.check(
        _make_tool_response(name="danger-tool", risk_level=RiskLevel.HIGH),
        RunMode.SAFE_EXECUTE,
    )
    assert decision.decision == PermissionDecisionType.ASK
    assert decision.required_mode == RunMode.FULL_EXECUTE


def test_smoke_permission_full_matrix() -> None:
    """冒烟：完整权限矩阵验证。"""
    engine = PermissionEngine()
    cases = [
        (RunMode.PLAN_ONLY, RiskLevel.LOW, PermissionDecisionType.DENY),
        (RunMode.PLAN_ONLY, RiskLevel.HIGH, PermissionDecisionType.DENY),
        (RunMode.SAFE_EXECUTE, RiskLevel.LOW, PermissionDecisionType.ALLOW),
        (RunMode.SAFE_EXECUTE, RiskLevel.HIGH, PermissionDecisionType.ASK),
        (RunMode.FULL_EXECUTE, RiskLevel.LOW, PermissionDecisionType.ALLOW),
        (RunMode.FULL_EXECUTE, RiskLevel.HIGH, PermissionDecisionType.ALLOW),
    ]
    for run_mode, risk, expected in cases:
        decision = engine.check(
            _make_tool_response(name="perm-test", risk_level=risk),
            run_mode,
        )
        assert decision.decision == expected, (
            f"{run_mode.value} × {risk.value}: 期望 {expected}, 实际 {decision.decision}"
        )


def test_smoke_task_submit_and_query() -> None:
    """冒烟：提交 PLAN_ONLY 任务后可查询其状态和事件。"""
    init_db()

    service = TaskService()
    response = service.submit_task(
        TaskSubmitRequest(
            user_input="请查看 git status",
            run_mode=RunMode.PLAN_ONLY,
            run_config=TaskRunConfig(max_steps=1, max_retries=0),
        )
    )

    task = service.get_task(response.task_id)
    assert task.status in {"QUEUED", "RUNNING", "PLANNED", "SUCCESS"}, task.status
    assert task.run_config["max_steps"] == 1

    events = service.get_task_events(response.task_id)
    event_types = {e.event_type for e in events}
    assert "TASK_SUBMITTED" in event_types


def test_smoke_trace_aggregation() -> None:
    """冒烟：提交任务后 trace API 可聚合到数据。"""
    init_db()

    service = TaskService()
    response = service.submit_task(
        TaskSubmitRequest(
            user_input="trace smoke test",
            run_mode=RunMode.PLAN_ONLY,
            run_config=TaskRunConfig(max_steps=1, max_retries=0),
        )
    )

    trace = TraceService().get_trace(response.trace_id)
    assert trace.trace_id == response.trace_id
    assert len(trace.tasks) >= 1
    assert len(trace.task_events) >= 1
    assert trace.summary is not None
    assert len(trace.timeline) >= 1


def test_smoke_replay_tool_call() -> None:
    """冒烟：基于历史 tool_call_id 发起 replay 并验证关联。"""
    init_db()

    from app.repositories.tool_call_repository import ToolCallRepository
    from app.repositories.tool_repository import ToolRepository

    # 注册工具并创建任务以满足 FK 约束
    with get_connection() as connection:
        try:
            registered = ToolRepository(connection).create(
                ToolRegisterRequest(
                    name="smoke-test-echo",
                    description="smoke replay test",
                    tool_type=ToolType.HTTP,
                    endpoint="mock://echo",
                    version="1.0.0",
                    risk_level=RiskLevel.LOW,
                )
            )
        except Exception:
            connection.rollback()
            registered = connection.execute(
                "SELECT id FROM tools WHERE name = 'smoke-test-echo'"
            ).fetchone()
        tool_id = registered["id"]

        task = TaskRepository(connection).create_queued_task(
            user_input="replay test",
            run_mode=RunMode.SAFE_EXECUTE,
            priority="default",
        )
        task_id = task["id"]
        run_id = task["run_id"]
        trace_id = task["trace_id"]

        # 创建原始 tool_call
        original_result = ToolCallResult(
            success=True, status="SUCCESS",
            tool_id=tool_id, tool_name="smoke-test-echo", tool_type="HTTP",
            input={"method": "GET"}, output={"status_code": 200},
            duration_ms=42, run_id=run_id, trace_id=trace_id, task_id=task_id,
            user_id="local-user", workspace_id="default",
        )
        original_id = ToolCallRepository(connection).create(original_result)

        # 创建 replay
        replay_result = ToolCallResult(
            success=True, status="SUCCESS",
            tool_id=tool_id, tool_name="smoke-test-echo", tool_type="HTTP",
            input={"method": "GET", "params": {"q": "replay-test"}},
            output={"status_code": 200}, duration_ms=38,
            run_id=run_id, trace_id=trace_id, task_id=task_id,
            user_id="local-user", workspace_id="default",
            replay_of_tool_call_id=original_id,
            replay_reason="冒烟测试 replay",
        )
        replay_id = ToolCallRepository(connection).create(replay_result)

    # 从 DB 读取验证 replay 关联
    with get_connection() as connection:
        loaded = ToolCallRepository(connection).get_by_id(replay_id)
    assert loaded is not None
    assert loaded["replay_of_tool_call_id"] == original_id


def test_smoke_replay_via_service() -> None:
    """冒烟：通过 ToolReplayService 发起 replay。"""
    init_db()

    from app.repositories.tool_call_repository import ToolCallRepository
    from app.schemas.tool_call import ToolCallReplayRequest
    from app.services.tool_replay_service import ToolReplayService

    # 先创建真实任务以满足 FK 约束
    with get_connection() as connection:
        task = TaskRepository(connection).create_queued_task(
            user_input="replay via service test",
            run_mode=RunMode.SAFE_EXECUTE,
            priority="default",
        )
        task_id = task["id"]
        run_id = task["run_id"]
        trace_id = task["trace_id"]

    tool_id = uuid4()

    # 注册工具并创建原始 tool_call（同事务满足 FK）
    from app.repositories.tool_repository import ToolRepository
    with get_connection() as connection:
        try:
            registered = ToolRepository(connection).create(
                ToolRegisterRequest(
                    name="smoke-echo",
                    description="smoke test echo",
                    tool_type=ToolType.HTTP,
                    endpoint="mock://echo",
                    version="1.0.0",
                    risk_level=RiskLevel.LOW,
                )
            )
        except Exception:
            connection.rollback()
            registered = connection.execute(
                "SELECT id FROM tools WHERE name = 'smoke-echo'"
            ).fetchone()
        tool_id = registered["id"]

        original_result = ToolCallResult(
            success=True, status="SUCCESS",
            tool_id=tool_id, tool_name="smoke-echo", tool_type="HTTP",
            input={"method": "GET", "params": {"echo": "hello"}},
            output={"echo": "hello"}, duration_ms=10,
            run_id=run_id, trace_id=trace_id, task_id=task_id,
            user_id="local-user", workspace_id="default",
        )
        original_id = ToolCallRepository(connection).create(original_result)

    # 发起 replay
    service = ToolReplayService()
    replay = service.replay_tool_call(
        tool_call_id=original_id,
        request=ToolCallReplayRequest(
            override_input={"method": "GET", "params": {"echo": "replay-smoke"}},
            reason="冒烟测试 replay service",
        ),
    )
    assert replay.success is True
    assert replay.replay_of_tool_call_id == original_id
    assert "replay-smoke" in str(replay.input)
