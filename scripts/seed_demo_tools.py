from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.common.exceptions import ConflictError
from app.repositories.db import init_db
from app.schemas.tool import RiskLevel, ToolRegisterRequest, ToolType
from app.services.tool_registry_service import ToolRegistryService


DEMO_TOOLS: list[dict[str, Any]] = [
    {
        "name": "toolhub-demo-mcp-calculator",
        "description": "Demo MCP tool: evaluate simple arithmetic expressions through the current MCP adapter demo path.",
        "tool_type": ToolType.MCP,
        "endpoint": "calculator",
        "mcp_url": "mock://calculator",
        "transport": "mock",
        "version": "1.0.0",
        "tags": ["demo", "mcp", "calculator", "math"],
        "risk_level": RiskLevel.LOW,
        "input_schema": {
            "type": "object",
            "properties": {
                "expression": {
                    "type": "string",
                    "description": "Arithmetic expression using numbers and operators.",
                    "examples": ["1 + 2 * 3"],
                }
            },
            "required": ["expression"],
            "additionalProperties": False,
        },
        "output_schema": {
            "type": "object",
            "properties": {
                "expression": {"type": "string"},
                "result": {"type": ["number", "integer"]},
            },
            "required": ["expression", "result"],
        },
    },
    {
        "name": "toolhub-demo-http-echo",
        "description": "Demo HTTP tool: local mock echo endpoint handled by HTTPToolAdapter without network access.",
        "tool_type": ToolType.HTTP,
        "endpoint": "mock://echo",
        "version": "1.0.0",
        "tags": ["demo", "http", "echo", "mock"],
        "risk_level": RiskLevel.LOW,
        "input_schema": {
            "type": "object",
            "properties": {
                "method": {"type": "string", "enum": ["GET", "POST"]},
                "params": {"type": "object"},
                "json": {"type": "object"},
            },
            "additionalProperties": True,
        },
        "output_schema": {
            "type": "object",
            "properties": {"echo": {"type": "object"}},
            "required": ["echo"],
        },
    },
    {
        "name": "toolhub-demo-http-public-api",
        "description": "Demo HTTP tool: call a public HTTPS echo API through SSRF-protected HTTPToolAdapter.",
        "tool_type": ToolType.HTTP,
        "endpoint": "https://httpbin.org/anything",
        "version": "1.0.0",
        "tags": ["demo", "http", "public-api", "httpbin"],
        "risk_level": RiskLevel.LOW,
        "input_schema": {
            "type": "object",
            "properties": {
                "method": {"type": "string", "enum": ["GET", "POST"]},
                "params": {"type": "object"},
                "headers": {"type": "object"},
                "json": {"type": "object"},
                "timeout": {"type": "number", "minimum": 0.1, "maximum": 10},
            },
            "additionalProperties": False,
        },
        "output_schema": {
            "type": "object",
            "properties": {
                "status_code": {"type": "integer"},
                "final_url": {"type": "string"},
                "headers": {"type": "object"},
                "body": {},
                "truncated": {"type": "boolean"},
            },
            "required": ["status_code", "final_url", "body", "truncated"],
        },
    },
    {
        "name": "toolhub-demo-cli-git-status",
        "description": "Demo CLI tool: inspect workspace git status through DockerSandbox using the safe git status rule.",
        "tool_type": ToolType.CLI,
        "endpoint": "cli://git/status-short",
        "version": "1.0.0",
        "tags": ["demo", "cli", "git", "status"],
        "risk_level": RiskLevel.MEDIUM,
        "input_schema": {
            "type": "object",
            "properties": {
                "rule_id": {"type": "string", "const": "cli://git/status-short"},
                "args": {"type": "object", "additionalProperties": False},
            },
            "additionalProperties": False,
        },
        "output_schema": {
            "type": "object",
            "properties": {
                "rule_id": {"type": "string"},
                "command": {"type": "string"},
                "argv": {"type": "array", "items": {"type": "string"}},
                "stdout": {"type": "string"},
                "stderr": {"type": "string"},
                "exit_code": {"type": "integer"},
                "sandbox_status": {"type": "string"},
            },
            "required": ["rule_id", "stdout", "stderr", "exit_code", "sandbox_status"],
        },
    },
    {
        "name": "toolhub-demo-cli-git-diff",
        "description": "Demo CLI tool: inspect workspace git diff through DockerSandbox using the safe git diff rule.",
        "tool_type": ToolType.CLI,
        "endpoint": "cli://git/diff",
        "version": "1.0.0",
        "tags": ["demo", "cli", "git", "diff"],
        "risk_level": RiskLevel.MEDIUM,
        "input_schema": {
            "type": "object",
            "properties": {
                "rule_id": {"type": "string", "const": "cli://git/diff"},
                "args": {
                    "type": "object",
                    "properties": {
                        "staged": {"type": "boolean"},
                        "path": {"type": "string"},
                    },
                    "additionalProperties": False,
                },
            },
            "additionalProperties": False,
        },
        "output_schema": {
            "type": "object",
            "properties": {
                "rule_id": {"type": "string"},
                "command": {"type": "string"},
                "argv": {"type": "array", "items": {"type": "string"}},
                "stdout": {"type": "string"},
                "stderr": {"type": "string"},
                "exit_code": {"type": "integer"},
                "sandbox_status": {"type": "string"},
            },
            "required": ["rule_id", "stdout", "stderr", "exit_code", "sandbox_status"],
        },
    },
    {
        "name": "toolhub-demo-python-sandbox",
        "description": "Demo Sandbox tool: execute short Python code in DockerSandbox with network disabled.",
        "tool_type": ToolType.SANDBOX,
        "endpoint": "python",
        "version": "1.0.0",
        "tags": ["demo", "sandbox", "python", "code-runner"],
        "risk_level": RiskLevel.HIGH,
        "input_schema": {
            "type": "object",
            "properties": {
                "language": {"type": "string", "const": "python"},
                "code": {
                    "type": "string",
                    "description": "Python code passed to python -c inside DockerSandbox.",
                    "examples": ["print(sum(range(10)))"],
                },
                "timeout": {"type": "integer", "minimum": 1, "maximum": 10},
            },
            "required": ["code"],
            "additionalProperties": False,
        },
        "output_schema": {
            "type": "object",
            "properties": {
                "language": {"type": "string"},
                "stdout": {"type": "string"},
                "stderr": {"type": "string"},
                "exit_code": {"type": "integer"},
                "sandbox_status": {"type": "string"},
                "container_id": {"type": ["string", "null"]},
            },
            "required": ["language", "stdout", "stderr", "exit_code", "sandbox_status"],
        },
    },
]


def seed_demo_tools() -> list[dict[str, str]]:
    init_db()
    service = ToolRegistryService()
    results: list[dict[str, str]] = []

    for tool_data in DEMO_TOOLS:
        request = ToolRegisterRequest(**tool_data)
        existing = _find_existing_tool(service, request.name)
        if existing is not None:
            if existing.status.value != "ACTIVE":
                existing = service.enable_tool(existing.id)
            results.append(
                {
                    "name": existing.name,
                    "tool_type": existing.tool_type.value,
                    "id": str(existing.id),
                    "status": "reused",
                }
            )
            continue

        try:
            created = service.register_tool(request)
            results.append(
                {
                    "name": created.name,
                    "tool_type": created.tool_type.value,
                    "id": str(created.id),
                    "status": "created",
                }
            )
        except ConflictError:
            existing = _find_existing_tool(service, request.name)
            if existing is None:
                raise
            results.append(
                {
                    "name": existing.name,
                    "tool_type": existing.tool_type.value,
                    "id": str(existing.id),
                    "status": "reused_after_conflict",
                }
            )

    return results


def _find_existing_tool(service: ToolRegistryService, name: str):
    for tool in service.search_tools(name, include_disabled=True):
        if tool.name == name:
            return tool
    return None


def main() -> None:
    results = seed_demo_tools()
    print(json.dumps({"items": results, "total": len(results)}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
