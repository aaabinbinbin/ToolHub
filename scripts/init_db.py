from __future__ import annotations

import sys
from pathlib import Path

# 允许直接执行 `python scripts/init_db.py`。
# Python 默认只会把 scripts 目录加入 sys.path，这里主动补上项目根目录，
# 这样脚本才能稳定导入 app 包。
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.common.config import configure_logging
from app.repositories.db import init_db


def main() -> None:
    # 初始化日志配置后执行建库建表；具体 SQL 统一维护在 Repository 层。
    configure_logging()
    database_url = init_db()
    print(f"PostgreSQL database initialized: {database_url}")


if __name__ == "__main__":
    main()
