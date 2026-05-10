from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch
from uuid import uuid4

from app.schemas.routing import ToolRouteCandidateDetail
from app.schemas.tool import HealthStatus, RiskLevel, ToolResponse, ToolStatus, ToolType
from app.services.tool_rerank_service import ToolRerankService


def make_tool(name: str, tool_type: ToolType, risk: RiskLevel = RiskLevel.LOW) -> ToolResponse:
    now = datetime.now(timezone.utc)
    return ToolResponse(
        id=uuid4(),
        name=name,
        description=f"描述: {name}",
        tool_type=tool_type,
        endpoint="mock://echo",
        mcp_url=None,
        transport=None,
        version="1.0.0",
        input_schema=None,
        output_schema=None,
        tags=["demo"],
        risk_level=risk,
        status=ToolStatus.ACTIVE,
        health_status=HealthStatus.UP,
        last_checked_at=None,
        created_at=now,
        updated_at=now,
    )


def candidate(tool: ToolResponse, score: float = 5.0) -> ToolRouteCandidateDetail:
    return ToolRouteCandidateDetail(
        tool=tool,
        score=score,
        score_breakdown={"keyword": score},
        matched_signals=["tool_name"],
        schema_match=True,
        schema_score=0,
        rank=None,
    )


def test_rerank_empty_candidates_returns_fallback() -> None:
    """空候选列表应返回 fallback。"""
    service = ToolRerankService()
    result = service.rerank(
        user_input="test",
        intent=None,
        suggested_tool_type=None,
        tool_input={},
        candidates=[],
        task_id=uuid4(),
        run_id=uuid4(),
        trace_id=uuid4(),
    )
    assert result.enabled is True
    assert result.applied is False
    assert result.fallback_used is True


def test_rerank_without_task_id_returns_fallback() -> None:
    """没有 task_id 时不应调用 LLM。"""
    service = ToolRerankService()
    tool = make_tool("test-http", ToolType.HTTP)
    result = service.rerank(
        user_input="test",
        intent=None,
        suggested_tool_type=None,
        tool_input={},
        candidates=[candidate(tool)],
        task_id=None,
        run_id=None,
        trace_id=None,
    )
    assert result.fallback_used is True


def test_rerank_applies_llm_ranking() -> None:
    """LLM 排序结果应正确回写到候选详情。"""
    tool_a = make_tool("tool-a", ToolType.HTTP)
    tool_b = make_tool("tool-b", ToolType.MCP)
    candidates_list = [candidate(tool_a, 3.0), candidate(tool_b, 5.0)]

    mock_result = MagicMock()
    mock_result.text = '{"ranked_tool_ids": ["' + str(tool_b.id) + '", "' + str(tool_a.id) + '"], "reasons": {}, "reason": "ok"}'

    mock_llm = MagicMock()
    mock_llm.complete_json.return_value = (mock_result, {
        "ranked_tool_ids": [str(tool_b.id), str(tool_a.id)],
        "reasons": {},
        "reason": "ok",
    })

    service = ToolRerankService(llm_client=mock_llm)
    result = service.rerank(
        user_input="test",
        intent=None,
        suggested_tool_type=None,
        tool_input={},
        candidates=candidates_list,
        task_id=uuid4(),
        run_id=uuid4(),
        trace_id=uuid4(),
    )

    assert result.enabled is True
    assert result.applied is True
    # tool_b 被 LLM 排第一，应获得更高加分
    assert candidates_list[1].llm_rerank_rank == 1  # tool_b
    assert candidates_list[0].llm_rerank_rank == 2  # tool_a


def test_rerank_never_overrides_schema_validation() -> None:
    """LLM rerank 不能覆盖 schema_match=false 的结果。"""
    tool = make_tool("bad-tool", ToolType.HTTP)
    bad_candidate = ToolRouteCandidateDetail(
        tool=tool,
        score=10.0,
        score_breakdown={"keyword": 10.0},
        matched_signals=[],
        schema_match=False,
        schema_score=-100,
        missing_fields=["required_field"],
        rejection_reason="缺少字段",
    )

    mock_result = MagicMock()
    mock_result.text = '{"ranked_tool_ids": ["' + str(tool.id) + '"], "reasons": {}, "reason": "test"}'

    mock_llm = MagicMock()
    mock_llm.complete_json.return_value = (mock_result, {
        "ranked_tool_ids": [str(tool.id)],
        "reasons": {},
        "reason": "test",
    })

    service = ToolRerankService(llm_client=mock_llm)
    service.rerank(
        user_input="test",
        intent=None,
        suggested_tool_type=None,
        tool_input={},
        candidates=[bad_candidate],
        task_id=uuid4(),
        run_id=uuid4(),
        trace_id=uuid4(),
    )

    # schema_match=false 的候选不应被 rerank
    assert bad_candidate.llm_rerank_rank is None
