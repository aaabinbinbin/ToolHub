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
    """计算 accuracy、top-k recall 和 no-tool precision。"""
    router = ToolRouterService()
    total = len(cases)
    correct = 0
    top_k_hits = 0
    no_tool_expected = 0
    no_tool_correct = 0
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
        selected = route.selected_tool
        selected_ok = _matches(selected, expected_type, expected_name_contains)
        top_k_ok = any(
            _matches(candidate, expected_type, expected_name_contains)
            for candidate in route.candidates
        )
        if expected_type is None:
            no_tool_expected += 1
            selected_ok = selected is None
            top_k_ok = selected is None
            if selected_ok:
                no_tool_correct += 1

        correct += int(selected_ok)
        top_k_hits += int(top_k_ok)
        details.append(
            {
                "user_input": case["user_input"],
                "expected_tool_type": expected_type,
                "selected_tool": selected.name if selected else None,
                "selected_tool_type": selected.tool_type.value if selected else None,
                "selected_ok": selected_ok,
                "top_k_ok": top_k_ok,
                "reason": route.reason,
            }
        )

    return {
        "total": total,
        "accuracy": correct / total if total else 0,
        "top_k_recall": top_k_hits / total if total else 0,
        "no_tool_precision": (
            no_tool_correct / no_tool_expected if no_tool_expected else None
        ),
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
    parser = argparse.ArgumentParser(description="Evaluate ToolHub tool routing cases.")
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
