from __future__ import annotations

from fastapi import APIRouter, Depends

from app.llm.intent_service import IntentService
from app.schemas.llm import IntentRequest, IntentResult

router = APIRouter(prefix="/api/intent", tags=["intent"])


def get_intent_service() -> IntentService:
    """创建 IntentService 依赖。

    FastAPI 测试时可以通过 `app.dependency_overrides` 替换为 mock service。
    """
    return IntentService()


@router.post("/understand", response_model=IntentResult)
def understand_intent(
    request: IntentRequest,
    service: IntentService = Depends(get_intent_service),
) -> IntentResult:
    """理解用户意图。

    API 层只负责 HTTP 参数接收和响应封装，真正的意图识别逻辑交给 IntentService。
    """
    return service.understand_intent(
        request.user_input,
        run_mode=request.run_mode,
    )
