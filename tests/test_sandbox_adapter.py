from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from app.schemas.sandbox import SandboxRunResult
from app.schemas.tool import HealthStatus, RiskLevel, ToolResponse, ToolStatus, ToolType
from app.tools.adapters.sandbox_adapter import SandboxToolAdapter


class FakeSandbox:
    def __init__(self) -> None:
        self.last_request = None

    def run_once(self, request):
        self.last_request = request
        return SandboxRunResult(
            command=" ".join(request.command),
            stdout="ok",
            stderr="",
            exit_code=0,
            duration_ms=1,
            timeout_seconds=request.timeout_seconds,
            container_id="container-1",
            status="SUCCESS",
            language=request.language,
            artifacts=[{"path": "out.txt", "status": "DECLARED"}],
        )


def test_sandbox_adapter_supports_node_runtime() -> None:
    now = datetime.now(timezone.utc)
    adapter = SandboxToolAdapter()
    fake_sandbox = FakeSandbox()
    adapter.sandbox = fake_sandbox
    tool = ToolResponse(
        id=uuid4(),
        name="node-sandbox",
        description="node sandbox",
        tool_type=ToolType.SANDBOX,
        endpoint="node",
        mcp_url=None,
        transport=None,
        version="1.0.0",
        input_schema=None,
        output_schema=None,
        tags=[],
        risk_level=RiskLevel.HIGH,
        status=ToolStatus.ACTIVE,
        health_status=HealthStatus.UNKNOWN,
        last_checked_at=None,
        created_at=now,
        updated_at=now,
    )

    output = adapter.call(
        tool,
        {"language": "node", "code": "console.log(1)", "artifact_paths": ["out.txt"]},
    )

    assert fake_sandbox.last_request.command == ["node", "-e", "console.log(1)"]
    assert output["language"] == "node"
    assert output["artifacts"] == [{"path": "out.txt", "status": "DECLARED"}]
