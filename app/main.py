from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from redis import Redis

from app.api.approvals import router as approvals_router
from app.api.harness import router as harness_router
from app.api.intent import router as intent_router
from app.api.openapi_import import router as openapi_import_router
from app.api.permissions import router as permissions_router
from app.api.routing import router as routing_router
from app.api.tasks import router as tasks_router
from app.api.tool_calls import router as tool_calls_router
from app.api.tools import router as tools_router
from app.api.traces import router as traces_router
from app.common.config import configure_logging, get_settings, validate_settings
from app.common.exceptions import ToolHubError
from app.repositories.db import get_connection

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging()
    validate_settings()
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
    """兼容旧调用的轻量存活检查。"""
    return {"status": "OK"}


@app.get("/health/live", tags=["system"])
def health_live() -> dict[str, str]:
    """容器存活检查，只验证进程仍可响应 HTTP。"""
    return {"status": "OK"}


@app.get("/health/ready", tags=["system"], response_model=None)
def health_ready() -> dict[str, object] | JSONResponse:
    """就绪检查，验证关键依赖是否可用。"""
    checks = {
        "database": _check_database(),
        "redis": _check_redis(),
    }
    status = "OK" if all(item["ok"] for item in checks.values()) else "ERROR"
    payload = {"status": status, "checks": checks}
    if status != "OK":
        return JSONResponse(status_code=503, content=payload)
    return payload


def _check_database() -> dict[str, object]:
    """检查数据库连接。"""
    try:
        with get_connection() as connection:
            connection.execute("SELECT 1")
        return {"ok": True}
    except Exception as exc:
        return {"ok": False, "error": f"{exc.__class__.__name__}: {exc}"}


def _check_redis() -> dict[str, object]:
    """检查 Redis 连接。"""
    try:
        client = Redis.from_url(get_settings().redis_url, socket_connect_timeout=2)
        client.ping()
        client.close()
        return {"ok": True}
    except Exception as exc:
        return {"ok": False, "error": f"{exc.__class__.__name__}: {exc}"}


app.include_router(tools_router)
app.include_router(intent_router)
app.include_router(openapi_import_router)
app.include_router(routing_router)
app.include_router(permissions_router)
app.include_router(approvals_router)
app.include_router(harness_router)
app.include_router(tool_calls_router)
app.include_router(tasks_router)
app.include_router(traces_router)
