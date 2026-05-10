from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from app.schemas.tool import ToolResponse


class OpenAPIImportRequest(BaseModel):
    """OpenAPI 导入请求。"""

    spec: dict[str, Any] = Field(default_factory=dict)
    base_url: str
    name_prefix: str = "openapi"
    owner_id: str = "local-user"
    workspace_id: str = "default"
    tag: str = "openapi"


class OpenAPIImportResponse(BaseModel):
    """OpenAPI 导入结果。"""

    items: list[ToolResponse]
    total: int
