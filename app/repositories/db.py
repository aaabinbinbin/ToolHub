from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from urllib.parse import urlparse, urlunparse

from alembic import command
from alembic.config import Config
import psycopg
from psycopg import Connection, sql
from psycopg.errors import DuplicateDatabase, InvalidCatalogName
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from app.common.config import get_settings

_connection_pool: ConnectionPool | None = None


def get_database_url() -> str:
    return get_settings().database_url


def get_connection_pool() -> ConnectionPool:
    """获取进程内 PostgreSQL 连接池。

    Repository 层仍然使用短事务；连接池只负责复用底层连接，避免每条事件都重新建立 TCP 连接。
    """
    global _connection_pool
    if _connection_pool is None:
        settings = get_settings()
        _connection_pool = ConnectionPool(
            conninfo=settings.database_url,
            min_size=settings.database_pool_min_size,
            max_size=settings.database_pool_max_size,
            kwargs={"connect_timeout": 5, "row_factory": dict_row},
            open=True,
        )
    return _connection_pool


def close_connection_pool() -> None:
    """关闭当前进程的数据库连接池。"""
    global _connection_pool
    if _connection_pool is not None:
        _connection_pool.close()
        _connection_pool = None


def _maintenance_database_url(database_url: str) -> tuple[str, str]:
    parsed = urlparse(database_url)
    database_name = parsed.path.lstrip("/")
    if not database_name:
        raise ValueError("DATABASE_URL must include a database name")
    maintenance = parsed._replace(path="/postgres")
    return urlunparse(maintenance), database_name


@contextmanager
def get_connection() -> Iterator[Connection]:
    with get_connection_pool().connection() as connection:
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise


def ensure_database_exists() -> None:
    """确保目标 PostgreSQL database 存在。"""
    database_url = get_database_url()
    try:
        with psycopg.connect(database_url, connect_timeout=5):
            return
    except InvalidCatalogName:
        maintenance_url, database_name = _maintenance_database_url(database_url)

    with psycopg.connect(
        maintenance_url, autocommit=True, connect_timeout=5
    ) as connection:
        try:
            connection.execute(
                sql.SQL("CREATE DATABASE {}").format(sql.Identifier(database_name))
            )
        except DuplicateDatabase:
            pass


def _alembic_config() -> Config:
    """创建指向当前工作区 migration 目录的 Alembic 配置。"""
    project_root = Path(__file__).resolve().parents[2]
    config = Config(str(project_root / "alembic.ini"))
    config.set_main_option("script_location", str(project_root / "migrations"))
    config.set_main_option("prepend_sys_path", str(project_root))
    return config


def run_migrations() -> None:
    """执行数据库迁移到最新版本。"""
    command.upgrade(_alembic_config(), "head")


def init_db() -> str:
    """初始化数据库。

    现在主路径使用 Alembic migration 管理 schema 版本，不再在代码里维护大段
    `CREATE TABLE` SQL。这个函数保留给脚本、测试和 demo seed 作为统一入口。
    """
    ensure_database_exists()
    run_migrations()
    return get_database_url()
