from __future__ import annotations

from unittest.mock import MagicMock, patch

from app.infra.docker_sandbox import DockerSandbox
from app.schemas.sandbox import SandboxRunRequest


def make_request(command=None, artifact_paths=None) -> SandboxRunRequest:
    return SandboxRunRequest(
        command=command or ["echo", "hello"],
        image="alpine:latest",
        timeout_seconds=5,
        tool_name="test",
        artifact_paths=artifact_paths or [],
        network_disabled=True,
    )


def test_sandbox_read_only_enabled_by_default() -> None:
    """DockerSandbox create 应默认启用 read_only 根文件系统。"""
    sandbox = DockerSandbox()
    mock_container = MagicMock()
    mock_client = MagicMock()
    mock_client.containers.create.return_value = mock_container
    sandbox.client = mock_client
    sandbox.command_policy.validate = MagicMock()

    request = make_request()
    sandbox.create(request)

    create_kwargs = mock_client.containers.create.call_args.kwargs
    assert create_kwargs.get("read_only") is True


def test_sandbox_no_new_privileges() -> None:
    """DockerSandbox create 应添加 no-new-privileges 安全选项。"""
    sandbox = DockerSandbox()
    mock_container = MagicMock()
    mock_client = MagicMock()
    mock_client.containers.create.return_value = mock_container
    sandbox.client = mock_client
    sandbox.command_policy.validate = MagicMock()

    request = make_request()
    sandbox.create(request)

    create_kwargs = mock_client.containers.create.call_args.kwargs
    security_opt = create_kwargs.get("security_opt") or []
    assert any("no-new-privileges" in opt for opt in security_opt)


def test_sandbox_cap_drop_all() -> None:
    """DockerSandbox create 应 drop ALL capabilities。"""
    sandbox = DockerSandbox()
    mock_container = MagicMock()
    mock_client = MagicMock()
    mock_client.containers.create.return_value = mock_container
    sandbox.client = mock_client
    sandbox.command_policy.validate = MagicMock()

    request = make_request()
    sandbox.create(request)

    create_kwargs = mock_client.containers.create.call_args.kwargs
    cap_drop = create_kwargs.get("cap_drop") or []
    assert "ALL" in cap_drop


def test_sandbox_tmpfs_mount() -> None:
    """DockerSandbox create 应将 /tmp 挂载为 tmpfs。"""
    sandbox = DockerSandbox()
    mock_container = MagicMock()
    mock_client = MagicMock()
    mock_client.containers.create.return_value = mock_container
    sandbox.client = mock_client
    sandbox.command_policy.validate = MagicMock()

    request = make_request()
    sandbox.create(request)

    create_kwargs = mock_client.containers.create.call_args.kwargs
    tmpfs = create_kwargs.get("tmpfs") or {}
    assert "/tmp" in tmpfs
    assert "noexec" in tmpfs["/tmp"]


def test_sandbox_rejects_artifact_path_outside_workspace() -> None:
    """artifact_path 必须在 /workspace/output 内，否则拒绝。"""
    sandbox = DockerSandbox()
    mock_container = MagicMock()
    mock_client = MagicMock()
    mock_client.containers.create.return_value = mock_container
    sandbox.client = mock_client
    sandbox.command_policy.validate = MagicMock()

    request = make_request(artifact_paths=["/etc/passwd"])
    try:
        sandbox.create(request)
        # 如果没抛异常，验证容器未被创建
        mock_client.containers.create.assert_not_called()
    except ValueError as e:
        assert "artifact_path" in str(e)


def test_sandbox_accepts_valid_artifact_path() -> None:
    """合法的 /workspace/output 内 artifact_path 应被接受。"""
    sandbox = DockerSandbox()
    mock_container = MagicMock()
    mock_client = MagicMock()
    mock_client.containers.create.return_value = mock_container
    sandbox.client = mock_client
    sandbox.command_policy.validate = MagicMock()

    request = make_request(artifact_paths=["workspace/output/report.txt"])
    sandbox.create(request)

    mock_client.containers.create.assert_called_once()
