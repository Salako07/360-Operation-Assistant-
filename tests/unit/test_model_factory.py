"""Unit tests for hosted chat-model configuration and construction."""

import pytest

from operations_agent.config import ModelProvider, ModelSettings, load_model_settings
from operations_agent.services import model_factory


class StubChatModel:
    """Captures factory arguments without making a network call."""

    def __init__(self, **kwargs: object) -> None:
        self.kwargs = kwargs


def test_create_chat_model_returns_configured_gemini_model(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The factory constructs ChatGoogleGenerativeAI with google_api_key when provider=gemini."""
    monkeypatch.setattr(model_factory, "ChatGoogleGenerativeAI", StubChatModel)
    settings = ModelSettings(
        provider=ModelProvider.GEMINI,
        model_name="gemini-1.5-flash",
        api_key="test-gemini-key",
        temperature=0.0,
    )

    model = model_factory.create_chat_model(settings)

    assert isinstance(model, StubChatModel)
    assert model.kwargs == {
        "model": "gemini-1.5-flash",
        "google_api_key": "test-gemini-key",
        "temperature": 0.0,
    }


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


def test_load_model_settings_uses_gemini_environment_variables(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """GEMINI_API_KEY and GEMINI_MODEL are prioritized when LLM_PROVIDER=gemini."""
    monkeypatch.setenv("LLM_PROVIDER", "gemini")
    monkeypatch.setenv("GEMINI_API_KEY", "ai-secret-gemini-key")
    monkeypatch.setenv("GEMINI_MODEL", "gemini-1.5-pro")
    monkeypatch.setenv("LLM_TEMPERATURE", "0.0")

    settings = load_model_settings()

    assert settings.provider is ModelProvider.GEMINI
    assert settings.model_name == "gemini-1.5-pro"
    assert settings.api_key == "ai-secret-gemini-key"
    assert settings.temperature == 0.0


def test_load_model_settings_auto_detects_gemini_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When GEMINI_API_KEY is present without LLM_PROVIDER, defaults to gemini provider."""
    monkeypatch.delenv("LLM_PROVIDER", raising=False)
    monkeypatch.setenv("GEMINI_API_KEY", "auto-detected-key")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    settings = load_model_settings()

    assert settings.provider is ModelProvider.GEMINI
    assert settings.api_key == "auto-detected-key"


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


def test_load_model_settings_requires_credentials_for_gemini(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Missing Gemini API key raises a clear configuration error."""
    monkeypatch.setenv("LLM_PROVIDER", "gemini")
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("LLM_API_KEY", raising=False)

    with pytest.raises(ValueError, match="GEMINI_API_KEY"):
        load_model_settings()


def test_load_model_settings_requires_credentials_for_openai(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Missing OpenAI API key raises a clear configuration error."""
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    with pytest.raises(ValueError, match="LLM_API_KEY"):
        load_model_settings()


def test_load_model_settings_rejects_invalid_provider(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Unsupported provider strings raise a clear configuration error."""
    monkeypatch.setenv("LLM_PROVIDER", "unsupported_provider")

    with pytest.raises(ValueError, match="LLM_PROVIDER must be one of"):
        load_model_settings()


def test_load_model_settings_rejects_invalid_temperature(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Non-numeric temperature raises a clear configuration error."""
    monkeypatch.setenv("LLM_PROVIDER", "gemini")
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setenv("LLM_TEMPERATURE", "not-a-number")

    with pytest.raises(ValueError, match="LLM_TEMPERATURE"):
        load_model_settings()


def test_gemini_model_tool_binding_preserves_langchain_tools(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The Gemini model abstraction supports standard LangChain bind_tools."""
    from operations_agent.tools.registry import get_langchain_tools

    class StubGeminiWithTools(StubChatModel):
        def bind_tools(self, tools: list[object]) -> "StubGeminiWithTools":
            self.tools = tools
            return self

    monkeypatch.setattr(model_factory, "ChatGoogleGenerativeAI", StubGeminiWithTools)
    settings = ModelSettings(
        provider=ModelProvider.GEMINI,
        model_name="gemini-1.5-flash",
        api_key="test-key",
    )

    model = model_factory.create_chat_model(settings)
    bound_model = model.bind_tools(get_langchain_tools())  # type: ignore[attr-defined]

    assert hasattr(bound_model, "tools")
    tool_names = [tool.name for tool in bound_model.tools]
    assert "get_customer" in tool_names
    assert "get_transactions" in tool_names
    assert "get_support_tickets" in tool_names
    assert "search_knowledge_base" in tool_names
