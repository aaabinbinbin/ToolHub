from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.repositories.db import init_db
from app.schemas.tool import RiskLevel
from app.services.mcp_sync_service import MCPSyncService


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Sync MCP tools into ToolHub.")
    parser.add_argument("--mcp-url", required=True, help="MCP server URL.")
    parser.add_argument(
        "--transport",
        choices=["mock", "stdio", "sse", "streamable-http", "http"],
        default=None,
        help="MCP transport. If omitted, ToolHub infers it from --mcp-url.",
    )
    parser.add_argument(
        "--name-prefix",
        default="mcp",
        help="Prefix used for ToolHub tool names.",
    )
    parser.add_argument(
        "--tag",
        action="append",
        default=[],
        help="Extra tag to attach to synced tools. Can be passed multiple times.",
    )
    parser.add_argument(
        "--risk-level",
        choices=["LOW", "MEDIUM", "HIGH"],
        default="LOW",
        help="Risk level assigned to synced tools.",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=30,
        help="MCP client timeout in seconds.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    init_db()
    results = MCPSyncService().sync_tools(
        mcp_url=args.mcp_url,
        transport=args.transport,
        name_prefix=args.name_prefix,
        tags=args.tag,
        risk_level=RiskLevel(args.risk_level),
        timeout_seconds=args.timeout,
    )
    print(
        json.dumps(
            {
                "items": [result.__dict__ for result in results],
                "total": len(results),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
