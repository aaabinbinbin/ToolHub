from __future__ import annotations

import sys
from pathlib import Path
from typing import Any
from uuid import UUID

import pandas as pd
import streamlit as st

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.common.config import get_settings
from app.repositories.db import get_connection


st.set_page_config(page_title="ToolHub Dashboard", page_icon="TH", layout="wide")


def run_query(query: str, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    """执行只读查询并返回 dict 列表。"""
    with get_connection() as connection:
        return list(connection.execute(query, params or {}).fetchall())


def to_dataframe(rows: list[dict[str, Any]]) -> pd.DataFrame:
    """把查询结果转换成 DataFrame，空结果也返回可展示对象。"""
    if not rows:
        return pd.DataFrame()
    return pd.DataFrame(rows)


def format_duration(value: Any) -> str:
    if value is None:
        return "-"
    return f"{int(value)} ms"


def load_overview() -> dict[str, Any]:
    rows = run_query(
        """
        SELECT
            count(*) AS total_tasks,
            count(*) FILTER (WHERE status = 'SUCCESS') AS success_tasks,
            count(*) FILTER (WHERE status = 'FAILED') AS failed_tasks,
            count(*) FILTER (WHERE status = 'DENIED') AS denied_tasks,
            count(*) FILTER (WHERE status = 'NO_TOOL') AS no_tool_tasks,
            avg(EXTRACT(EPOCH FROM (finished_at - started_at)) * 1000)
                FILTER (WHERE finished_at IS NOT NULL AND started_at IS NOT NULL)
                AS avg_duration_ms
        FROM tasks
        """
    )
    return rows[0] if rows else {}


def load_recent_tasks(limit: int) -> list[dict[str, Any]]:
    return run_query(
        """
        SELECT
            id, status, current_step, run_mode, priority, selected_tool_id,
            user_input, result -> 'summary' ->> 'final_answer' AS final_answer,
            created_at, started_at, finished_at, updated_at
        FROM tasks
        ORDER BY created_at DESC
        LIMIT %(limit)s
        """,
        {"limit": limit},
    )


def load_task(task_id: UUID) -> dict[str, Any] | None:
    rows = run_query("SELECT * FROM tasks WHERE id = %(task_id)s", {"task_id": task_id})
    return rows[0] if rows else None


def load_task_events(task_id: UUID) -> list[dict[str, Any]]:
    return run_query(
        """
        SELECT event_type, step, message, payload, created_at
        FROM task_events
        WHERE task_id = %(task_id)s
        ORDER BY created_at ASC
        """,
        {"task_id": task_id},
    )


def load_tool_calls(task_id: UUID | None = None, limit: int = 50) -> list[dict[str, Any]]:
    where_clause = "WHERE task_id = %(task_id)s" if task_id else ""
    params: dict[str, Any] = {"limit": limit}
    if task_id:
        params["task_id"] = task_id
    return run_query(
        f"""
        SELECT
            created_at, tool_name, tool_type, status, duration_ms,
            error_message, input, output
        FROM tool_calls
        {where_clause}
        ORDER BY created_at DESC
        LIMIT %(limit)s
        """,
        params,
    )


def load_llm_calls(task_id: UUID | None = None, limit: int = 50) -> list[dict[str, Any]]:
    where_clause = "WHERE task_id = %(task_id)s" if task_id else ""
    params: dict[str, Any] = {"limit": limit}
    if task_id:
        params["task_id"] = task_id
    return run_query(
        f"""
        SELECT
            created_at, node_name, provider, model, status,
            input_tokens, output_tokens, duration_ms, error_message
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
    where_clause = "WHERE task_id = %(task_id)s" if task_id else ""
    params: dict[str, Any] = {"limit": limit}
    if task_id:
        params["task_id"] = task_id
    return run_query(
        f"""
        SELECT
            created_at, tool_name, command, status, exit_code, duration_ms,
            timeout_seconds, container_id, stdout, stderr, error_message
        FROM sandbox_executions
        {where_clause}
        ORDER BY created_at DESC
        LIMIT %(limit)s
        """,
        params,
    )


def load_tool_health() -> list[dict[str, Any]]:
    return run_query(
        """
        SELECT
            t.name, t.tool_type, t.status, t.health_status, t.risk_level,
            t.last_checked_at,
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


def render_overview() -> None:
    overview = load_overview()
    total = int(overview.get("total_tasks") or 0)
    success = int(overview.get("success_tasks") or 0)
    failed = int(overview.get("failed_tasks") or 0)
    denied = int(overview.get("denied_tasks") or 0)
    no_tool = int(overview.get("no_tool_tasks") or 0)
    success_rate = (success / total * 100) if total else 0
    failed_rate = (failed / total * 100) if total else 0

    col1, col2, col3, col4, col5, col6 = st.columns(6)
    col1.metric("任务总数", total)
    col2.metric("成功率", f"{success_rate:.1f}%")
    col3.metric("失败率", f"{failed_rate:.1f}%")
    col4.metric("权限拒绝", denied)
    col5.metric("无工具", no_tool)
    col6.metric("平均耗时", format_duration(overview.get("avg_duration_ms")))


def render_task_detail(task_id_text: str) -> None:
    try:
        task_id = UUID(task_id_text)
    except ValueError:
        st.warning("请选择或输入合法的 task_id。")
        return

    task = load_task(task_id)
    if not task:
        st.warning("未找到任务。")
        return

    st.subheader("任务详情")
    left, right = st.columns([1, 1])
    with left:
        st.json(
            {
                "id": str(task["id"]),
                "status": task["status"],
                "current_step": task["current_step"],
                "run_mode": task["run_mode"],
                "run_id": str(task["run_id"]),
                "trace_id": str(task["trace_id"]),
            }
        )
    with right:
        summary = (task.get("result") or {}).get("summary") if task.get("result") else None
        if summary:
            st.markdown("**最终答案**")
            st.write(summary.get("final_answer"))
            st.caption(f"summary_type={summary.get('summary_type')}")
        else:
            st.info("该任务暂无 summary。")

    tabs = st.tabs(["事件链路", "工具调用", "LLM 调用", "沙箱日志", "原始结果"])
    with tabs[0]:
        st.dataframe(to_dataframe(load_task_events(task_id)), use_container_width=True)
    with tabs[1]:
        st.dataframe(to_dataframe(load_tool_calls(task_id)), use_container_width=True)
    with tabs[2]:
        st.dataframe(to_dataframe(load_llm_calls(task_id)), use_container_width=True)
    with tabs[3]:
        st.dataframe(
            to_dataframe(load_sandbox_executions(task_id)),
            use_container_width=True,
        )
    with tabs[4]:
        st.json(task.get("result") or {})


def main() -> None:
    settings = get_settings()
    st.title("ToolHub Observability Dashboard")
    st.caption(f"Database: {settings.database_url}")

    with st.sidebar:
        st.header("筛选")
        recent_limit = st.slider("最近任务数量", 5, 100, 20, step=5)
        refresh = st.button("刷新")
        if refresh:
            st.cache_data.clear()

    render_overview()
    st.divider()

    st.subheader("最近任务")
    recent_tasks = load_recent_tasks(recent_limit)
    recent_df = to_dataframe(recent_tasks)
    st.dataframe(recent_df, use_container_width=True)

    task_options = [str(row["id"]) for row in recent_tasks]
    selected_task = st.selectbox("选择任务查看完整链路", task_options)
    if selected_task:
        render_task_detail(selected_task)

    st.divider()
    global_tabs = st.tabs(["最近工具调用", "最近 LLM 调用", "最近沙箱执行", "工具健康"])
    with global_tabs[0]:
        st.dataframe(to_dataframe(load_tool_calls()), use_container_width=True)
    with global_tabs[1]:
        st.dataframe(to_dataframe(load_llm_calls()), use_container_width=True)
    with global_tabs[2]:
        st.dataframe(to_dataframe(load_sandbox_executions()), use_container_width=True)
    with global_tabs[3]:
        st.dataframe(to_dataframe(load_tool_health()), use_container_width=True)


if __name__ == "__main__":
    main()
