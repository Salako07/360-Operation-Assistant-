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
    industry: str = "Technology"
    company_size: str = "50-250"
    country: str = "United States"
    region: str = "North America"
    account_manager: str | None = None
    contract_start: date | None = None
    contract_end: date | None = None
    satisfaction_score: float | None = None
    risk_segment: str = "Healthy"


class Subscription(BaseModel):
    """A customer subscription record."""

    model_config = ConfigDict(frozen=True)

    subscription_id: str
    customer_id: int = Field(gt=0)
    plan_name: str
    billing_cycle: str
    start_date: date
    end_date: date | None = None
    monthly_recurring_revenue: Decimal = Field(ge=0)
    status: str
    seats: int = 10
    auto_renew: bool = True


class Invoice(BaseModel):
    """A customer invoice."""

    model_config = ConfigDict(frozen=True)

    invoice_id: str
    customer_id: int = Field(gt=0)
    subscription_id: str | None = None
    issue_date: date
    due_date: date
    paid_date: date | None = None
    amount: Decimal = Field(ge=0)
    status: str
    days_overdue: int = 0


class ProductUsage(BaseModel):
    """Daily or period product usage metrics."""

    model_config = ConfigDict(frozen=True)

    usage_id: str | None = None
    customer_id: int = Field(gt=0)
    date: date
    active_users: int = 0
    sessions: int = 0
    api_calls: int = 0
    workflows_executed: int = 0
    automation_runs: int = 0
    features_used_count: int = 0
    storage_consumed_gb: float = 0.0


class CustomerInteraction(BaseModel):
    """A logged touchpoint between customer and company."""

    model_config = ConfigDict(frozen=True)

    interaction_id: str
    customer_id: int = Field(gt=0)
    occurred_at: datetime
    interaction_type: str
    sentiment: str
    topic: str
    summary: str
    account_manager: str | None = None


class AccountManager(BaseModel):
    """An internal account manager / customer success manager."""

    model_config = ConfigDict(frozen=True)

    employee_id: str
    name: str
    email: str
    team: str
    region: str
    portfolio_size: int = 0


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
    subscription_id: str | None = None
    transaction_type: str = "payment"
    payment_method: str = "credit_card"


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
    resolved_at: datetime | None = None
    sla_status: str = "met"
    assigned_team: str = "Tier 1 Support"
    resolution_time_hours: float | None = None
    satisfaction_score: int | None = None


class KnowledgeBaseArticle(BaseModel):
    """An approved internal knowledge-base article available for search."""

    model_config = ConfigDict(frozen=True)

    article_id: str
    title: str
    summary: str
    tags: tuple[str, ...]
    updated_on: date
    category: str = "General"
    content: str = ""


class ToolError(BaseModel):
    """A recoverable validation or lookup error returned by a tool."""

    code: str
    message: str


class CustomerLookupInput(BaseModel):
    """Input contract for a customer-scoped retrieval tool."""

    customer_id: int = Field(gt=0)


class TransactionLookupInput(BaseModel):
    """Input contract for transactions with optional date range and limits."""

    customer_id: int = Field(gt=0)
    start_date: str | None = Field(default=None, description="Optional ISO start date YYYY-MM-DD")
    end_date: str | None = Field(default=None, description="Optional ISO end date YYYY-MM-DD")
    limit: int = Field(default=50, ge=1, le=500)


class SupportTicketsInput(BaseModel):
    """Input contract for support tickets lookup with optional filters."""

    customer_id: int = Field(gt=0)
    status: str | None = Field(default=None, description="Optional status filter (open, pending, resolved, closed)")
    priority: str | None = Field(default=None, description="Optional priority filter (low, medium, high, urgent)")
    limit: int = Field(default=50, ge=1, le=500)


class GetInvoicesInput(BaseModel):
    """Input contract for invoices lookup."""

    customer_id: int = Field(gt=0)
    status: str | None = Field(default=None, description="Optional status filter (paid, overdue, pending)")
    limit: int = Field(default=50, ge=1, le=500)


class GetUsageMetricsInput(BaseModel):
    """Input contract for usage metrics retrieval."""

    customer_id: int = Field(gt=0)
    start_date: str | None = Field(default=None, description="Optional ISO start date YYYY-MM-DD")
    end_date: str | None = Field(default=None, description="Optional ISO end date YYYY-MM-DD")
    limit: int = Field(default=90, ge=1, le=365)


class GetCustomerInteractionsInput(BaseModel):
    """Input contract for customer interactions."""

    customer_id: int = Field(gt=0)
    start_date: str | None = Field(default=None, description="Optional ISO start date YYYY-MM-DD")
    end_date: str | None = Field(default=None, description="Optional ISO end date YYYY-MM-DD")
    limit: int = Field(default=50, ge=1, le=500)


class CalculateChurnRiskInput(BaseModel):
    """Input contract for calculating churn risk indicators."""

    customer_id: int = Field(gt=0)


class KnowledgeBaseSearchInput(BaseModel):
    """Input contract for an internal knowledge-base search."""

    query: str = Field(min_length=1, max_length=500)


class ListCustomersInput(BaseModel):
    """Input arguments for listing all customers in the directory."""

    segment: str | None = Field(default=None, description="Optional segment filter (enterprise, mid-market, small-business).")
    status: str | None = Field(default=None, description="Optional account status filter (active, past_due, cancelled).")
    risk_segment: str | None = Field(default=None, description="Optional risk segment (Healthy, Growing, At Risk, Dormant, etc.).")
    limit: int = Field(default=50, ge=1, le=500)
    offset: int = Field(default=0, ge=0)


class CustomerResult(BaseModel):
    """Structured result from a customer profile lookup."""

    customer_id: int | None
    customer: Customer | None = None
    error: ToolError | None = None


class CustomerSummaryResult(BaseModel):
    """Structured high-level operational summary for a customer."""

    customer_id: int
    customer: Customer | None = None
    recent_transactions_count: int = 0
    failed_transactions_count: int = 0
    open_tickets_count: int = 0
    urgent_tickets_count: int = 0
    average_daily_users_last_30d: float = 0.0
    usage_trend_percentage: float = 0.0
    sentiment_summary: str = "neutral"
    risk_segment: str = "Healthy"
    error: ToolError | None = None


class TransactionsResult(BaseModel):
    """Structured result from a customer transaction lookup."""

    customer_id: int | None
    transactions: tuple[Transaction, ...] = ()
    error: ToolError | None = None


class InvoicesResult(BaseModel):
    """Structured result from customer invoice lookup."""

    customer_id: int | None
    invoices: tuple[Invoice, ...] = ()
    error: ToolError | None = None


class SupportTicketsResult(BaseModel):
    """Structured result from a customer support-ticket lookup."""

    customer_id: int | None
    tickets: tuple[SupportTicket, ...] = ()
    error: ToolError | None = None


class UsageMetricsResult(BaseModel):
    """Structured result from a customer usage metrics lookup."""

    customer_id: int | None
    metrics: tuple[ProductUsage, ...] = ()
    error: ToolError | None = None


class CustomerInteractionsResult(BaseModel):
    """Structured result from customer interactions lookup."""

    customer_id: int | None
    interactions: tuple[CustomerInteraction, ...] = ()
    error: ToolError | None = None


class ChurnRiskResult(BaseModel):
    """Structured calculated churn risk evaluation for a customer."""

    customer_id: int
    churn_probability: float = Field(ge=0.0, le=1.0)
    risk_level: str  # low, medium, high, critical
    primary_risk_factors: tuple[str, ...] = ()
    usage_trend: str  # growing, stable, declining, sudden_drop, seasonal
    billing_health: str  # healthy, payment_friction, severe_overdue
    support_health: str  # healthy, normal, elevated_friction, critical_sla_breach
    recommendation_summary: str
    error: ToolError | None = None


class UsageAnomalyResult(BaseModel):
    """Structured anomaly detection result for customer usage."""

    customer_id: int
    has_anomaly: bool = False
    anomaly_type: str | None = None  # drop, spike, zero_usage, seasonal_dip, incident_related
    anomaly_date: str | None = None
    baseline_average: float = 0.0
    anomaly_value: float = 0.0
    percentage_change: float = 0.0
    explanation: str
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


class CustomerListResult(BaseModel):
    """Structured result containing directory-wide customer summary."""

    total_count: int = Field(ge=0)
    total_mrr: Decimal = Field(ge=0)
    customers: tuple[Customer, ...] = ()
    error: ToolError | None = None

