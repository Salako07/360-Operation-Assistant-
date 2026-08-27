"""Structured contracts for local, read-only operations tools."""

from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class AccountStatus(StrEnum):
    """Current state of a customer account."""

    ACTIVE = "active"
    PAST_DUE = "past_due"
    CANCELLED = "cancelled"


class TicketStatus(StrEnum):
    """Lifecycle state of a support ticket."""

    OPEN = "open"
    PENDING = "pending"
    RESOLVED = "resolved"


class TicketPriority(StrEnum):
    """Support ticket priority assigned by the support system."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    URGENT = "urgent"


class TransactionStatus(StrEnum):
    """Outcome of a subscription billing transaction."""

    SUCCEEDED = "succeeded"
    FAILED = "failed"
    REFUNDED = "refunded"


class Customer(BaseModel):
    """A customer profile returned by the customer directory."""

    model_config = ConfigDict(frozen=True)

    customer_id: int = Field(gt=0)
    full_name: str
    company_name: str
    email: str
    segment: str
    plan_name: str
    monthly_recurring_revenue: Decimal = Field(ge=0)
    account_status: AccountStatus
    joined_on: date
    last_login_at: datetime | None = None


class Transaction(BaseModel):
    """A billing, payment, or refund event for a customer."""

    model_config = ConfigDict(frozen=True)

    transaction_id: str
    customer_id: int = Field(gt=0)
    occurred_on: date
    amount: Decimal
    currency: str = Field(min_length=3, max_length=3)
    status: TransactionStatus
    description: str
    failure_reason: str | None = None


class SupportTicket(BaseModel):
    """A normalized support ticket summary."""

    model_config = ConfigDict(frozen=True)

    ticket_id: str
    customer_id: int = Field(gt=0)
    created_at: datetime
    updated_at: datetime
    status: TicketStatus
    priority: TicketPriority
    subject: str
    summary: str
    category: str


class KnowledgeBaseArticle(BaseModel):
    """An approved internal knowledge-base article available for search."""

    model_config = ConfigDict(frozen=True)

    article_id: str
    title: str
    summary: str
    tags: tuple[str, ...]
    updated_on: date


class ToolError(BaseModel):
    """A recoverable validation or lookup error returned by a tool."""

    code: str
    message: str


class CustomerLookupInput(BaseModel):
    """Input contract for a customer-scoped retrieval tool."""

    customer_id: int = Field(gt=0)


class KnowledgeBaseSearchInput(BaseModel):
    """Input contract for an internal knowledge-base search."""

    query: str = Field(min_length=1, max_length=500)


class CustomerResult(BaseModel):
    """Structured result from a customer profile lookup."""

    customer_id: int | None
    customer: Customer | None = None
    error: ToolError | None = None


class TransactionsResult(BaseModel):
    """Structured result from a customer transaction lookup."""

    customer_id: int | None
    transactions: tuple[Transaction, ...] = ()
    error: ToolError | None = None


class SupportTicketsResult(BaseModel):
    """Structured result from a customer support-ticket lookup."""

    customer_id: int | None
    tickets: tuple[SupportTicket, ...] = ()
    error: ToolError | None = None


class KnowledgeBaseMatch(BaseModel):
    """A knowledge-base article and its deterministic lexical relevance score."""

    article: KnowledgeBaseArticle
    relevance_score: float = Field(ge=0, le=1)


class KnowledgeBaseSearchResult(BaseModel):
    """Structured result from an internal knowledge-base search."""

    query: str
    matches: tuple[KnowledgeBaseMatch, ...] = ()
    error: ToolError | None = None
