"""SQLite-backed relational repository for NovaDesk synthetic enterprise data."""

from datetime import date, datetime
from decimal import Decimal
import os
from pathlib import Path
import sqlite3
from typing import Any

from operations_agent.models.tools import (
    AccountManager,
    AccountStatus,
    Customer,
    CustomerInteraction,
    CustomerSummaryResult,
    Invoice,
    KnowledgeBaseArticle,
    ProductUsage,
    Subscription,
    SupportTicket,
    TicketPriority,
    TicketStatus,
    Transaction,
    TransactionStatus,
)

DEFAULT_DB_DIR = Path(__file__).resolve().parent
DEFAULT_DB_PATH = DEFAULT_DB_DIR / "enterprise.db"


def get_db_path() -> Path:
    """Return configured or default SQLite database file path."""
    env_path = os.getenv("ENTERPRISE_DB_PATH")
    if env_path:
        return Path(env_path)
    return DEFAULT_DB_PATH


def get_db_connection(db_path: Path | str | None = None) -> sqlite3.Connection:
    """Open an optimized SQLite connection with WAL mode and row dictionary support."""
    path = Path(db_path) if db_path else get_db_path()
    conn = sqlite3.connect(str(path), timeout=30.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = WAL;")
    conn.execute("PRAGMA synchronous = NORMAL;")
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn


def init_db(db_path: Path | str | None = None) -> None:
    """Initialize SQLite tables and create optimized indexes."""
    path = Path(db_path) if db_path else get_db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = get_db_connection(path)
    with conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS account_managers (
            employee_id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            email TEXT NOT NULL,
            team TEXT NOT NULL,
            region TEXT NOT NULL,
            portfolio_size INTEGER NOT NULL DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS customers (
            customer_id INTEGER PRIMARY KEY,
            full_name TEXT NOT NULL,
            company_name TEXT NOT NULL,
            email TEXT NOT NULL,
            segment TEXT NOT NULL,
            plan_name TEXT NOT NULL,
            monthly_recurring_revenue REAL NOT NULL,
            account_status TEXT NOT NULL,
            joined_on TEXT NOT NULL,
            last_login_at TEXT,
            industry TEXT NOT NULL DEFAULT 'Technology',
            company_size TEXT NOT NULL DEFAULT '50-250',
            country TEXT NOT NULL DEFAULT 'United States',
            region TEXT NOT NULL DEFAULT 'North America',
            account_manager TEXT,
            contract_start TEXT,
            contract_end TEXT,
            satisfaction_score REAL,
            risk_segment TEXT NOT NULL DEFAULT 'Healthy'
        );

        CREATE TABLE IF NOT EXISTS subscriptions (
            subscription_id TEXT PRIMARY KEY,
            customer_id INTEGER NOT NULL REFERENCES customers(customer_id),
            plan_name TEXT NOT NULL,
            billing_cycle TEXT NOT NULL,
            start_date TEXT NOT NULL,
            end_date TEXT,
            monthly_recurring_revenue REAL NOT NULL,
            status TEXT NOT NULL,
            seats INTEGER NOT NULL DEFAULT 10,
            auto_renew INTEGER NOT NULL DEFAULT 1
        );

        CREATE TABLE IF NOT EXISTS transactions (
            transaction_id TEXT PRIMARY KEY,
            customer_id INTEGER NOT NULL REFERENCES customers(customer_id),
            subscription_id TEXT,
            occurred_on TEXT NOT NULL,
            amount REAL NOT NULL,
            currency TEXT NOT NULL DEFAULT 'USD',
            status TEXT NOT NULL,
            description TEXT NOT NULL,
            failure_reason TEXT,
            transaction_type TEXT NOT NULL DEFAULT 'payment',
            payment_method TEXT NOT NULL DEFAULT 'credit_card'
        );

        CREATE TABLE IF NOT EXISTS invoices (
            invoice_id TEXT PRIMARY KEY,
            customer_id INTEGER NOT NULL REFERENCES customers(customer_id),
            subscription_id TEXT,
            issue_date TEXT NOT NULL,
            due_date TEXT NOT NULL,
            paid_date TEXT,
            amount REAL NOT NULL,
            status TEXT NOT NULL,
            days_overdue INTEGER NOT NULL DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS product_usage (
            usage_id TEXT PRIMARY KEY,
            customer_id INTEGER NOT NULL REFERENCES customers(customer_id),
            date TEXT NOT NULL,
            active_users INTEGER NOT NULL DEFAULT 0,
            sessions INTEGER NOT NULL DEFAULT 0,
            api_calls INTEGER NOT NULL DEFAULT 0,
            workflows_executed INTEGER NOT NULL DEFAULT 0,
            automation_runs INTEGER NOT NULL DEFAULT 0,
            features_used_count INTEGER NOT NULL DEFAULT 0,
            storage_consumed_gb REAL NOT NULL DEFAULT 0.0
        );

        CREATE TABLE IF NOT EXISTS support_tickets (
            ticket_id TEXT PRIMARY KEY,
            customer_id INTEGER NOT NULL REFERENCES customers(customer_id),
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            resolved_at TEXT,
            status TEXT NOT NULL,
            priority TEXT NOT NULL,
            subject TEXT NOT NULL,
            summary TEXT NOT NULL,
            category TEXT NOT NULL,
            sla_status TEXT NOT NULL DEFAULT 'met',
            assigned_team TEXT NOT NULL DEFAULT 'Tier 1 Support',
            resolution_time_hours REAL,
            satisfaction_score INTEGER
        );

        CREATE TABLE IF NOT EXISTS customer_interactions (
            interaction_id TEXT PRIMARY KEY,
            customer_id INTEGER NOT NULL REFERENCES customers(customer_id),
            account_manager TEXT,
            occurred_at TEXT NOT NULL,
            interaction_type TEXT NOT NULL,
            sentiment TEXT NOT NULL,
            topic TEXT NOT NULL,
            summary TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS knowledge_base (
            article_id TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            category TEXT NOT NULL,
            summary TEXT NOT NULL,
            tags TEXT NOT NULL,
            updated_on TEXT NOT NULL,
            content TEXT NOT NULL
        );

        -- Indexes for high-performance retrieval
        CREATE INDEX IF NOT EXISTS idx_customers_status ON customers(account_status);
        CREATE INDEX IF NOT EXISTS idx_customers_risk ON customers(risk_segment);
        CREATE INDEX IF NOT EXISTS idx_customers_segment ON customers(segment);
        CREATE INDEX IF NOT EXISTS idx_subscriptions_cust ON subscriptions(customer_id);
        CREATE INDEX IF NOT EXISTS idx_transactions_cust_date ON transactions(customer_id, occurred_on DESC);
        CREATE INDEX IF NOT EXISTS idx_invoices_cust_date ON invoices(customer_id, issue_date DESC);
        CREATE INDEX IF NOT EXISTS idx_usage_cust_date ON product_usage(customer_id, date DESC);
        CREATE INDEX IF NOT EXISTS idx_tickets_cust_created ON support_tickets(customer_id, created_at DESC);
        CREATE INDEX IF NOT EXISTS idx_interactions_cust_date ON customer_interactions(customer_id, occurred_at DESC);
        CREATE INDEX IF NOT EXISTS idx_kb_category ON knowledge_base(category);
        """)
    conn.close()


def parse_date(value: Any) -> date | None:
    """Safely convert string or date to date object."""
    if not value:
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def parse_datetime(value: Any) -> datetime | None:
    """Safely convert string or datetime to datetime object."""
    if not value:
        return None
    if isinstance(value, datetime):
        return value
    try:
        iso_str = str(value).replace("Z", "+00:00")
        return datetime.fromisoformat(iso_str)
    except ValueError:
        return None


def row_to_customer(row: sqlite3.Row) -> Customer:
    """Convert an SQLite Row to a Pydantic Customer instance."""
    return Customer(
        customer_id=row["customer_id"],
        full_name=row["full_name"],
        company_name=row["company_name"],
        email=row["email"],
        segment=row["segment"],
        plan_name=row["plan_name"],
        monthly_recurring_revenue=Decimal(f"{row['monthly_recurring_revenue']:.2f}"),
        account_status=AccountStatus(row["account_status"]),
        joined_on=parse_date(row["joined_on"]) or date(2024, 1, 1),
        last_login_at=parse_datetime(row["last_login_at"]),
        industry=row["industry"],
        company_size=row["company_size"],
        country=row["country"],
        region=row["region"],
        account_manager=row["account_manager"],
        contract_start=parse_date(row["contract_start"]),
        contract_end=parse_date(row["contract_end"]),
        satisfaction_score=row["satisfaction_score"],
        risk_segment=row["risk_segment"],
    )


def row_to_transaction(row: sqlite3.Row) -> Transaction:
    """Convert an SQLite Row to a Pydantic Transaction instance."""
    return Transaction(
        transaction_id=row["transaction_id"],
        customer_id=row["customer_id"],
        subscription_id=row["subscription_id"],
        occurred_on=parse_date(row["occurred_on"]) or date(2026, 1, 1),
        amount=Decimal(f"{row['amount']:.2f}"),
        currency=row["currency"],
        status=TransactionStatus(row["status"]),
        description=row["description"],
        failure_reason=row["failure_reason"],
        transaction_type=row["transaction_type"],
        payment_method=row["payment_method"],
    )


def row_to_support_ticket(row: sqlite3.Row) -> SupportTicket:
    """Convert an SQLite Row to a Pydantic SupportTicket instance."""
    return SupportTicket(
        ticket_id=row["ticket_id"],
        customer_id=row["customer_id"],
        created_at=parse_datetime(row["created_at"]) or datetime(2026, 1, 1),
        updated_at=parse_datetime(row["updated_at"]) or datetime(2026, 1, 1),
        resolved_at=parse_datetime(row["resolved_at"]),
        status=TicketStatus(row["status"]),
        priority=TicketPriority(row["priority"]),
        subject=row["subject"],
        summary=row["summary"],
        category=row["category"],
        sla_status=row["sla_status"],
        assigned_team=row["assigned_team"],
        resolution_time_hours=row["resolution_time_hours"],
        satisfaction_score=row["satisfaction_score"],
    )


def row_to_invoice(row: sqlite3.Row) -> Invoice:
    """Convert an SQLite Row to a Pydantic Invoice instance."""
    return Invoice(
        invoice_id=row["invoice_id"],
        customer_id=row["customer_id"],
        subscription_id=row["subscription_id"],
        issue_date=parse_date(row["issue_date"]) or date(2026, 1, 1),
        due_date=parse_date(row["due_date"]) or date(2026, 1, 1),
        paid_date=parse_date(row["paid_date"]),
        amount=Decimal(f"{row['amount']:.2f}"),
        status=row["status"],
        days_overdue=row["days_overdue"],
    )


def row_to_usage(row: sqlite3.Row) -> ProductUsage:
    """Convert an SQLite Row to a Pydantic ProductUsage instance."""
    return ProductUsage(
        usage_id=row["usage_id"],
        customer_id=row["customer_id"],
        date=parse_date(row["date"]) or date(2026, 1, 1),
        active_users=row["active_users"],
        sessions=row["sessions"],
        api_calls=row["api_calls"],
        workflows_executed=row["workflows_executed"],
        automation_runs=row["automation_runs"],
        features_used_count=row["features_used_count"],
        storage_consumed_gb=row["storage_consumed_gb"],
    )


def row_to_interaction(row: sqlite3.Row) -> CustomerInteraction:
    """Convert an SQLite Row to a Pydantic CustomerInteraction instance."""
    return CustomerInteraction(
        interaction_id=row["interaction_id"],
        customer_id=row["customer_id"],
        account_manager=row["account_manager"],
        occurred_at=parse_datetime(row["occurred_at"]) or datetime(2026, 1, 1),
        interaction_type=row["interaction_type"],
        sentiment=row["sentiment"],
        topic=row["topic"],
        summary=row["summary"],
    )


def row_to_kb_article(row: sqlite3.Row) -> KnowledgeBaseArticle:
    """Convert an SQLite Row to a Pydantic KnowledgeBaseArticle instance."""
    raw_tags = row["tags"].split(",") if row["tags"] else []
    clean_tags = tuple(t.strip() for t in raw_tags if t.strip())
    return KnowledgeBaseArticle(
        article_id=row["article_id"],
        title=row["title"],
        category=row["category"],
        summary=row["summary"],
        tags=clean_tags,
        updated_on=parse_date(row["updated_on"]) or date(2026, 1, 1),
        content=row["content"],
    )
