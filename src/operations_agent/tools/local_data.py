"""High-performance, read-only data accessors for NovaDesk operations tools."""

from datetime import date, datetime
from decimal import Decimal
import re
from typing import Any

from operations_agent.data.database import (
    get_db_connection,
    get_db_path,
    row_to_customer,
    row_to_interaction,
    row_to_invoice,
    row_to_kb_article,
    row_to_support_ticket,
    row_to_transaction,
    row_to_usage,
)
from operations_agent.data.mock_data import (
    CUSTOMERS as MOCK_CUSTOMERS,
    KNOWLEDGE_BASE_ARTICLES as MOCK_KB_ARTICLES,
    SUPPORT_TICKETS as MOCK_SUPPORT_TICKETS,
    TRANSACTIONS as MOCK_TRANSACTIONS,
)
from operations_agent.models.tools import (
    ChurnRiskResult,
    Customer,
    CustomerInteractionsResult,
    CustomerListResult,
    CustomerResult,
    CustomerSummaryResult,
    InvoicesResult,
    KnowledgeBaseArticle,
    KnowledgeBaseMatch,
    KnowledgeBaseSearchResult,
    SupportTicketsResult,
    ToolError,
    TransactionsResult,
    UsageAnomalyResult,
    UsageMetricsResult,
)

_TOKEN_PATTERN = re.compile(r"[a-z0-9]+")


def _customer_id_error(customer_id: object) -> ToolError | None:
    """Return a structured error when a supplied customer ID is invalid."""
    if isinstance(customer_id, bool) or not isinstance(customer_id, int) or customer_id <= 0:
        return ToolError(
            code="invalid_customer_id",
            message="customer_id must be a positive integer.",
        )
    return None


def get_customer(customer_id: int) -> CustomerResult:
    """Retrieve one customer profile by ID from the database or fixture cache."""
    error = _customer_id_error(customer_id)
    if error:
        return CustomerResult(customer_id=None, error=error)

    db_path = get_db_path()
    if db_path.exists():
        try:
            conn = get_db_connection(db_path)
            row = conn.execute("SELECT * FROM customers WHERE customer_id = ?", (customer_id,)).fetchone()
            conn.close()
            if row:
                return CustomerResult(customer_id=customer_id, customer=row_to_customer(row))
        except Exception:
            pass

    # Fallback to in-memory fixtures
    customer = MOCK_CUSTOMERS.get(customer_id)
    if customer is None:
        return CustomerResult(
            customer_id=customer_id,
            error=ToolError(
                code="customer_not_found",
                message=f"No customer exists with ID {customer_id}.",
            ),
        )
    return CustomerResult(customer_id=customer_id, customer=customer)


def get_customer_summary(customer_id: int) -> CustomerSummaryResult:
    """Retrieve an aggregated operational 360-degree overview for a customer."""
    cust_res = get_customer(customer_id)
    if cust_res.error or not cust_res.customer:
        return CustomerSummaryResult(
            customer_id=customer_id,
            error=cust_res.error or ToolError(code="customer_not_found", message=f"Customer {customer_id} not found."),
        )

    tx_res = get_transactions(customer_id, limit=50)
    ticket_res = get_support_tickets(customer_id, limit=50)
    usage_res = get_usage_metrics(customer_id, limit=30)
    interaction_res = get_customer_interactions(customer_id, limit=10)

    recent_txs = tx_res.transactions
    failed_txs = [t for t in recent_txs if t.status.value == "failed"]
    open_tickets = [t for t in ticket_res.tickets if t.status.value in {"open", "pending"}]
    urgent_tickets = [t for t in ticket_res.tickets if t.priority.value in {"high", "urgent"} and t.status.value in {"open", "pending"}]

    avg_users = 0.0
    trend_pct = 0.0
    if usage_res.metrics:
        recent_usage = list(usage_res.metrics)
        avg_users = sum(u.active_users for u in recent_usage) / len(recent_usage)
        if len(recent_usage) >= 14:
            first_half = recent_usage[len(recent_usage)//2:]
            second_half = recent_usage[:len(recent_usage)//2]
            avg1 = sum(u.active_users for u in first_half) / len(first_half)
            avg2 = sum(u.active_users for u in second_half) / len(second_half)
            if avg1 > 0:
                trend_pct = round(((avg2 - avg1) / avg1) * 100.0, 1)

    sentiment = "neutral"
    if interaction_res.interactions:
        sentiments = [i.sentiment for i in interaction_res.interactions]
        if sentiments.count("negative") > sentiments.count("positive"):
            sentiment = "negative"
        elif sentiments.count("positive") > sentiments.count("negative"):
            sentiment = "positive"

    return CustomerSummaryResult(
        customer_id=customer_id,
        customer=cust_res.customer,
        recent_transactions_count=len(recent_txs),
        failed_transactions_count=len(failed_txs),
        open_tickets_count=len(open_tickets),
        urgent_tickets_count=len(urgent_tickets),
        average_daily_users_last_30d=round(avg_users, 1),
        usage_trend_percentage=trend_pct,
        sentiment_summary=sentiment,
        risk_segment=cust_res.customer.risk_segment,
    )


def get_transactions(
    customer_id: int,
    start_date: str | None = None,
    end_date: str | None = None,
    limit: int = 50,
) -> TransactionsResult:
    """Retrieve billing transactions for one customer with optional date and pagination filtering."""
    error = _customer_id_error(customer_id)
    if error:
        return TransactionsResult(customer_id=None, error=error)

    cust_check = get_customer(customer_id)
    if cust_check.error:
        return TransactionsResult(customer_id=customer_id, error=cust_check.error)

    db_path = get_db_path()
    if db_path.exists():
        try:
            conn = get_db_connection(db_path)
            query = "SELECT * FROM transactions WHERE customer_id = ?"
            params: list[Any] = [customer_id]
            if start_date:
                query += " AND occurred_on >= ?"
                params.append(start_date)
            if end_date:
                query += " AND occurred_on <= ?"
                params.append(end_date)
            query += " ORDER BY occurred_on DESC LIMIT ?"
            params.append(limit)

            rows = conn.execute(query, params).fetchall()
            conn.close()
            if rows:
                return TransactionsResult(
                    customer_id=customer_id,
                    transactions=tuple(row_to_transaction(r) for r in rows),
                )
        except Exception:
            pass

    # Fallback to in-memory fixtures
    transactions = tuple(
        t for t in MOCK_TRANSACTIONS
        if t.customer_id == customer_id
    )
    return TransactionsResult(customer_id=customer_id, transactions=transactions)


def get_invoices(
    customer_id: int,
    status: str | None = None,
    limit: int = 50,
) -> InvoicesResult:
    """Retrieve customer invoices with optional status filter."""
    error = _customer_id_error(customer_id)
    if error:
        return InvoicesResult(customer_id=None, error=error)

    cust_check = get_customer(customer_id)
    if cust_check.error:
        return InvoicesResult(customer_id=customer_id, error=cust_check.error)

    db_path = get_db_path()
    if db_path.exists():
        try:
            conn = get_db_connection(db_path)
            query = "SELECT * FROM invoices WHERE customer_id = ?"
            params: list[Any] = [customer_id]
            if status:
                query += " AND status = ?"
                params.append(status.strip().lower())
            query += " ORDER BY issue_date DESC LIMIT ?"
            params.append(limit)

            rows = conn.execute(query, params).fetchall()
            conn.close()
            return InvoicesResult(
                customer_id=customer_id,
                invoices=tuple(row_to_invoice(r) for r in rows),
            )
        except Exception:
            pass

    return InvoicesResult(customer_id=customer_id, invoices=())


def get_support_tickets(
    customer_id: int,
    status: str | None = None,
    priority: str | None = None,
    limit: int = 50,
) -> SupportTicketsResult:
    """Retrieve support tickets for one customer with optional status and priority filtering."""
    error = _customer_id_error(customer_id)
    if error:
        return SupportTicketsResult(customer_id=None, error=error)

    cust_check = get_customer(customer_id)
    if cust_check.error:
        return SupportTicketsResult(customer_id=customer_id, error=cust_check.error)

    db_path = get_db_path()
    if db_path.exists():
        try:
            conn = get_db_connection(db_path)
            query = "SELECT * FROM support_tickets WHERE customer_id = ?"
            params: list[Any] = [customer_id]
            if status:
                query += " AND status = ?"
                params.append(status.strip().lower())
            if priority:
                query += " AND priority = ?"
                params.append(priority.strip().lower())
            query += " ORDER BY created_at DESC LIMIT ?"
            params.append(limit)

            rows = conn.execute(query, params).fetchall()
            conn.close()
            if rows:
                return SupportTicketsResult(
                    customer_id=customer_id,
                    tickets=tuple(row_to_support_ticket(r) for r in rows),
                )
        except Exception:
            pass

    # Fallback to in-memory fixtures
    tickets = tuple(t for t in MOCK_SUPPORT_TICKETS if t.customer_id == customer_id)
    return SupportTicketsResult(customer_id=customer_id, tickets=tickets)


def get_usage_metrics(
    customer_id: int,
    start_date: str | None = None,
    end_date: str | None = None,
    limit: int = 90,
) -> UsageMetricsResult:
    """Retrieve daily product usage time-series metrics for one customer."""
    error = _customer_id_error(customer_id)
    if error:
        return UsageMetricsResult(customer_id=None, error=error)

    cust_check = get_customer(customer_id)
    if cust_check.error:
        return UsageMetricsResult(customer_id=customer_id, error=cust_check.error)

    db_path = get_db_path()
    if db_path.exists():
        try:
            conn = get_db_connection(db_path)
            query = "SELECT * FROM product_usage WHERE customer_id = ?"
            params: list[Any] = [customer_id]
            if start_date:
                query += " AND date >= ?"
                params.append(start_date)
            if end_date:
                query += " AND date <= ?"
                params.append(end_date)
            query += " ORDER BY date DESC LIMIT ?"
            params.append(limit)

            rows = conn.execute(query, params).fetchall()
            conn.close()
            return UsageMetricsResult(
                customer_id=customer_id,
                metrics=tuple(row_to_usage(r) for r in rows),
            )
        except Exception:
            pass

    return UsageMetricsResult(customer_id=customer_id, metrics=())


def get_customer_interactions(
    customer_id: int,
    start_date: str | None = None,
    end_date: str | None = None,
    limit: int = 50,
) -> CustomerInteractionsResult:
    """Retrieve logged customer touchpoints, meetings, calls, and sentiment records."""
    error = _customer_id_error(customer_id)
    if error:
        return CustomerInteractionsResult(customer_id=None, error=error)

    cust_check = get_customer(customer_id)
    if cust_check.error:
        return CustomerInteractionsResult(customer_id=customer_id, error=cust_check.error)

    db_path = get_db_path()
    if db_path.exists():
        try:
            conn = get_db_connection(db_path)
            query = "SELECT * FROM customer_interactions WHERE customer_id = ?"
            params: list[Any] = [customer_id]
            if start_date:
                query += " AND occurred_at >= ?"
                params.append(start_date)
            if end_date:
                query += " AND occurred_at <= ?"
                params.append(end_date)
            query += " ORDER BY occurred_at DESC LIMIT ?"
            params.append(limit)

            rows = conn.execute(query, params).fetchall()
            conn.close()
            return CustomerInteractionsResult(
                customer_id=customer_id,
                interactions=tuple(row_to_interaction(r) for r in rows),
            )
        except Exception:
            pass

    return CustomerInteractionsResult(customer_id=customer_id, interactions=())


def calculate_churn_risk(customer_id: int) -> ChurnRiskResult:
    """Calculate multi-dimensional churn probability and risk indicators."""
    error = _customer_id_error(customer_id)
    if error:
        return ChurnRiskResult(
            customer_id=customer_id or 0,
            churn_probability=0.0,
            risk_level="unknown",
            recommendation_summary="Invalid customer ID.",
            error=error,
        )

    summary = get_customer_summary(customer_id)
    if summary.error or not summary.customer:
        return ChurnRiskResult(
            customer_id=customer_id,
            churn_probability=0.0,
            risk_level="unknown",
            recommendation_summary=f"Customer {customer_id} not found.",
            error=summary.error,
        )

    risk_factors: list[str] = []
    score = 0.10

    # 1. Billing Risk
    billing_health = "healthy"
    if summary.customer.account_status.value == "past_due":
        score += 0.35
        billing_health = "severe_overdue"
        risk_factors.append("past_due_account_status")
    elif summary.failed_transactions_count > 0:
        score += 0.20
        billing_health = "payment_friction"
        risk_factors.append("recent_failed_payment")

    # 2. Support Risk
    support_health = "healthy"
    if summary.urgent_tickets_count > 0:
        score += 0.25
        support_health = "critical_sla_breach"
        risk_factors.append("unresolved_urgent_support_ticket")
    elif summary.open_tickets_count > 2:
        score += 0.15
        support_health = "elevated_friction"
        risk_factors.append("multiple_open_support_tickets")

    # 3. Usage Trend Risk
    usage_trend = "stable"
    if summary.usage_trend_percentage < -30.0:
        score += 0.30
        usage_trend = "declining"
        risk_factors.append("severe_usage_decline")
    elif summary.usage_trend_percentage < -15.0:
        score += 0.15
        usage_trend = "declining"
        risk_factors.append("moderate_usage_decline")
    elif summary.usage_trend_percentage > 15.0:
        score -= 0.10
        usage_trend = "growing"

    # 4. Sentiment Risk
    if summary.sentiment_summary == "negative":
        score += 0.15
        risk_factors.append("negative_customer_sentiment")

    churn_prob = max(0.02, min(0.98, round(score, 2)))
    if churn_prob >= 0.65:
        risk_lvl = "high"
        rec = "Immediate human-reviewed retention intervention required."
    elif churn_prob >= 0.35:
        risk_lvl = "medium"
        rec = "Proactive CSM outreach and support escalation monitoring recommended."
    else:
        risk_lvl = "low"
        rec = "Account is in healthy standing. Continue standard monitoring."

    return ChurnRiskResult(
        customer_id=customer_id,
        churn_probability=churn_prob,
        risk_level=risk_lvl,
        primary_risk_factors=tuple(risk_factors),
        usage_trend=usage_trend,
        billing_health=billing_health,
        support_health=support_health,
        recommendation_summary=rec,
    )


def detect_usage_anomaly(customer_id: int) -> UsageAnomalyResult:
    """Detect statistical anomalies in customer product usage time-series."""
    usage_res = get_usage_metrics(customer_id, limit=60)
    if usage_res.error or not usage_res.metrics or len(usage_res.metrics) < 7:
        return UsageAnomalyResult(
            customer_id=customer_id,
            has_anomaly=False,
            explanation="Insufficient usage history to establish statistical baseline.",
            error=usage_res.error,
        )

    records = list(usage_res.metrics)
    records.sort(key=lambda r: r.date)

    recent = records[-7:]
    historical = records[:-7] if len(records) > 7 else records

    base_avg = sum(r.active_users for r in historical) / max(1, len(historical))
    rec_avg = sum(r.active_users for r in recent) / max(1, len(recent))

    if base_avg > 0:
        pct_change = round(((rec_avg - base_avg) / base_avg) * 100.0, 1)
    else:
        pct_change = 0.0

    if pct_change <= -40.0:
        return UsageAnomalyResult(
            customer_id=customer_id,
            has_anomaly=True,
            anomaly_type="drop",
            anomaly_date=recent[0].date.isoformat(),
            baseline_average=round(base_avg, 1),
            anomaly_value=round(rec_avg, 1),
            percentage_change=pct_change,
            explanation=f"Severe usage drop of {abs(pct_change)}% detected relative to baseline.",
        )
    elif pct_change >= 50.0:
        return UsageAnomalyResult(
            customer_id=customer_id,
            has_anomaly=True,
            anomaly_type="spike",
            anomaly_date=recent[0].date.isoformat(),
            baseline_average=round(base_avg, 1),
            anomaly_value=round(rec_avg, 1),
            percentage_change=pct_change,
            explanation=f"Usage spike of +{pct_change}% detected, indicating rapid adoption or expansion.",
        )

    return UsageAnomalyResult(
        customer_id=customer_id,
        has_anomaly=False,
        baseline_average=round(base_avg, 1),
        anomaly_value=round(rec_avg, 1),
        percentage_change=pct_change,
        explanation="Product usage is within normal baseline variance.",
    )


def _tokenize(value: str) -> set[str]:
    """Normalize text into lexical search tokens."""
    return set(_TOKEN_PATTERN.findall(value.lower()))


def search_knowledge_base(query: str) -> KnowledgeBaseSearchResult:
    """Search approved local knowledge-base articles using deterministic token overlap."""
    if not isinstance(query, str) or not query.strip():
        return KnowledgeBaseSearchResult(
            query="" if not isinstance(query, str) else query,
            error=ToolError(
                code="invalid_query",
                message="query must be a non-empty string.",
            ),
        )

    normalized_query = query.strip()
    query_tokens = _tokenize(normalized_query)
    matches: list[KnowledgeBaseMatch] = []

    db_path = get_db_path()
    articles: list[KnowledgeBaseArticle] = []
    if db_path.exists():
        try:
            conn = get_db_connection(db_path)
            rows = conn.execute("SELECT * FROM knowledge_base").fetchall()
            conn.close()
            if rows:
                articles = [row_to_kb_article(r) for r in rows]
        except Exception:
            pass

    if not articles:
        articles = list(MOCK_KB_ARTICLES)

    for article in articles:
        searchable_text = " ".join((article.title, article.summary, *article.tags))
        matching_tokens = query_tokens & _tokenize(searchable_text)
        if matching_tokens:
            matches.append(
                KnowledgeBaseMatch(
                    article=article,
                    relevance_score=len(matching_tokens) / len(query_tokens),
                )
            )

    matches.sort(key=lambda match: (-match.relevance_score, match.article.article_id))
    return KnowledgeBaseSearchResult(query=normalized_query, matches=tuple(matches))


def list_customers(
    segment: str | None = None,
    status: str | None = None,
    risk_segment: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> CustomerListResult:
    """List customers with metrics, total counts, MRR, and optional filtering."""
    db_path = get_db_path()
    if db_path.exists():
        try:
            conn = get_db_connection(db_path)
            where_clauses: list[str] = []
            params: list[Any] = []
            if segment:
                where_clauses.append("LOWER(segment) = ?")
                params.append(segment.strip().lower())
            if status:
                where_clauses.append("LOWER(account_status) = ?")
                params.append(status.strip().lower())
            if risk_segment:
                where_clauses.append("LOWER(risk_segment) = ?")
                params.append(risk_segment.strip().lower())

            where_sql = f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ""

            count_row = conn.execute(f"SELECT COUNT(*), COALESCE(SUM(monthly_recurring_revenue), 0) FROM customers {where_sql}", params).fetchone()
            total_count = count_row[0]
            total_mrr = Decimal(f"{count_row[1]:.2f}")

            list_sql = f"SELECT * FROM customers {where_sql} ORDER BY customer_id ASC LIMIT ? OFFSET ?"
            list_params = list(params) + [limit, offset]
            rows = conn.execute(list_sql, list_params).fetchall()
            conn.close()

            customers = tuple(row_to_customer(r) for r in rows)
            return CustomerListResult(
                total_count=total_count,
                total_mrr=total_mrr,
                customers=customers,
            )
        except Exception:
            pass

    # Fallback to mock dictionary
    filtered = list(MOCK_CUSTOMERS.values())
    if segment:
        norm_seg = segment.strip().lower()
        filtered = [c for c in filtered if c.segment.lower() == norm_seg]
    if status:
        norm_stat = status.strip().lower()
        filtered = [c for c in filtered if c.account_status.value.lower() == norm_stat]
    if risk_segment:
        norm_risk = risk_segment.strip().lower()
        filtered = [c for c in filtered if getattr(c, "risk_segment", "").lower() == norm_risk]

    filtered.sort(key=lambda c: c.customer_id)
    total_mrr = sum((c.monthly_recurring_revenue for c in filtered), start=Decimal("0.00"))
    return CustomerListResult(
        total_count=len(filtered),
        total_mrr=total_mrr,
        customers=tuple(filtered[offset:offset+limit]),
    )
