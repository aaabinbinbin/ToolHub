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

