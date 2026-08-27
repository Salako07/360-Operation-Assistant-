"""Centralized factory for the application's replaceable chat model."""

from langchain_openai import ChatOpenAI

from operations_agent.config import ModelSettings, load_model_settings
from operations_agent.models.chat_model import ChatModel


def create_chat_model(settings: ModelSettings | None = None) -> ChatModel:
    """Create the configured LangChain chat model.

    Both supported providers use the OpenAI-compatible LangChain adapter. Native
    OpenAI uses its standard API endpoint; `openai_compatible` supplies a custom
    base URL, such as a hosted vLLM server. Application code depends only on the
    returned `ChatModel` abstraction, not on `ChatOpenAI`.
    """
    resolved_settings = settings or load_model_settings()
    model_kwargs: dict[str, str | float] = {
        "model": resolved_settings.model_name,
        "api_key": resolved_settings.api_key,
        "temperature": resolved_settings.temperature,
    }
    if resolved_settings.base_url:
        model_kwargs["base_url"] = resolved_settings.base_url

    return ChatOpenAI(**model_kwargs)
