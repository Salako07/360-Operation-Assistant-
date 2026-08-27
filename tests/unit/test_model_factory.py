"""Unit tests for hosted chat-model configuration and construction."""

import pytest

from operations_agent.config import ModelProvider, ModelSettings, load_model_settings
from operations_agent.services import model_factory


class StubChatModel:
    """Captures factory arguments without making a network call."""

    def __init__(self, **kwargs: object) -> None:
        self.kwargs = kwargs


def test_create_chat_model_returns_configured_openai_model(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The factory converts settings into one provider-specific construction point."""
    monkeypatch.setattr(model_factory, "ChatOpenAI", StubChatModel)
    settings = ModelSettings(
        provider=ModelProvider.OPENAI,
        model_name="gpt-4.1-mini",
        api_key="test-key",
        temperature=0.2,
    )

    model = model_factory.create_chat_model(settings)

    assert isinstance(model, StubChatModel)
    assert model.kwargs == {
        "model": "gpt-4.1-mini",
        "api_key": "test-key",
        "temperature": 0.2,
    }


def test_create_chat_model_passes_custom_base_url_for_openai_compatible_provider(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A future vLLM endpoint uses the same abstract factory interface."""
    monkeypatch.setattr(model_factory, "ChatOpenAI", StubChatModel)
    settings = ModelSettings(
        provider=ModelProvider.OPENAI_COMPATIBLE,
        model_name="meta-llama/Meta-Llama-3.1-8B-Instruct",
        api_key="local-token",
        base_url="http://localhost:8000/v1",
    )

    model = model_factory.create_chat_model(settings)

    assert isinstance(model, StubChatModel)
    assert model.kwargs["base_url"] == "http://localhost:8000/v1"
    assert model.kwargs["model"] == "meta-llama/Meta-Llama-3.1-8B-Instruct"


def test_load_model_settings_uses_generic_environment_variables(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Generic LLM settings support changing providers without code changes."""
    monkeypatch.setenv("LLM_PROVIDER", "openai_compatible")
    monkeypatch.setenv("LLM_MODEL", "custom-model")
    monkeypatch.setenv("LLM_API_KEY", "configured-key")
    monkeypatch.setenv("LLM_BASE_URL", "https://models.example/v1")
    monkeypatch.setenv("LLM_TEMPERATURE", "0.4")

    settings = load_model_settings()

    assert settings.provider is ModelProvider.OPENAI_COMPATIBLE
    assert settings.model_name == "custom-model"
    assert settings.api_key == "configured-key"
    assert settings.base_url == "https://models.example/v1"
    assert settings.temperature == 0.4


def test_load_model_settings_requires_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    """The factory never falls back to a hard-coded credential."""
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    with pytest.raises(ValueError, match="LLM_API_KEY"):
        load_model_settings()
