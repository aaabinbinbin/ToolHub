from __future__ import annotations

# 通用服务器错误
class ToolHubError(Exception):
    status_code = 500
    message = "Internal server error"

    def __init__(self, message: str | None = None) -> None:
        self.message = message or self.message
        super().__init__(self.message)

# 资源不存在
class NotFoundError(ToolHubError):
    status_code = 404
    message = "Resource not found"

# 资源冲突
class ConflictError(ToolHubError):
    status_code = 409
    message = "Resource already exists"

# 请求参数无效
class ValidationError(ToolHubError):
    status_code = 400
    message = "Invalid request"
