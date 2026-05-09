from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends

from app.schemas.approval import (
    ApprovalDecisionRequest,
    ApprovalDecisionResponse,
    ApprovalRequestResponse,
)
from app.services.approval_service import ApprovalService

router = APIRouter(prefix="/api/approvals", tags=["approvals"])


def get_approval_service() -> ApprovalService:
    """创建 ApprovalService 依赖。"""
    return ApprovalService()


@router.get("/pending", response_model=list[ApprovalRequestResponse])
def list_pending_approvals(
    service: ApprovalService = Depends(get_approval_service),
) -> list[ApprovalRequestResponse]:
    """查询所有待审批请求。"""
    return service.list_pending()


@router.post("/{approval_id}/approve", response_model=ApprovalDecisionResponse)
def approve_request(
    approval_id: UUID,
    request: ApprovalDecisionRequest,
    service: ApprovalService = Depends(get_approval_service),
) -> ApprovalDecisionResponse:
    """审批通过，并将任务重新入队。"""
    return service.approve(
        approval_id,
        decided_by=request.decided_by,
        decision_reason=request.decision_reason,
    )


@router.post("/{approval_id}/reject", response_model=ApprovalDecisionResponse)
def reject_request(
    approval_id: UUID,
    request: ApprovalDecisionRequest,
    service: ApprovalService = Depends(get_approval_service),
) -> ApprovalDecisionResponse:
    """审批拒绝，并将任务标记为 DENIED。"""
    return service.reject(
        approval_id,
        decided_by=request.decided_by,
        decision_reason=request.decision_reason,
    )
