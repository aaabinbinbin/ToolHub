from __future__ import annotations

from app.schemas.tool import ToolRegisterRequest, ToolType
from scripts.seed_demo_tools import DEMO_TOOLS


def test_demo_tool_seed_contains_all_tool_types() -> None:
    tool_types = {ToolType(tool["tool_type"]) for tool in DEMO_TOOLS}

    assert tool_types == {
        ToolType.MCP,
        ToolType.HTTP,
        ToolType.CLI,
        ToolType.SANDBOX,
    }


def test_demo_tool_seed_definitions_are_valid() -> None:
    requests = [ToolRegisterRequest(**tool) for tool in DEMO_TOOLS]

    assert len(requests) >= 4
    assert all(request.name.startswith("toolhub-demo-") for request in requests)
    assert all(request.input_schema for request in requests)
    assert all(request.output_schema for request in requests)
