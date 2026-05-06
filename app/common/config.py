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
    database_url: str = "postgresql://postgres:postgres@localhost:5432/toolhub"
    redis_url: str = "redis://localhost:6379/0"
    llm_provider: str = "openai_compatible"
    llm_base_url: str = "https://api.example.com/v1"
    llm_api_key: str = "your_api_key"
    llm_model: str = "your-model-name"


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
    )


def configure_logging() -> None:
    settings = get_settings()
    logging.basicConfig(
        level=settings.log_level,
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    )
