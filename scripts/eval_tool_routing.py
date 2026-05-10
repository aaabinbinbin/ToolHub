from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.repositories.db import init_db
from app.services.tool_router_service import ToolRouterService


def load_cases(path: Path) -> list[dict[str, Any]]:
    """读取 JSONL 路由评估样例。"""
    cases: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as file:
        for line in file:
            line = line.strip()
            if line:
                cases.append(json.loads(line))
    return cases


def evaluate(cases: list[dict[str, Any]], *, top_k: int) -> dict[str, Any]:
    """计算 top1_accuracy / top3_recall / schema_reject_accuracy / dangerous_tool_avoidance_rate。"""
    router = ToolRouterService()
    total = len(cases)
    top1_correct = 0
    top3_correct = 0
    schema_reject_ok = 0
    schema_reject_total = 0
    dangerous_avoided = 0
    dangerous_total = 0
    details: list[dict[str, Any]] = []

    for case in cases:
        route = router.select_tool(
            user_input=case["user_input"],
            intent=case.get("intent"),
            suggested_tool_type=case.get("suggested_tool_type"),
            tool_input=case.get("tool_input") or {},
            top_k=top_k,
        )
        expected_type = case.get("expected_tool_type")
        expected_name_contains = case.get("expected_tool_name_contains")
        case_risk = case.get("risk", "low")
        selected = route.selected_tool

        # top-1 accuracy: 首选工具是否符合预期
        top1_ok = _matches(selected, expected_type, expected_name_contains)
        if expected_type is None:
            top1_ok = selected is None
        top1_correct += int(top1_ok)

        # top-3 recall: 前 3 个候选是否包含预期工具
        top3_candidates = route.candidates[:min(3, len(route.candidates))]
        top3_ok = any(
            _matches(c, expected_type, expected_name_contains)
            for c in top3_candidates
        )
        if expected_type is None:
            top3_ok = selected is None
        top3_correct += int(top3_ok)

        # schema_reject_accuracy: schema 不匹配的工具是否被正确拒绝
        if route.selected_tool is None and route.schema_match is False:
            schema_reject_ok += 1
            schema_reject_total += 1
        elif route.schema_match is False:
            schema_reject_total += 1

        # dangerous_tool_avoidance_rate: 危险输入是否未匹配到工具
        if case_risk == "dangerous":
            dangerous_total += 1
            if selected is None:
                dangerous_avoided += 1

        details.append({
            "user_input": case["user_input"],
            "expected_tool_type": expected_type,
            "selected_tool": selected.name if selected else None,
            "selected_tool_type": selected.tool_type.value if selected else None,
            "top1_ok": top1_ok,
            "top3_ok": top3_ok,
            "schema_match": route.schema_match,
            "missing_fields": route.missing_fields,
            "rejection_reason": route.rejection_reason,
            "case_risk": case_risk,
            "reason": route.reason,
        })

    return {
        "total": total,
        "top1_accuracy": round(top1_correct / total, 4) if total else 0,
        "top3_recall": round(top3_correct / total, 4) if total else 0,
        "schema_reject_accuracy": (
            round(schema_reject_ok / schema_reject_total, 4)
            if schema_reject_total else None
        ),
        "dangerous_tool_avoidance_rate": (
            round(dangerous_avoided / dangerous_total, 4)
            if dangerous_total else None
        ),
        "dangerous_cases": dangerous_total,
        "dangerous_avoided": dangerous_avoided,
        "details": details,
    }


def _matches(
    candidate: Any,
    expected_type: str | None,
    expected_name_contains: str | None,
) -> bool:
    """判断候选工具是否符合评估期望。"""
    if expected_type is None:
        return candidate is None
    if candidate is None:
        return False
    if candidate.tool_type.value != expected_type:
        return False
    if expected_name_contains and expected_name_contains not in candidate.name:
        return False
    return True


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate ToolHub tool routing.")
    parser.add_argument(
        "--cases",
        default="evals/tool_routing_cases.jsonl",
        help="JSONL eval case file.",
    )
    parser.add_argument("--top-k", type=int, default=5)
    args = parser.parse_args()

    init_db()
    report = evaluate(load_cases(Path(args.cases)), top_k=args.top_k)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
