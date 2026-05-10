from __future__ import annotations

import os
from collections.abc import Mapping
from typing import Any


class SecretReferenceResolver:
    """解析工具输入中的 secret reference。

    当前先支持 `env:NAME`，真实 Secret Vault 可以在不改变调用方接口的情况下
    继续扩展 `secret:NAME`。
    """

    ENV_PREFIX = "env:"
    SECRET_PREFIX = "secret:"

    def resolve(self, value: Any) -> Any:
        """递归解析 dict/list/string 中的 secret reference。"""
        if isinstance(value, str):
            return self._resolve_string(value)
        if isinstance(value, list):
            return [self.resolve(item) for item in value]
        if isinstance(value, Mapping):
            return {str(key): self.resolve(item) for key, item in value.items()}
        return value

    def _resolve_string(self, value: str) -> str:
        if value.startswith(self.ENV_PREFIX):
            env_name = value[len(self.ENV_PREFIX) :].strip()
            if not env_name:
                raise ValueError("env secret reference requires a variable name")
            secret = os.getenv(env_name)
            if secret is None:
                raise ValueError(f"Environment secret is not configured: {env_name}")
            return secret
        if value.startswith(self.SECRET_PREFIX):
            raise ValueError("secret: references require a secret backend, which is not configured")
        return value


class PayloadRedactor:
    """对审计 payload 做统一脱敏。

    Repository 写库前统一调用该类，避免 token、cookie、authorization 等敏感值进入
    task_events、tool_calls、llm_calls 和 approval_requests。
    """

    REDACTED = "***REDACTED***"
    SENSITIVE_KEYS = {
        "api_key",
        "apikey",
        "access_key",
        "access_token",
        "authorization",
        "cookie",
        "password",
        "refresh_token",
        "secret",
        "set-cookie",
        "token",
        "x-api-key",
    }

    def redact(self, value: Any) -> Any:
        """递归脱敏 dict/list/string。"""
        if isinstance(value, Mapping):
            return {
                key: self.REDACTED
                if self._is_sensitive_key(str(key))
                else self.redact(item)
                for key, item in value.items()
            }
        if isinstance(value, list):
            return [self.redact(item) for item in value]
        if isinstance(value, str):
            return self._redact_string(value)
        return value

    def _is_sensitive_key(self, key: str) -> bool:
        normalized = key.strip().lower().replace("_", "-")
        return normalized in self.SENSITIVE_KEYS or any(
            marker in normalized
            for marker in ("password", "secret", "token", "api-key", "authorization")
        )

    def _redact_string(self, value: str) -> str:
        if value.startswith((SecretReferenceResolver.ENV_PREFIX, SecretReferenceResolver.SECRET_PREFIX)):
            return value
        lowered = value.lower()
        if lowered.startswith("bearer ") or lowered.startswith("basic "):
            return self.REDACTED
        return value


redactor = PayloadRedactor()
secret_resolver = SecretReferenceResolver()
