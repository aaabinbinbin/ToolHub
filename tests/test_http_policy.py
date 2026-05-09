from __future__ import annotations

import pytest

from app.security.http_policy import HTTPPolicy


def test_http_policy_blocks_local_and_metadata_urls() -> None:
    policy = HTTPPolicy((80, 443))

    for url in (
        "http://127.0.0.1",
        "http://localhost",
        "http://169.254.169.254/latest/meta-data/",
    ):
        with pytest.raises(ValueError):
            policy.validate_url(url)


def test_http_policy_rejects_sensitive_request_headers() -> None:
    policy = HTTPPolicy((80, 443))

    with pytest.raises(ValueError):
        policy.sanitize_request_headers({"Cookie": "sid=secret"})


def test_http_policy_redacts_sensitive_response_headers() -> None:
    policy = HTTPPolicy((80, 443))

    redacted = policy.redact_response_headers(
        {"Set-Cookie": "sid=secret", "X-Test": "ok"}
    )

    assert redacted["Set-Cookie"] == "***REDACTED***"
    assert redacted["X-Test"] == "ok"

