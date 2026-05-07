from __future__ import annotations

from fastapi import APIRouter, Depends

from app.schemas.routing import HarnessPlanRequest, HarnessPlanResponse
from app.services.harness_plan_service import HarnessPlanService

router = APIRouter(prefix="/api/harness", tags=["harness"])


def get_harness_plan_service() -> HarnessPlanService:
    """创建 HarnessPlanService 依赖。"""
    return HarnessPlanService()


@router.post("/plan", response_model=HarnessPlanResponse)
def plan_harness_run(
    request: HarnessPlanRequest,
    service: HarnessPlanService = Depends(get_harness_plan_service),
) -> HarnessPlanResponse:
    """预演一次 Harness 执行链路。

    该接口只执行意图理解、工具路由和权限判断，不真正调用工具。
    它会创建 tasks 记录，并把工具路由和权限判断写入 task_events。
    """
    return service.plan(request)
