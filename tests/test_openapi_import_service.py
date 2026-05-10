from __future__ import annotations

from app.schemas.openapi_import import OpenAPIImportRequest
from app.services.openapi_import_service import OpenAPIImportService


def test_openapi_import_builds_http_tool_requests() -> None:
    spec = {
        "openapi": "3.0.0",
        "paths": {
            "/users/{id}": {
                "get": {
                    "operationId": "getUser",
                    "summary": "Get user",
                    "parameters": [
                        {"name": "id", "in": "path", "schema": {"type": "string"}},
                        {"name": "verbose", "in": "query", "schema": {"type": "boolean"}},
                    ],
                }
            },
            "/users": {
                "post": {
                    "operationId": "createUser",
                    "requestBody": {
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "required": ["name"],
                                    "properties": {"name": {"type": "string"}},
                                }
                            }
                        }
                    },
                }
            },
        },
    }

    requests = OpenAPIImportService()._build_tool_requests(
        OpenAPIImportRequest(
            spec=spec,
            base_url="https://api.example.test",
            name_prefix="demo",
            owner_id="owner-a",
            workspace_id="workspace-a",
        )
    )

    assert [request.name for request in requests] == ["demo-getuser", "demo-createuser"]
    assert requests[0].endpoint == "https://api.example.test/users/{id}"
    assert requests[0].input_schema["properties"]["path_params"]["properties"]["id"] == {
        "type": "string"
    }
    assert requests[1].input_schema["properties"]["json"]["required"] == ["name"]
    assert requests[1].owner_id == "owner-a"
    assert requests[1].workspace_id == "workspace-a"
