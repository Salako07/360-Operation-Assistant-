"""Centralized factory for the application's replaceable chat model."""

try:
    import langchain_google_genai.chat_models as _cm
    from langchain_google_genai import ChatGoogleGenerativeAI

    # Ensure Gemini 3 series thought_signatures are preserved across multi-turn tool calling in LangChain
    _orig_parse_candidate = _cm._parse_response_candidate
    _orig_parse_history = _cm._parse_chat_history

    def _patched_parse_candidate(candidate: object, streaming: bool = False) -> object:
        msg = _orig_parse_candidate(candidate, streaming=streaming)
        signatures = []
        parts = getattr(getattr(candidate, "content", None), "parts", [])
        for part in parts:
            sig = getattr(part, "thought_signature", None)
            if sig:
                signatures.append(sig)
        if signatures:
            msg.additional_kwargs["thought_signatures"] = signatures
        return msg

    def _patched_parse_history(input_messages: list[object], convert_system_message_to_human: bool = False) -> tuple[object, list[object]]:
        system_instruction, messages = _orig_parse_history(
            input_messages, convert_system_message_to_human=convert_system_message_to_human
        )
        for input_msg in input_messages:
            if getattr(input_msg, "tool_calls", None):
                signatures = getattr(input_msg, "additional_kwargs", {}).get("thought_signatures", [])
                if signatures:
                    for content in messages:
                        if getattr(content, "role", None) == "model" and getattr(content, "parts", None):
                            for i, part in enumerate(content.parts):
                                if getattr(part, "function_call", None) and not getattr(part, "thought_signature", None):
                                    part.thought_signature = signatures[i] if i < len(signatures) else signatures[0]
        return system_instruction, messages

    _cm._parse_response_candidate = _patched_parse_candidate
    _cm._parse_chat_history = _patched_parse_history

except ImportError:  # pragma: no cover
    ChatGoogleGenerativeAI = None  # type: ignore[assignment,misc]

from langchain_openai import ChatOpenAI

from operations_agent.config import ModelProvider, ModelSettings, load_model_settings
from operations_agent.models.chat_model import ChatModel


def create_chat_model(settings: ModelSettings | None = None) -> ChatModel:
    """Create the configured LangChain chat model.

    Supported providers:
    - `gemini`: Uses `ChatGoogleGenerativeAI` via `GEMINI_API_KEY`.
    - `openai`: Uses `ChatOpenAI` with standard OpenAI API endpoint.
    - `openai_compatible`: Uses `ChatOpenAI` with custom `base_url` (e.g. self-hosted vLLM).

    Application code depends only on the returned `ChatModel` abstraction.
    """
    resolved_settings = settings or load_model_settings()

    if resolved_settings.provider is ModelProvider.GEMINI:
        if ChatGoogleGenerativeAI is None:
            raise ImportError(
                "langchain-google-genai is required for the Gemini provider. "
                "Install it using `pip install langchain-google-genai`."
            )
        return ChatGoogleGenerativeAI(
            model=resolved_settings.model_name,
            google_api_key=resolved_settings.api_key,
            temperature=resolved_settings.temperature,
        )

    model_kwargs: dict[str, str | float] = {
        "model": resolved_settings.model_name,
        "api_key": resolved_settings.api_key,
        "temperature": resolved_settings.temperature,
    }
    if resolved_settings.base_url:
        model_kwargs["base_url"] = resolved_settings.base_url

    return ChatOpenAI(**model_kwargs)
