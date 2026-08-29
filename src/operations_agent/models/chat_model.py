"""Abstract chat-model type exported for application dependencies."""

from langchain_core.language_models.chat_models import BaseChatModel

ChatModel = BaseChatModel

__all__ = ["ChatModel"]
