from __future__ import annotations

from unittest.mock import MagicMock
from uuid import uuid4

from app.harness.replanner import HarnessReplanner


def test_replanner_llm_success_returns_modified_step() -> None:
    """LLM 成功时返回修正后的 step。"""
    replanner = HarnessReplanner()
    mock_llm = MagicMock()
    mock_result = MagicMock()
    mock_result.text = '{"tool_input": {"code": "print(42)"}, "reason": "修正参数"}'
    mock_llm.complete_json.return_value = (mock_result, {
        "tool_input": {"code": "print(42)"},
        "reason": "修正参数",
    })
    replanner.llm_client = mock_llm

    result = replanner.replan_step(
        user_input="run python code",
        current_step={"tool_input": {"code": "print('bad')"}, "objective": "run code"},
        observation={"error_message": "SyntaxError"},
        retry_count=1,
        max_retries=2,
        task_id=uuid4(),
        run_id=uuid4(),
        trace_id=uuid4(),
    )

    assert result["tool_input"] == {"code": "print(42)"}
    assert replanner.last_fallback_used is False


def test_replanner_llm_failure_falls_back() -> None:
    """LLM 调用失败时返回原始 step。"""
    replanner = HarnessReplanner()
    mock_llm = MagicMock()
    mock_llm.complete_json.side_effect = RuntimeError("LLM unavailable")
    replanner.llm_client = mock_llm

    original_step = {"tool_input": {"code": "print('hello')"}, "objective": "run code"}
    result = replanner.replan_step(
        user_input="run python code",
        current_step=original_step,
        observation={"error_message": "Error"},
        retry_count=1,
        max_retries=2,
        task_id=uuid4(),
        run_id=uuid4(),
        trace_id=uuid4(),
    )

    assert result["tool_input"] == original_step["tool_input"]
    assert replanner.last_fallback_used is True


def test_replanner_json_parse_failure_falls_back() -> None:
    """LLM 返回非 dict JSON 时回退到原始 step。"""
    replanner = HarnessReplanner()
    mock_llm = MagicMock()
    mock_result = MagicMock()
    mock_result.text = '["not", "an", "object"]'
    mock_llm.complete_json.return_value = (mock_result, ["not", "an", "object"])
    replanner.llm_client = mock_llm

    original_step = {"tool_input": {"code": "print('hello')"}, "objective": "run code"}
    result = replanner.replan_step(
        user_input="run python code",
        current_step=original_step,
        observation={"error_message": "Error"},
        retry_count=1,
        max_retries=2,
        task_id=uuid4(),
        run_id=uuid4(),
        trace_id=uuid4(),
    )

    assert result is not None
    assert replanner.last_fallback_used is True


def test_replanner_no_tool_input_falls_back() -> None:
    """LLM 返回缺少 tool_input 时回退。"""
    replanner = HarnessReplanner()
    mock_llm = MagicMock()
    mock_result = MagicMock()
    mock_result.text = '{"reason": "no change"}'
    mock_llm.complete_json.return_value = (mock_result, {"reason": "no change"})
    replanner.llm_client = mock_llm

    original_step = {"tool_input": {"code": "print('hello')"}, "objective": "run code"}
    result = replanner.replan_step(
        user_input="run python code",
        current_step=original_step,
        observation={"error_message": "Error"},
        retry_count=1,
        max_retries=2,
        task_id=uuid4(),
        run_id=uuid4(),
        trace_id=uuid4(),
    )

    assert result is not None
    assert replanner.last_fallback_used is True


def test_replanner_keeps_original_fields() -> None:
    """修正后的 step 应保留原始字段并追加新的元数据。"""
    replanner = HarnessReplanner()
    mock_llm = MagicMock()
    mock_result = MagicMock()
    mock_result.text = '{"tool_input": {"code": "print(99)"}, "reason": "fixed"}'
    mock_llm.complete_json.return_value = (mock_result, {
        "tool_input": {"code": "print(99)"},
        "reason": "fixed",
    })
    replanner.llm_client = mock_llm

    original_step = {
        "tool_input": {"code": "print(broken)"},
        "objective": "run code",
        "suggested_tool_type": "SANDBOX",
    }
    result = replanner.replan_step(
        user_input="run python code",
        current_step=original_step,
        observation={"error_message": "NameError"},
        retry_count=1,
        max_retries=2,
        task_id=uuid4(),
        run_id=uuid4(),
        trace_id=uuid4(),
    )

    assert result["objective"] == "run code"
    assert result["suggested_tool_type"] == "SANDBOX"
    assert result["tool_input"] == {"code": "print(99)"}
    assert "replan_reason" in result
