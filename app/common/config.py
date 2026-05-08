from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    app_name: str = "ToolHub"
    app_env: str = "dev"
    host: str = "127.0.0.1"
    port: int = 8000
    log_level: str = "INFO"
    database_url: str = "postgresql://postgres:postgres@localhost:15432/toolhub"
    redis_url: str = "redis://localhost:6379/0"
    llm_provider: str = "openai_compatible"
    llm_base_url: str = "https://api.example.com/v1"
    llm_api_key: str = "your_api_key"
    llm_model: str = "your-model-name"
    llm_timeout_seconds: float = 30
    llm_max_retries: int = 2
    sandbox_python_image: str = "python:3.12-alpine"
    sandbox_cli_image: str = "alpine/git:latest"
    sandbox_mem_limit: str = "128m"
    sandbox_pids_limit: int = 64
    sandbox_timeout_seconds: int = 10
    sandbox_network_disabled: bool = True
    http_timeout_seconds: float = 10
    http_max_retries: int = 2
    http_max_redirects: int = 3
    http_max_response_bytes: int = 1024 * 1024
    http_allowed_ports: tuple[int, ...] = (80, 443)


def load_env_file(path: Path = Path(".env")) -> None:
    if not path.exists():
        return

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        # 系统环境变量优先；.env 只补充缺失项，避免覆盖部署环境配置。
        os.environ.setdefault(key.strip(), value.strip().strip("\"'"))


@lru_cache
def get_settings() -> Settings:
    load_env_file()
    return Settings(
        app_name=os.getenv("APP_NAME", Settings.app_name),
        app_env=os.getenv("APP_ENV", Settings.app_env),
        host=os.getenv("HOST", Settings.host),
        port=int(os.getenv("PORT", Settings.port)),
        log_level=os.getenv("LOG_LEVEL", Settings.log_level).upper(),
        database_url=os.getenv("DATABASE_URL", Settings.database_url),
        redis_url=os.getenv("REDIS_URL", Settings.redis_url),
        llm_provider=os.getenv("LLM_PROVIDER", Settings.llm_provider),
        llm_base_url=os.getenv("LLM_BASE_URL", Settings.llm_base_url),
        llm_api_key=os.getenv("LLM_API_KEY", Settings.llm_api_key),
        llm_model=os.getenv("LLM_MODEL", Settings.llm_model),
        llm_timeout_seconds=float(
            os.getenv("LLM_TIMEOUT_SECONDS", Settings.llm_timeout_seconds)
        ),
        llm_max_retries=int(os.getenv("LLM_MAX_RETRIES", Settings.llm_max_retries)),
        sandbox_python_image=os.getenv(
            "SANDBOX_PYTHON_IMAGE", Settings.sandbox_python_image
        ),
        sandbox_cli_image=os.getenv("SANDBOX_CLI_IMAGE", Settings.sandbox_cli_image),
        sandbox_mem_limit=os.getenv("SANDBOX_MEM_LIMIT", Settings.sandbox_mem_limit),
        sandbox_pids_limit=int(
            os.getenv("SANDBOX_PIDS_LIMIT", Settings.sandbox_pids_limit)
        ),
        sandbox_timeout_seconds=int(
            os.getenv("SANDBOX_TIMEOUT_SECONDS", Settings.sandbox_timeout_seconds)
        ),
        sandbox_network_disabled=os.getenv(
            "SANDBOX_NETWORK_DISABLED",
            str(Settings.sandbox_network_disabled),
        ).lower()
        in {"1", "true", "yes", "on"},
        http_timeout_seconds=float(
            os.getenv("HTTP_TIMEOUT_SECONDS", Settings.http_timeout_seconds)
        ),
        http_max_retries=int(os.getenv("HTTP_MAX_RETRIES", Settings.http_max_retries)),
        http_max_redirects=int(
            os.getenv("HTTP_MAX_REDIRECTS", Settings.http_max_redirects)
        ),
        http_max_response_bytes=int(
            os.getenv("HTTP_MAX_RESPONSE_BYTES", Settings.http_max_response_bytes)
        ),
        http_allowed_ports=tuple(
            int(port.strip())
            for port in os.getenv("HTTP_ALLOWED_PORTS", "80,443").split(",")
            if port.strip()
        ),
    )


def configure_logging() -> None:
    settings = get_settings()
    logging.basicConfig(
        level=settings.log_level,
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    )
