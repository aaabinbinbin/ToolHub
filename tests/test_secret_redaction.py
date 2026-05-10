from __future__ import annotations

import pytest

from app.security.secret_manager import PayloadRedactor, SecretReferenceResolver


def test_secret_resolver_reads_env_reference(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TOOLHUB_TEST_TOKEN", "real-token")

    payload = SecretReferenceResolver().resolve(
        {"headers": {"Authorization": "env:TOOLHUB_TEST_TOKEN"}}
    )

    assert payload["headers"]["Authorization"] == "real-token"


def test_secret_resolver_rejects_missing_env_reference() -> None:
    with pytest.raises(ValueError, match="Environment secret"):
        SecretReferenceResolver().resolve("env:TOOLHUB_MISSING_TOKEN")


def test_payload_redactor_redacts_nested_sensitive_values() -> None:
    payload = {
        "headers": {
            "Authorization": "Bearer abc",
            "X-Api-Key": "secret-value",
            "Content-Type": "application/json",
        },
        "body": {"password": "123456", "name": "toolhub"},
    }

    redacted = PayloadRedactor().redact(payload)

    assert redacted["headers"]["Authorization"] == "***REDACTED***"
    assert redacted["headers"]["X-Api-Key"] == "***REDACTED***"
    assert redacted["headers"]["Content-Type"] == "application/json"
    assert redacted["body"]["password"] == "***REDACTED***"
    assert redacted["body"]["name"] == "toolhub"
