from __future__ import annotations

import json
import sys
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any
from uuid import UUID

import pandas as pd
import streamlit as st

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.common.config import get_settings, validate_settings
from app.common.exceptions import ToolHubError
from app.repositories.db import get_connection
from app.schemas.task import TaskCancelRequest
from app.schemas.tool_call import ToolCallReplayRequest
from app.services.task_service import TaskService
from app.services.tool_replay_service import ToolReplayService
from app.services.tool_router_service import ToolRouterService
from app.services.trace_service import TraceService


validate_settings()
st.set_page_config(page_title="ToolHub Console", page_icon="TH", layout="wide")


def run_query(query: str, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    """执行只读查询并返回 dict 列表。"""
    with get_connection() as connection:
        return list(connection.execute(query, params or {}).fetchall())


def json_safe(value: Any) -> Any:
    """把 UUID、datetime、Decimal 等对象转换为 Streamlit JSON 可展示结构。"""
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, datetime | date):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, dict):
        return {str(key): json_safe(item) for key, item in value.items()}
    if isinstance(value, list | tuple):
        return [json_safe(item) for item in value]
    return value


def to_dataframe(rows: list[dict[str, Any]] | list[Any]) -> pd.DataFrame:
    """转换为 DataFrame，空结果也返回可展示对象。"""
    if not rows:
        return pd.DataFrame()
    return pd.DataFrame([json_safe(row) for row in rows])


def parse_uuid(value: str, *, label: str) -> UUID | None:
    """解析 UUID 输入，失败时在页面上提示。"""
    value = value.strip()
    if not value:
        st.warning(f"请输入 {label}。")
        return None
    try:
        return UUID(value)
    except ValueError:
        st.warning(f"{label} 不是合法 UUID。")
        return None


def parse_json_object(value: str, *, label: str) -> dict[str, Any] | None:
    """解析 JSON 对象输入。"""
    value = value.strip()
    if not value:
        return {}
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError as exc:
        st.warning(f"{label} JSON 格式错误：{exc}")
        return None
    if not isinstance(parsed, dict):
        st.warning(f"{label} 必须是 JSON object。")
        return None
    return parsed


def format_duration(value: Any) -> str:
    """格式化毫秒耗时。"""
    if value is None:
        return "-"
    return f"{int(value)} ms"


def load_overview() -> dict[str, Any]:
    """读取任务概览指标。"""
    rows = run_query(
        """
        SELECT
            count(*) AS total_tasks,
            count(*) FILTER (WHERE status = 'SUCCESS') AS success_tasks,
            count(*) FILTER (WHERE status = 'FAILED') AS failed_tasks,
            count(*) FILTER (WHERE status = 'DENIED') AS denied_tasks,
            count(*) FILTER (WHERE status = 'NO_TOOL') AS no_tool_tasks,
            count(*) FILTER (WHERE status = 'CANCELLED') AS cancelled_tasks,
            avg(EXTRACT(EPOCH FROM (finished_at - started_at)) * 1000)
                FILTER (WHERE finished_at IS NOT NULL AND started_at IS NOT NULL)
                AS avg_duration_ms
        FROM tasks
        """
    )
    return rows[0] if rows else {}


def load_recent_tasks(limit: int) -> list[dict[str, Any]]:
    """读取最近任务列表。"""
    return run_query(
        """
        SELECT
            id, trace_id, run_id, status, current_step, run_mode, priority,
            cancel_requested, user_input,
            result -> 'summary' ->> 'final_answer' AS final_answer,
            created_at, started_at, finished_at, updated_at
        FROM tasks
        ORDER BY created_at DESC
        LIMIT %(limit)s
        """,
        {"limit": limit},
    )


def load_task(task_id: UUID) -> dict[str, Any] | None:
    """读取单个任务。"""
    rows = run_query("SELECT * FROM tasks WHERE id = %(task_id)s", {"task_id": task_id})
    return rows[0] if rows else None


def load_task_events(task_id: UUID) -> list[dict[str, Any]]:
    """读取任务事件。"""
    return run_query(
        """
        SELECT id, event_type, step, message, payload, created_at
        FROM task_events
        WHERE task_id = %(task_id)s
        ORDER BY created_at ASC
        """,
        {"task_id": task_id},
    )


def load_tool_calls(task_id: UUID | None = None, limit: int = 50) -> list[dict[str, Any]]:
    """读取工具调用记录。"""
    where_clause = "WHERE task_id = %(task_id)s" if task_id else ""
    params: dict[str, Any] = {"limit": limit}
    if task_id:
        params["task_id"] = task_id
    return run_query(
        f"""
        SELECT
            id, task_id, run_id, trace_id, created_at, tool_id, tool_name,
            tool_type, status, duration_ms, error_message, input, output,
            artifacts, replay_of_tool_call_id, replay_reason
        FROM tool_calls
        {where_clause}
        ORDER BY created_at DESC
        LIMIT %(limit)s
        """,
        params,
    )


def load_llm_calls(task_id: UUID | None = None, limit: int = 50) -> list[dict[str, Any]]:
    """读取 LLM 调用记录。"""
    where_clause = "WHERE task_id = %(task_id)s" if task_id else ""
    params: dict[str, Any] = {"limit": limit}
    if task_id:
        params["task_id"] = task_id
    return run_query(
        f"""
        SELECT
            id, task_id, run_id, trace_id, created_at, node_name, provider,
            model, status, input_tokens, output_tokens, duration_ms,
            error_message
        FROM llm_calls
        {where_clause}
        ORDER BY created_at DESC
        LIMIT %(limit)s
        """,
        params,
    )


def load_sandbox_executions(
    task_id: UUID | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    """读取沙箱执行记录。"""
    where_clause = "WHERE task_id = %(task_id)s" if task_id else ""
    params: dict[str, Any] = {"limit": limit}
    if task_id:
        params["task_id"] = task_id
    return run_query(
        f"""
        SELECT
            id, task_id, run_id, trace_id, created_at, tool_name, command,
            status, exit_code, duration_ms, timeout_seconds, container_id,
            language, artifacts, stdout, stderr, error_message
        FROM sandbox_executions
        {where_clause}
        ORDER BY created_at DESC
        LIMIT %(limit)s
        """,
        params,
    )


def load_tool_health() -> list[dict[str, Any]]:
    """读取工具健康和质量指标。"""
    return run_query(
        """
        SELECT
            t.id, t.name, t.tool_type, t.status, t.health_status, t.risk_level,
            t.success_rate, t.avg_duration_ms, t.quality_score, t.last_checked_at,
            h.status AS last_check_status,
            h.latency_ms,
            h.error_message,
            h.checked_at
        FROM tools t
        LEFT JOIN LATERAL (
            SELECT status, latency_ms, error_message, checked_at
            FROM tool_health_checks
            WHERE tool_id = t.id
            ORDER BY checked_at DESC
            LIMIT 1
        ) h ON true
        WHERE t.status != 'DELETED'
        ORDER BY t.created_at DESC
        """
    )


def render_overview(recent_limit: int) -> None:
    """渲染概览页。"""
    overview = load_overview()
    total = int(overview.get("total_tasks") or 0)
    success = int(overview.get("success_tasks") or 0)
    failed = int(overview.get("failed_tasks") or 0)
    denied = int(overview.get("denied_tasks") or 0)
    no_tool = int(overview.get("no_tool_tasks") or 0)
    cancelled = int(overview.get("cancelled_tasks") or 0)
    success_rate = (success / total * 100) if total else 0

    cols = st.columns(6)
    cols[0].metric("任务总数", total)
    cols[1].metric("成功率", f"{success_rate:.1f}%")
    cols[2].metric("失败", failed)
    cols[3].metric("权限拒绝", denied)
    cols[4].metric("无工具", no_tool)
    cols[5].metric("已取消", cancelled)
    st.metric("平均耗时", format_duration(overview.get("avg_duration_ms")))

    st.subheader("最近任务")
    st.dataframe(to_dataframe(load_recent_tasks(recent_limit)), use_container_width=True)


def render_trace_console(recent_tasks: list[dict[str, Any]]) -> None:
    """渲染 Trace 聚合视图。"""
    trace_options = [str(row["trace_id"]) for row in recent_tasks if row.get("trace_id")]
    if not trace_options:
        st.info("暂无任务 trace。")
        return
    selected = st.selectbox("trace_id", trace_options, key="trace_select")
    manual = st.text_input("手动输入 trace_id", value=selected or "", key="trace_input")
    trace_id = parse_uuid(manual, label="trace_id")
    if trace_id is None:
        return

    try:
        trace = TraceService().get_trace(trace_id)
    except ToolHubError as exc:
        st.warning(exc.message)
        return

    data = trace.model_dump(mode="json")
    summary = data["summary"]
    cols = st.columns(6)
    cols[0].metric("任务", summary["task_count"])
    cols[1].metric("事件", summary["event_count"])
    cols[2].metric("工具调用", summary["tool_call_count"])
    cols[3].metric("LLM 调用", summary["llm_call_count"])
    cols[4].metric("沙箱执行", summary["sandbox_execution_count"])
    cols[5].metric("审批", summary["approval_count"])
    st.json(summary)

    tabs = st.tabs(["Timeline", "Tasks", "Events", "Tool Calls", "LLM Calls", "Sandbox", "Approvals"])
    with tabs[0]:
        st.dataframe(to_dataframe(data["timeline"]), use_container_width=True)
    with tabs[1]:
        st.dataframe(to_dataframe(data["tasks"]), use_container_width=True)
    with tabs[2]:
        st.dataframe(to_dataframe(data["task_events"]), use_container_width=True)
    with tabs[3]:
        st.dataframe(to_dataframe(data["tool_calls"]), use_container_width=True)
    with tabs[4]:
        st.dataframe(to_dataframe(data["llm_calls"]), use_container_width=True)
    with tabs[5]:
        st.dataframe(to_dataframe(data["sandbox_executions"]), use_container_width=True)
    with tabs[6]:
        st.dataframe(to_dataframe(data["approval_requests"]), use_container_width=True)


def render_task_console(recent_tasks: list[dict[str, Any]]) -> None:
    """渲染任务详情、取消状态和执行结果。"""
    task_options = [str(row["id"]) for row in recent_tasks]
    if not task_options:
        st.info("暂无任务。")
        return
    selected = st.selectbox("task_id", task_options, key="task_select")
    manual = st.text_input("手动输入 task_id", value=selected or "", key="task_input")
    task_id = parse_uuid(manual, label="task_id")
    if task_id is None:
        return

    task = load_task(task_id)
    if not task:
        st.warning("未找到任务。")
        return

    left, right = st.columns([1, 1])
    with left:
        st.json(
            json_safe(
                {
                    "id": task["id"],
                    "status": task["status"],
                    "current_step": task["current_step"],
                    "run_mode": task["run_mode"],
                    "run_config": task.get("run_config"),
                    "cancel_requested": task.get("cancel_requested"),
                    "cancel_reason": task.get("cancel_reason"),
                    "run_id": task["run_id"],
                    "trace_id": task["trace_id"],
                }
            )
        )
    with right:
        result = task.get("result") or {}
        summary = result.get("summary") if isinstance(result, dict) else None
        if summary:
            st.write(summary.get("final_answer"))
            st.caption(f"summary_type={summary.get('summary_type')}")
        else:
            st.info("暂无 summary。")
        cancel_reason = st.text_input("取消原因", value="用户在 Console 中取消", key="cancel_reason")
        if st.button("取消任务", key="cancel_task"):
            response = TaskService().cancel_task(
                task_id,
                TaskCancelRequest(reason=cancel_reason, requested_by="dashboard"),
            )
            st.success(f"取消请求已提交：{response.status}")
            st.rerun()

    result_tabs = st.tabs(["Steps", "Observations", "Events", "Tool Calls", "LLM Calls", "Sandbox", "Raw Result"])
    result = task.get("result") or {}
    with result_tabs[0]:
        st.dataframe(to_dataframe((result.get("steps") if isinstance(result, dict) else []) or []), use_container_width=True)
    with result_tabs[1]:
        st.dataframe(to_dataframe((result.get("observations") if isinstance(result, dict) else []) or []), use_container_width=True)
    with result_tabs[2]:
        st.dataframe(to_dataframe(load_task_events(task_id)), use_container_width=True)
    with result_tabs[3]:
        st.dataframe(to_dataframe(load_tool_calls(task_id)), use_container_width=True)
    with result_tabs[4]:
        st.dataframe(to_dataframe(load_llm_calls(task_id)), use_container_width=True)
    with result_tabs[5]:
        st.dataframe(to_dataframe(load_sandbox_executions(task_id)), use_container_width=True)
    with result_tabs[6]:
        st.json(json_safe(result))


def render_routing_debug() -> None:
    """渲染路由调试页。"""
    with st.form("routing_debug_form"):
        user_input = st.text_area("user_input", value="请查看 git status")
        intent = st.selectbox(
            "intent",
            ["", "CLI_EXECUTION", "RUN_CODE", "HTTP_CALL", "CALCULATE", "GENERAL_QUERY"],
        )
        suggested_tool_type = st.selectbox(
            "suggested_tool_type",
            ["", "CLI", "SANDBOX", "HTTP", "MCP"],
        )
        tool_input_text = st.text_area(
            "tool_input JSON",
            value='{"rule_id":"cli://git/status-short","args":{}}',
        )
        top_k = st.slider("top_k", 1, 20, 5)
        enable_llm_rerank = st.checkbox("enable_llm_rerank", value=False)
        submitted = st.form_submit_button("运行路由")

    if not submitted:
        return
    tool_input = parse_json_object(tool_input_text, label="tool_input")
    if tool_input is None:
        return

    route = ToolRouterService().select_tool(
        user_input=user_input,
        intent=intent or None,
        suggested_tool_type=suggested_tool_type or None,
        tool_input=tool_input,
        top_k=top_k,
        enable_llm_rerank=enable_llm_rerank,
    )
    data = route.model_dump(mode="json")
    st.json(
        {
            "selected_tool": data["selected_tool"]["name"] if data["selected_tool"] else None,
            "score": data["score"],
            "reason": data["reason"],
            "schema_match": data["schema_match"],
            "rerank": data["rerank"],
        }
    )
    st.dataframe(to_dataframe(data["candidate_details"]), use_container_width=True)


def render_replay_console() -> None:
    """渲染工具调用 replay 入口。"""
    recent_calls = load_tool_calls(limit=100)
    if not recent_calls:
        st.info("暂无工具调用记录。")
        return
    call_options = [
        f'{row["id"]} | {row["tool_name"]} | {row["status"]} | {row["created_at"]}'
        for row in recent_calls
    ]
    selected = st.selectbox("tool_call", call_options, key="replay_select")
    source_id_text = selected.split(" | ", 1)[0] if selected else ""
    manual = st.text_input("手动输入 tool_call_id", value=source_id_text, key="replay_input")
    source_id = parse_uuid(manual, label="tool_call_id")
    if source_id is None:
        return

    source_call = next((row for row in recent_calls if str(row["id"]) == str(source_id)), None)
    if source_call:
        st.json(json_safe(source_call))

    override_text = st.text_area("override_input JSON（留空则使用原始 input）", value="")
    reason = st.text_input("replay_reason", value="dashboard replay")
    if st.button("执行 Replay", key="execute_replay"):
        override_input = parse_json_object(override_text, label="override_input")
        if override_input is None:
            return
        request = ToolCallReplayRequest(
            override_input=override_input or None,
            reason=reason,
            user_id="dashboard",
            workspace_id=source_call.get("workspace_id") if source_call else None,
        )
        result = ToolReplayService().replay_tool_call(source_id, request)
        st.success(f"Replay 完成：{result.status}")
        st.json(result.model_dump(mode="json"))


def render_raw_tables() -> None:
    """渲染原始审计表。"""
    tabs = st.tabs(["Tool Calls", "LLM Calls", "Sandbox", "Tool Health"])
    with tabs[0]:
        st.dataframe(to_dataframe(load_tool_calls()), use_container_width=True)
    with tabs[1]:
        st.dataframe(to_dataframe(load_llm_calls()), use_container_width=True)
    with tabs[2]:
        st.dataframe(to_dataframe(load_sandbox_executions()), use_container_width=True)
    with tabs[3]:
        st.dataframe(to_dataframe(load_tool_health()), use_container_width=True)


def main() -> None:
    """Dashboard 入口。"""
    settings = get_settings()
    st.title("ToolHub Console")
    st.caption(f"{settings.app_name} dashboard")

    with st.sidebar:
        st.header("筛选")
        recent_limit = st.slider("最近任务数量", 5, 100, 20, step=5)
        if st.button("刷新"):
            st.cache_data.clear()
            st.rerun()

    recent_tasks = load_recent_tasks(recent_limit)
    tabs = st.tabs(["Overview", "Trace", "Task", "Routing", "Replay", "Raw Tables"])
    with tabs[0]:
        render_overview(recent_limit)
    with tabs[1]:
        render_trace_console(recent_tasks)
    with tabs[2]:
        render_task_console(recent_tasks)
    with tabs[3]:
        render_routing_debug()
    with tabs[4]:
        render_replay_console()
    with tabs[5]:
        render_raw_tables()


if __name__ == "__main__":
    main()
