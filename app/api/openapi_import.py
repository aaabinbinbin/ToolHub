from __future__ import annotations

from fastapi import APIRouter, Depends

from app.schemas.openapi_import import OpenAPIImportRequest, OpenAPIImportResponse
from app.services.openapi_import_service import OpenAPIImportService

router = APIRouter(prefix="/api/openapi", tags=["openapi"])


def get_openapi_import_service() -> OpenAPIImportService:
    """创建 OpenAPIImportService 依赖。"""
    return OpenAPIImportService()


@router.post("/import", response_model=OpenAPIImportResponse)
def import_openapi_tools(
    request: OpenAPIImportRequest,
    service: OpenAPIImportService = Depends(get_openapi_import_service),
) -> OpenAPIImportResponse:
    """从 OpenAPI spec 导入 HTTP 工具。"""
    items = service.import_spec(request)
    return OpenAPIImportResponse(items=items, total=len(items))
