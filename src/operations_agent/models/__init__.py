"""Pydantic contracts for the local operations data sources."""

from operations_agent.models.chat_model import ChatModel
from operations_agent.models.tools import (
    Customer,
    CustomerLookupInput,
    CustomerResult,
    KnowledgeBaseArticle,
    KnowledgeBaseSearchInput,
    KnowledgeBaseSearchResult,
    SupportTicket,
    SupportTicketsResult,
    Transaction,
    TransactionsResult,
)

__all__ = [
    "ChatModel",
    "Customer",
    "CustomerLookupInput",
    "CustomerResult",
    "KnowledgeBaseArticle",
    "KnowledgeBaseSearchInput",
    "KnowledgeBaseSearchResult",
    "SupportTicket",
    "SupportTicketsResult",
    "Transaction",
    "TransactionsResult",
]
