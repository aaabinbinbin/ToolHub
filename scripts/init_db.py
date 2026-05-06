from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.common.config import configure_logging
from app.repositories.db import init_db


def main() -> None:
    configure_logging()
    database_url = init_db()
    print(f"PostgreSQL database initialized: {database_url}")


if __name__ == "__main__":
    main()
