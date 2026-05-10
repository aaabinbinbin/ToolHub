from __future__ import annotations

import re
from typing import Any

from app.common.exceptions import ConflictError
from app.schemas.openapi_import import OpenAPIImportRequest
from app.schemas.tool import RiskLevel, ToolRegisterRequest, ToolResponse, ToolType
from app.services.tool_registry_service import ToolRegistryService


class OpenAPIImportService:
    """把 OpenAPI operation 导入为 HTTP 工具。"""

    HTTP_METHODS = {"get", "post", "put", "patch", "delete"}

    def __init__(self, tool_registry_service: ToolRegistryService | None = None) -> None:
        self.tool_registry_service = tool_registry_service or ToolRegistryService()

    def import_spec(self, request: OpenAPIImportRequest) -> list[ToolResponse]:
        """导入 OpenAPI spec 中的所有 operation。"""
        tools: list[ToolResponse] = []
        for tool_request in self._build_tool_requests(request):
            try:
                tools.append(self.tool_registry_service.register_tool(tool_request))
            except ConflictError:
                existing = self._find_existing(tool_request.name)
                if existing is not None:
                    tools.append(existing)
        return tools

    def _build_tool_requests(
        self, request: OpenAPIImportRequest
    ) -> list[ToolRegisterRequest]:
        paths = request.spec.get("paths") or {}
        if not isinstance(paths, dict):
            raise ValueError("OpenAPI spec paths must be an object")

        tools: list[ToolRegisterRequest] = []
        for path, path_item in paths.items():
            if not isinstance(path_item, dict):
                continue
            for method, operation in path_item.items():
                if method.lower() not in self.HTTP_METHODS or not isinstance(operation, dict):
                    continue
                tools.append(self._operation_to_tool(request, str(path), method, operation))
        return tools

    def _operation_to_tool(
        self,
        request: OpenAPIImportRequest,
        path: str,
        method: str,
        operation: dict[str, Any],
    ) -> ToolRegisterRequest:
        operation_id = operation.get("operationId") or f"{method}_{path}"
        name = self._safe_name(f"{request.name_prefix}-{operation_id}")
        endpoint = request.base_url.rstrip("/") + "/" + path.lstrip("/")
        input_schema = self._input_schema(method, path, operation)
        metadata = {
            "source": "openapi",
            "operation_id": operation_id,
            "method": method.upper(),
            "path": path,
            "summary": operation.get("summary"),
        }
        return ToolRegisterRequest(
            name=name,
            description=operation.get("summary")
            or operation.get("description")
            or f"{method.upper()} {path}",
            tool_type=ToolType.HTTP,
            endpoint=endpoint,
            version=str(operation.get("x-toolhub-version") or "1.0.0"),
            input_schema=input_schema,
            output_schema=None,
            metadata=metadata,
            owner_id=request.owner_id,
            workspace_id=request.workspace_id,
            tags=[request.tag, "http", "openapi", method.lower()],
            risk_level=RiskLevel.LOW,
        )

    def _input_schema(
        self,
        method: str,
        path: str,
        operation: dict[str, Any],
    ) -> dict[str, Any]:
        properties: dict[str, Any] = {
            "method": {"type": "string", "const": method.upper()},
            "params": {"type": "object", "properties": {}, "additionalProperties": True},
        }
        required = ["method"]

        query_props: dict[str, Any] = {}
        path_props: dict[str, Any] = {}
        for parameter in operation.get("parameters") or []:
            if not isinstance(parameter, dict):
                continue
            schema = parameter.get("schema") or {"type": "string"}
            location = parameter.get("in")
            name = str(parameter.get("name") or "")
            if not name:
                continue
            if location == "query":
                query_props[name] = schema
            elif location == "path":
                path_props[name] = schema
                required.append("path_params")

        if query_props:
            properties["params"] = {
                "type": "object",
                "properties": query_props,
                "additionalProperties": False,
            }
        if path_props or "{" in path:
            properties["path_params"] = {
                "type": "object",
                "properties": path_props,
                "additionalProperties": False,
            }
        request_body = operation.get("requestBody") or {}
        content = request_body.get("content") if isinstance(request_body, dict) else {}
        json_content = (content or {}).get("application/json") if isinstance(content, dict) else None
        if isinstance(json_content, dict):
            properties["json"] = json_content.get("schema") or {"type": "object"}

        return {
            "type": "object",
            "required": sorted(set(required)),
            "properties": properties,
            "additionalProperties": False,
        }

    def _safe_name(self, value: str) -> str:
        text = re.sub(r"[^a-zA-Z0-9_.-]+", "-", value).strip("-").lower()
        return text[:120] or "openapi-tool"

    def _find_existing(self, name: str) -> ToolResponse | None:
        for tool in self.tool_registry_service.search_tools(name, include_disabled=True):
            if tool.name == name:
                return tool
        return None
