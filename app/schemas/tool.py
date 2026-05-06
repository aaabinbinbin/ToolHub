from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

# 工具类型
class ToolType(StrEnum):
    # ToolHub MVP 支持的四类工具。这里的枚举值需要和数据库 CHECK 约束保持一致。
    MCP = "MCP"
    HTTP = "HTTP"
    CLI = "CLI"
    SANDBOX = "SANDBOX"

# 风险等级
class RiskLevel(StrEnum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"

# 工具状态
class ToolStatus(StrEnum):
    ACTIVE = "ACTIVE"
    DISABLED = "DISABLED"
    DELETED = "DELETED"

# 健康状态
class HealthStatus(StrEnum):
    UNKNOWN = "UNKNOWN"
    UP = "UP"
    DOWN = "DOWN"


class ToolRegisterRequest(BaseModel):
    # 注册请求只描述工具元数据，不在这里执行健康检查或真实调用。
    name: str = Field(min_length=1, max_length=120) # 工具名称，1-120 字符
    description: str = Field(min_length=1) # 工具描述
    tool_type: ToolType # 工具类型枚举
    endpoint: str | None = None # HTTP/CLI/SANDBOX 工具必需
    mcp_url: str | None = None # MCP 工具必需
    transport: str | None = None # 传输协议（可选）
    version: str = Field(default="1.0.0", min_length=1) # 版本号，默认 "1.0.0"
    input_schema: dict[str, Any] | None = None # 输入参数 JSON Schema
    output_schema: dict[str, Any] | None = None # 输出结果 JSON Schema
    tags: list[str] = Field(default_factory=list) # 标签列表，默认为空
    risk_level: RiskLevel = RiskLevel.LOW # 风险等级，默认 LOW

    # 使用 Pydantic v2 的 model_validator 进行跨字段验证
    @model_validator(mode="after")
    def validate_tool_location(self) -> "ToolRegisterRequest":
        # 不同工具类型的入口字段不同：MCP 使用 mcp_url，其余类型先统一使用 endpoint。
        if self.tool_type == ToolType.MCP and not self.mcp_url:
            raise ValueError("mcp_url is required for MCP tools")
        if self.tool_type in {ToolType.HTTP, ToolType.CLI, ToolType.SANDBOX} and not self.endpoint:
            raise ValueError("endpoint is required for HTTP, CLI and SANDBOX tools")
        return self


class ToolResponse(BaseModel):
    # Repository 返回 dict，Pydantic 在这里统一转换为 API 响应结构和枚举类型。
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    description: str
    tool_type: ToolType
    endpoint: str | None
    mcp_url: str | None
    transport: str | None
    version: str
    input_schema: dict[str, Any] | None
    output_schema: dict[str, Any] | None
    tags: list[str]
    risk_level: RiskLevel
    status: ToolStatus
    health_status: HealthStatus
    last_checked_at: datetime | None # 最后健康检查时间
    created_at: datetime
    updated_at: datetime


class ToolSearchResponse(BaseModel):
    items: list[ToolResponse] # 工具列表
    total: int # 工具总数
