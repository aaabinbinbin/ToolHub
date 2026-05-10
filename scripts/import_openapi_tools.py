from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.repositories.db import init_db
from app.schemas.openapi_import import OpenAPIImportRequest
from app.services.openapi_import_service import OpenAPIImportService


def main() -> None:
    parser = argparse.ArgumentParser(description="Import HTTP tools from an OpenAPI JSON file.")
    parser.add_argument("spec", help="Path to OpenAPI JSON file")
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--name-prefix", default="openapi")
    parser.add_argument("--owner-id", default="local-user")
    parser.add_argument("--workspace-id", default="default")
    args = parser.parse_args()

    init_db()
    spec = json.loads(Path(args.spec).read_text(encoding="utf-8"))
    items = OpenAPIImportService().import_spec(
        OpenAPIImportRequest(
            spec=spec,
            base_url=args.base_url,
            name_prefix=args.name_prefix,
            owner_id=args.owner_id,
            workspace_id=args.workspace_id,
        )
    )
    print(json.dumps({"total": len(items), "items": [item.model_dump(mode="json") for item in items]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
