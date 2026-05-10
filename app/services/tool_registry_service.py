from __future__ import annotations

from uuid import UUID

from app.common.exceptions import NotFoundError
from app.repositories.db import get_connection
from app.repositories.tool_repository import ToolRepository
from app.repositories.tool_version_repository import ToolVersionRepository
from app.schemas.tool import ToolRegisterRequest, ToolResponse


class ToolRegistryService:
    # Service 层负责业务语义：开启事务、调用 Repository、把空结果转换成领域错误。
    def register_tool(self, request: ToolRegisterRequest) -> ToolResponse:
        with get_connection() as connection:
            tool = ToolRepository(connection).create(request)
            ToolVersionRepository(connection).create_snapshot(tool)
            return ToolResponse.model_validate(tool)

    def get_tool(self, tool_id: UUID) -> ToolResponse:
        with get_connection() as connection:
            tool = ToolRepository(connection).get_by_id(tool_id)
            if tool is None:
                raise NotFoundError(f"Tool not found: {tool_id}")
            return ToolResponse.model_validate(tool)

    def search_tools(
        self, query: str, include_disabled: bool = False
    ) -> list[ToolResponse]:
        # include_disabled 主要用于管理后台；Agent 路由默认应该只看 ACTIVE 工具。
        with get_connection() as connection:
            tools = ToolRepository(connection).search(query, include_disabled)
            return [ToolResponse.model_validate(tool) for tool in tools]

    def enable_tool(self, tool_id: UUID) -> ToolResponse:
        return self._set_status(tool_id, enabled=True)

    def disable_tool(self, tool_id: UUID) -> ToolResponse:
        return self._set_status(tool_id, enabled=False)

    def delete_tool(self, tool_id: UUID) -> None:
        with get_connection() as connection:
            tool = ToolRepository(connection).delete(tool_id)
            if tool is None:
                raise NotFoundError(f"Tool not found: {tool_id}")

    def _set_status(self, tool_id: UUID, enabled: bool) -> ToolResponse:
        # 对 API 来说 enable/disable 是两个动作；对数据库来说只是 status 字段变化。
        with get_connection() as connection:
            repository = ToolRepository(connection)
            tool = repository.enable(tool_id) if enabled else repository.disable(tool_id)
            if tool is None:
                raise NotFoundError(f"Tool not found: {tool_id}")
            return ToolResponse.model_validate(tool)
