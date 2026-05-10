#!/usr/bin/env python3
"""运行工具路由评估并生成 Markdown 报告。"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from app.repositories.db import init_db
from app.services.tool_router_service import ToolRouterService

EVAL_CASES_PATH = PROJECT_ROOT / "evals" / "tool_routing_cases.jsonl"
REPORT_PATH = PROJECT_ROOT / "evals" / "routing_eval_report.md"


def load_cases() -> list[dict]:
    cases = []
    with EVAL_CASES_PATH.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                cases.append(json.loads(line))
    return cases


def evaluate(cases: list[dict], top_k: int = 5) -> dict:
    router = ToolRouterService()
    total = len(cases)
    top1_correct = 0
    top3_correct = 0
    schema_reject_ok = 0
    schema_reject_total = 0
    dangerous_avoided = 0
    dangerous_total = 0
    no_tool_expected = 0
    no_tool_correct = 0
    details = []

    for case in cases:
        route = router.select_tool(
            user_input=case["user_input"],
            intent=case.get("intent"),
            suggested_tool_type=case.get("suggested_tool_type"),
            tool_input=case.get("tool_input") or {},
            top_k=top_k,
        )
        expected_type = case.get("expected_tool_type")
        expected_name = case.get("expected_tool_name_contains")
        case_risk = case.get("risk", "low")
        selected = route.selected_tool

        # top-1
        if expected_type is None:
            top1_ok = selected is None
            no_tool_expected += 1
            if top1_ok:
                no_tool_correct += 1
        else:
            top1_ok = (
                selected is not None
                and selected.tool_type.value == expected_type
                and (expected_name is None or expected_name in selected.name)
            )
        top1_correct += int(top1_ok)

        # top-3
        top3 = route.candidates[: min(3, len(route.candidates))]
        if expected_type is None:
            top3_ok = selected is None
        else:
            top3_ok = any(
                c.tool_type.value == expected_type
                and (expected_name is None or expected_name in c.name)
                for c in top3
            )
        top3_correct += int(top3_ok)

        # schema reject
        if route.schema_match is False:
            schema_reject_total += 1
            if route.selected_tool is None:
                schema_reject_ok += 1

        # dangerous avoidance: 只计 expected_type 为 null 的危险输入（应返回 NO_TOOL）
        if case_risk == "dangerous" and expected_type is None:
            dangerous_total += 1
            if selected is None:
                dangerous_avoided += 1

        details.append({
            "user_input": case["user_input"],
            "expected_type": expected_type,
            "selected": selected.name if selected else None,
            "selected_type": selected.tool_type.value if selected else None,
            "top1_ok": top1_ok,
            "top3_ok": top3_ok,
            "schema_match": route.schema_match,
            "risk": case_risk,
            "dangerous_avoided": (case_risk == "dangerous" and selected is None),
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
        "no_tool_precision": (
            round(no_tool_correct / no_tool_expected, 4)
            if no_tool_expected else None
        ),
        "dangerous_total": dangerous_total,
        "dangerous_avoided": dangerous_avoided,
        "no_tool_expected": no_tool_expected,
        "no_tool_correct": no_tool_correct,
        "details": details,
    }


def render_report(report: dict) -> str:
    lines = [
        "# ToolHub 工具路由评估报告",
        "",
        f"**评估时间**：{datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}",
        f"**评估样例数**：{report['total']}",
        f"**Top-K**：5",
        "",
        "## 核心指标",
        "",
        "| 指标 | 值 | 说明 |",
        "|---|---|---|",
        f"| top1_accuracy | {report['top1_accuracy']:.2%} | 首选工具命中率 |",
        f"| top3_recall | {report['top3_recall']:.2%} | 前 3 候选召回率 |",
        f"| schema_reject_accuracy | {report['schema_reject_accuracy']:.2%}" if report['schema_reject_accuracy'] is not None else "| schema_reject_accuracy | N/A | 无 schema 不匹配样例 |",
        f"| dangerous_tool_avoidance_rate | {report['dangerous_tool_avoidance_rate']:.2%} | 危险输入被正确拦截率 |",
        f"| no_tool_precision | {report['no_tool_precision']:.2%}" if report['no_tool_precision'] is not None else "| no_tool_precision | N/A | 无 NO_TOOL 样例 |",
        "",
        "## 样例分类统计",
        "",
        f"- 危险输入样例：{report['dangerous_total']}，成功拦截：{report['dangerous_avoided']}",
        f"- 期望 NO_TOOL 样例：{report['no_tool_expected']}，正确返回 NO_TOOL：{report['no_tool_correct']}",
        "",
        "## 逐样例详情",
        "",
        "| # | 输入 | 期望类型 | 选中工具 | top1 | top3 | schema | 危险拦截 |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for i, d in enumerate(report["details"], 1):
        lines.append(
            f"| {i} | {d['user_input'][:30]} | {d['expected_type'] or 'NO_TOOL'} | "
            f"{d['selected'] or '—'} | {'✓' if d['top1_ok'] else '✗'} | "
            f"{'✓' if d['top3_ok'] else '✗'} | "
            f"{'✓' if d['schema_match'] else '✗'} | "
            f"{'✓' if d.get('dangerous_avoided') else ('—' if d['risk'] != 'dangerous' else '✗')} |"
        )
    lines += [
        "",
        "## 指标说明",
        "",
        "- **top1_accuracy**：ToolRouter 首选工具是否符合评估期望",
        "- **top3_recall**：前 3 个候选工具是否包含期望工具",
        "- **schema_reject_accuracy**：schema 不匹配时是否正确拒绝执行",
        "- **dangerous_tool_avoidance_rate**：危险/恶意输入是否被正确拦截（未匹配到工具）",
        "- **no_tool_precision**：应返回空工具的查询中准确返回空的比例",
        "",
        "## 当前边界",
        "",
        "- 评估基于确定性规则路由 + 可选 LLM rerank",
        "- pgvector / embedding 语义召回尚未作为强依赖接入",
        "- 样例覆盖 MCP / HTTP / CLI / SANDBOX / GENERAL_QUERY / 恶意输入 六类场景",
    ]
    return "\n".join(lines)


def main() -> None:
    print("初始化数据库...")
    init_db()
    print(f"加载评估样例: {EVAL_CASES_PATH}")
    cases = load_cases()
    print(f"共 {len(cases)} 条样例，开始评估...")
    report = evaluate(cases)
    md = render_report(report)
    REPORT_PATH.write_text(md, encoding="utf-8")
    print(f"报告已写入: {REPORT_PATH}")
    print(f"\ntop1_accuracy: {report['top1_accuracy']:.2%}")
    print(f"top3_recall: {report['top3_recall']:.2%}")
    if report["schema_reject_accuracy"] is not None:
        print(f"schema_reject_accuracy: {report['schema_reject_accuracy']:.2%}")
    print(f"dangerous_tool_avoidance_rate: {report['dangerous_tool_avoidance_rate']:.2%}")


if __name__ == "__main__":
    main()
