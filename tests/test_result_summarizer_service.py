from __future__ import annotations

from uuid import uuid4

from app.llm.result_summarizer_service import ResultSummarizerService


class BrokenLLMClient:
    def complete_json(self, *args, **kwargs):
        raise RuntimeError("boom")


def test_summarizer_falls_back_when_llm_raises() -> None:
    summary = ResultSummarizerService(llm_client=BrokenLLMClient()).summarize(
        user_input="test",
        status="SUCCESS",
        intent=None,
        route=None,
        permission={"allowed": True},
        tool_input={},
        tool_result={"success": True, "output": {"stdout": "ok"}},
        task_id=uuid4(),
        run_id=uuid4(),
        trace_id=uuid4(),
    )

    assert summary.summary_type == "SUCCESS"
    assert summary.fallback_used is True
    assert "RuntimeError" in (summary.raw_response or "")


def test_summarizer_denied_fallback_message() -> None:
    summary = ResultSummarizerService(llm_client=BrokenLLMClient()).summarize(
        user_input="run python",
        status="DENIED",
        intent=None,
        route=None,
        permission={"allowed": False, "reason": "HIGH risk"},
        tool_input={},
        tool_result=None,
        task_id=uuid4(),
        run_id=uuid4(),
        trace_id=uuid4(),
    )

    assert summary.summary_type == "DENIED"
    assert "HIGH risk" in summary.final_answer


def test_summarizer_waiting_approval_fallback_message() -> None:
    summary = ResultSummarizerService(llm_client=BrokenLLMClient()).summarize(
        user_input="run python",
        status="WAITING_APPROVAL",
        intent=None,
        route=None,
        permission={
            "allowed": False,
            "decision": "ASK",
            "reason": "HIGH risk needs approval",
            "approval_id": "approval-1",
        },
        tool_input={},
        tool_result=None,
        task_id=uuid4(),
        run_id=uuid4(),
        trace_id=uuid4(),
    )

    assert summary.summary_type == "WAITING_APPROVAL"
    assert "等待人工审批" in summary.final_answer
    assert "approval-1" in (summary.next_action or "")


def test_summarizer_planned_fallback_message() -> None:
    summary = ResultSummarizerService(llm_client=BrokenLLMClient()).summarize(
        user_input="plan only",
        status="PLANNED",
        intent=None,
        route=None,
        permission=None,
        tool_input={},
        tool_result={
            "success": True,
            "status": "PLANNED",
            "output": {"steps": [{"objective": "查看 Git 状态"}]},
        },
        task_id=uuid4(),
        run_id=uuid4(),
        trace_id=uuid4(),
    )

    assert summary.summary_type == "PLANNED"
    assert "不会执行工具" in summary.final_answer
