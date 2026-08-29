import os
from enum import StrEnum
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field


_DOTENV_LOADED = False


def _load_dotenv_if_present() -> None:
    """Load variables from .env file into os.environ if present without overriding existing env."""
    global _DOTENV_LOADED
    if _DOTENV_LOADED or "PYTEST_CURRENT_TEST" in os.environ:
        return
    _DOTENV_LOADED = True
    for path in (Path(".env"), Path(__file__).resolve().parents[2] / ".env"):
        if path.is_file():
            try:
                for line in path.read_text(encoding="utf-8").splitlines():
                    line = line.strip()
                    if not line or line.startswith("#") or "=" not in line:
                        continue
                    key, value = line.split("=", 1)
                    key = key.strip()
                    value = value.strip().strip("'\"")
                    if key and key not in os.environ:
                        os.environ[key] = value
                break
            except Exception:
                pass


class ModelProvider(StrEnum):
    """Hosted model API protocols supported by the model factory."""

    GEMINI = "gemini"
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
    _load_dotenv_if_present()
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

    Supports Gemini, OpenAI, and OpenAI-compatible (vLLM) providers.
    `GEMINI_API_KEY` / `GEMINI_MODEL` are used when configuring Google Gemini.
    `LLM_API_KEY` is supported as a generic provider key across all backends.
    """
    _load_dotenv_if_present()
    default_provider = ModelProvider.GEMINI.value if os.getenv("GEMINI_API_KEY") else ModelProvider.OPENAI.value
    provider_value = os.getenv("LLM_PROVIDER", default_provider).lower()
    try:
        provider = ModelProvider(provider_value)
    except ValueError as error:
        supported = ", ".join(member.value for member in ModelProvider)
        raise ValueError(f"LLM_PROVIDER must be one of: {supported}.") from error

    if provider is ModelProvider.GEMINI:
        api_key = os.getenv("GEMINI_API_KEY") or os.getenv("LLM_API_KEY")
        if not api_key:
            raise ValueError("Set GEMINI_API_KEY or LLM_API_KEY before creating a Gemini chat model.")
        model_name = os.getenv("GEMINI_MODEL") or os.getenv("LLM_MODEL", "gemini-3.5-flash")
        base_url = None
    elif provider is ModelProvider.OPENAI:
        api_key = os.getenv("LLM_API_KEY") or os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise ValueError("Set LLM_API_KEY or OPENAI_API_KEY before creating a chat model.")
        model_name = os.getenv("LLM_MODEL", "gpt-4.1-mini")
        base_url = None
    else:  # OPENAI_COMPATIBLE
        api_key = os.getenv("LLM_API_KEY") or os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise ValueError("Set LLM_API_KEY or OPENAI_API_KEY before creating a chat model.")
        base_url = os.getenv("LLM_BASE_URL")
        if not base_url:
            raise ValueError("LLM_BASE_URL is required when LLM_PROVIDER=openai_compatible.")
        model_name = os.getenv("LLM_MODEL", "meta-llama/Meta-Llama-3.1-8B-Instruct")

    temperature_value = os.getenv("LLM_TEMPERATURE", "0")
    try:
        temperature = float(temperature_value)
    except ValueError as error:
        raise ValueError("LLM_TEMPERATURE must be a number between 0 and 2.") from error

    return ModelSettings(
        provider=provider,
        model_name=model_name,
        api_key=api_key,
        base_url=base_url,
        temperature=temperature,
    )
