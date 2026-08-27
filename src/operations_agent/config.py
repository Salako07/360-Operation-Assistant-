"""Configuration models and environment loading for the application."""

import os
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class ModelProvider(StrEnum):
    """Hosted model API protocols supported by the initial model factory."""

    OPENAI = "openai"
    OPENAI_COMPATIBLE = "openai_compatible"


class ModelSettings(BaseModel):
    """Validated settings required to create the application's chat model."""

    model_config = ConfigDict(frozen=True)

    provider: ModelProvider
    model_name: str = Field(min_length=1)
    api_key: str = Field(min_length=1)
    base_url: str | None = None
    temperature: float = Field(default=0, ge=0, le=2)


class ApiSettings(BaseModel):
    """Non-secret runtime configuration for the synchronous API."""

    model_config = ConfigDict(frozen=True)

    log_level: str = "INFO"
    cors_origins: tuple[str, ...] = ("http://localhost:3000", "http://127.0.0.1:3000")


def load_api_settings() -> ApiSettings:
    """Load API settings from environment variables."""
    log_level = os.getenv("API_LOG_LEVEL", "INFO").upper()
    if log_level not in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}:
        raise ValueError("API_LOG_LEVEL must be a standard Python logging level.")
    origins = tuple(
        origin.strip()
        for origin in os.getenv("API_CORS_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000").split(",")
        if origin.strip()
    )
    return ApiSettings(log_level=log_level, cors_origins=origins)


def load_model_settings() -> ModelSettings:
    """Load hosted-model settings from environment variables.

    `LLM_API_KEY` is preferred so one deployment contract works with multiple
    providers. `OPENAI_API_KEY` remains supported for local OpenAI compatibility.
    """
    provider_value = os.getenv("LLM_PROVIDER", ModelProvider.OPENAI.value)
    try:
        provider = ModelProvider(provider_value)
    except ValueError as error:
        supported = ", ".join(member.value for member in ModelProvider)
        raise ValueError(f"LLM_PROVIDER must be one of: {supported}.") from error

    api_key = os.getenv("LLM_API_KEY") or os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise ValueError("Set LLM_API_KEY or OPENAI_API_KEY before creating a chat model.")

    base_url = os.getenv("LLM_BASE_URL")
    if provider is ModelProvider.OPENAI_COMPATIBLE and not base_url:
        raise ValueError("LLM_BASE_URL is required when LLM_PROVIDER=openai_compatible.")

    temperature_value = os.getenv("LLM_TEMPERATURE", "0")
    try:
        temperature = float(temperature_value)
    except ValueError as error:
        raise ValueError("LLM_TEMPERATURE must be a number between 0 and 2.") from error

    return ModelSettings(
        provider=provider,
        model_name=os.getenv("LLM_MODEL", "gpt-4.1-mini"),
        api_key=api_key,
        base_url=base_url,
        temperature=temperature,
    )
