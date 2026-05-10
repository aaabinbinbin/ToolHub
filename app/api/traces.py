from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends

from app.schemas.trace import TraceResponse
from app.services.trace_service import TraceService

router = APIRouter(prefix="/api/traces", tags=["traces"])


def get_trace_service() -> TraceService:
    """创建 TraceService 依赖。"""
    return TraceService()


@router.get("/{trace_id}", response_model=TraceResponse)
def get_trace(
    trace_id: UUID,
    service: TraceService = Depends(get_trace_service),
) -> TraceResponse:
    """按 trace_id 返回完整 Agent 执行链路。"""
    return service.get_trace(trace_id)
