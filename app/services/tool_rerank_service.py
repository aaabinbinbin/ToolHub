from __future__ import annotations

import json
from typing import Any
from uuid import UUID

from app.llm.llm_client import LLMClient
from app.schemas.routing import ToolRouteCandidateDetail, ToolRouteRerankMetadata


class ToolRerankService:
    """让 LLM 对 top-k 候选工具给出排序建议，最终选择仍由系统校验。"""

    def __init__(self, llm_client: LLMClient | None = None) -> None:
        self.llm_client = llm_client or LLMClient()

    def rerank(
        self,
        *,
        user_input: str,
        intent: str | None,
        suggested_tool_type: str | None,
        tool_input: dict[str, Any],
        candidates: list[ToolRouteCandidateDetail],
        task_id: UUID | None,
        run_id: UUID | None,
        trace_id: UUID | None,
    ) -> ToolRouteRerankMetadata:
        """调用 LLM rerank，并把排序结果回写到候选详情。"""
        if not candidates:
            return ToolRouteRerankMetadata(
                enabled=True,
                applied=False,
                fallback_used=True,
                reason="没有候选工具可重排。",
            )
        if task_id is None or run_id is None or trace_id is None:
            return ToolRouteRerankMetadata(
                enabled=True,
                applied=False,
                fallback_used=True,
                reason="缺少 task_id/run_id/trace_id，跳过需要审计落库的 LLM rerank。",
            )

        prompt = self._build_prompt(
            user_input=user_input,
            intent=intent,
            suggested_tool_type=suggested_tool_type,
            tool_input=tool_input,
            candidates=candidates,
        )
        try:
            result, parsed = self.llm_client.complete_json(
                prompt,
                node_name="tool_rerank",
                task_id=task_id,
                run_id=run_id,
                trace_id=trace_id,
                system_message=self._system_message(),
            )
        except Exception as exc:
            return ToolRouteRerankMetadata(
                enabled=True,
                applied=False,
                fallback_used=True,
                reason=f"LLM rerank 调用失败：{exc.__class__.__name__}: {exc}",
            )

        if not isinstance(parsed, dict):
            return ToolRouteRerankMetadata(
                enabled=True,
                applied=False,
                fallback_used=True,
                reason="LLM rerank 未返回合法 JSON 对象。",
                raw_response=result.text,
            )

        ranked_ids = parsed.get("ranked_tool_ids")
        reasons = parsed.get("reasons") or {}
        if not isinstance(ranked_ids, list):
            return ToolRouteRerankMetadata(
                enabled=True,
                applied=False,
                fallback_used=True,
                reason="LLM rerank 结果缺少 ranked_tool_ids。",
                raw_response=result.text,
            )

        candidate_by_id = {str(item.tool.id): item for item in candidates}
        applied = False
        for index, tool_id in enumerate(ranked_ids):
            candidate = candidate_by_id.get(str(tool_id))
            if candidate is None or not candidate.schema_match:
                continue
            candidate.llm_rerank_rank = index + 1
            candidate.llm_rerank_reason = str(reasons.get(str(tool_id)) or "").strip() or None
            # rerank 只是加权建议，不覆盖 schema、权限和确定性分数。
            candidate.score += max(0, len(candidates) - index) * 0.5
            candidate.score_breakdown["llm_rerank"] = max(0, len(candidates) - index) * 0.5
            applied = True

        return ToolRouteRerankMetadata(
            enabled=True,
            applied=applied,
            fallback_used=not applied,
            reason=str(parsed.get("reason") or "LLM rerank 已应用。"),
            raw_response=result.text,
        )

    def _system_message(self) -> str:
        """构造 rerank 的 system message。"""
        return (
            "你是 ToolHub 的工具候选 reranker。你只能在系统给出的候选工具中排序，"
            "不能新增工具，不能忽略 schema_match=false 的候选，不能替代 PermissionEngine。"
            "只返回严格 JSON。"
        )

    def _build_prompt(
        self,
        *,
        user_input: str,
        intent: str | None,
        suggested_tool_type: str | None,
        tool_input: dict[str, Any],
        candidates: list[ToolRouteCandidateDetail],
    ) -> str:
        """构造候选工具重排 prompt。"""
        payload = {
            "user_input": user_input,
            "intent": intent,
            "suggested_tool_type": suggested_tool_type,
            "tool_input": tool_input,
            "candidates": [
                {
                    "tool_id": str(item.tool.id),
                    "name": item.tool.name,
                    "description": item.tool.description,
                    "tool_type": item.tool.tool_type.value,
                    "tags": item.tool.tags,
                    "risk_level": item.tool.risk_level.value,
                    "schema_match": item.schema_match,
                    "score": item.score,
                    "score_breakdown": item.score_breakdown,
                    "missing_fields": item.missing_fields,
                    "rejection_reason": item.rejection_reason,
                }
                for item in candidates
            ],
            "output_schema": {
                "ranked_tool_ids": ["只允许候选列表里的 tool_id"],
                "reasons": {"tool_id": "简短排序理由"},
                "reason": "整体排序理由",
            },
            "rules": [
                "不要返回候选列表之外的 tool_id。",
                "schema_match=false 的候选不能排在可执行候选前面。",
                "高风险工具不能因为描述相似就优先，除非任务明确需要该类型工具。",
            ],
        }
        return json.dumps(payload, ensure_ascii=False, indent=2)
