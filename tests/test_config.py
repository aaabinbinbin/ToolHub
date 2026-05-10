from __future__ import annotations

import pytest

from app.common.config import get_settings, validate_settings


@pytest.fixture(autouse=True)
def clear_settings_cache():
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_llm_mock_enabled_is_explicit(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_MOCK_ENABLED", "true")
    get_settings.cache_clear()

    assert get_settings().llm_mock_enabled is True


def test_validate_settings_requires_real_llm_config_when_mock_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LLM_MOCK_ENABLED", "false")
    monkeypatch.setenv("LLM_API_KEY", "your_api_key")
    monkeypatch.setenv("LLM_BASE_URL", "https://api.example.com/v1")
    monkeypatch.setenv("LLM_MODEL", "your-model-name")
    get_settings.cache_clear()

    with pytest.raises(ValueError, match="LLM_API_KEY"):
        validate_settings()


def test_validate_settings_accepts_real_llm_config_when_mock_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LLM_MOCK_ENABLED", "false")
    monkeypatch.setenv("LLM_API_KEY", "real-key")
    monkeypatch.setenv("LLM_BASE_URL", "https://llm.example.test/v1")
    monkeypatch.setenv("LLM_MODEL", "real-model")
    get_settings.cache_clear()

    validate_settings()
