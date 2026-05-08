from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.api.harness import router as harness_router
from app.api.intent import router as intent_router
from app.api.permissions import router as permissions_router
from app.api.routing import router as routing_router
from app.api.tasks import router as tasks_router
from app.api.tool_calls import router as tool_calls_router
from app.api.tools import router as tools_router
from app.common.config import configure_logging, get_settings
from app.common.exceptions import ToolHubError

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging()
    logger.info("ToolHub API started")
    yield


settings = get_settings()
app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    description="Agent Harness & Tool Runtime Platform for CLI/IDE Agents.",
    lifespan=lifespan,
)


@app.exception_handler(ToolHubError)
def handle_toolhub_error(request: Request, exc: ToolHubError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.message},
    )


@app.get("/health", tags=["system"])
def health() -> dict[str, str]:
    return {"status": "OK"}


app.include_router(tools_router)
app.include_router(intent_router)
app.include_router(routing_router)
app.include_router(permissions_router)
app.include_router(harness_router)
app.include_router(tool_calls_router)
app.include_router(tasks_router)
