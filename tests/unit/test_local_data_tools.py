"""Unit tests for the in-memory, read-only operations tools."""

from decimal import Decimal

import pytest

from operations_agent.models.tools import (
    AccountStatus,
    TicketPriority,
    TicketStatus,
    TransactionStatus,
)
from operations_agent.tools import (
    get_customer,
    get_support_tickets,
    get_transactions,
    list_customers,
    search_knowledge_base,
)


@pytest.mark.parametrize("invalid_id", [0, -104, "104", None, True])
def test_get_customer_returns_typed_error_for_invalid_customer_id(invalid_id: object) -> None:
    """Customer lookup rejects invalid identifiers without raising."""
    result = get_customer(invalid_id)  # type: ignore[arg-type]

    assert result.customer is None
    assert result.customer_id is None
    assert result.error is not None
    assert result.error.code == "invalid_customer_id"


def test_get_customer_returns_customer_104_profile() -> None:
    """Customer 104 provides the account-level risk signal."""
    result = get_customer(104)

    assert result.error is None
    assert result.customer is not None
    assert result.customer.company_name == "Northstar Analytics"
    assert result.customer.account_status is AccountStatus.PAST_DUE
    assert result.customer.monthly_recurring_revenue == Decimal("1200.00")


def test_get_customer_returns_not_found_for_unknown_customer() -> None:
    """Unknown valid identifiers produce a recoverable lookup error."""
    result = get_customer(999)

    assert result.customer is None
    assert result.customer_id == 999
    assert result.error is not None
    assert result.error.code == "customer_not_found"


def test_get_customer_returns_sparse_valid_customer_for_insufficient_data_scenario() -> None:
    """Customer 107 exists but has only limited profile information available."""
    result = get_customer(107)

    assert result.error is None
    assert result.customer is not None
    assert result.customer.last_login_at is None


def test_get_transactions_returns_churn_relevant_history_for_customer_104() -> None:
    """Customer 104 has a recent failed renewal payment and service credit."""
    result = get_transactions(104)

    assert result.error is None
    assert [transaction.status for transaction in result.transactions] == [
        TransactionStatus.FAILED,
        TransactionStatus.SUCCEEDED,
        TransactionStatus.REFUNDED,
    ]
    assert result.transactions[0].failure_reason == "Card declined by issuing bank"
    assert result.transactions[0].occurred_on > result.transactions[-1].occurred_on


def test_get_transactions_handles_unknown_customer() -> None:
    """Transaction retrieval returns a structured error for unknown customers."""
    result = get_transactions(999)

    assert result.transactions == ()
    assert result.error is not None
    assert result.error.code == "customer_not_found"


def test_get_support_tickets_returns_open_high_priority_issue_for_customer_104() -> None:
    """Customer 104 has an unresolved reporting reliability issue."""
    result = get_support_tickets(104)

    assert result.error is None
    assert len(result.tickets) == 3
    assert result.tickets[0].status is TicketStatus.OPEN
    assert result.tickets[0].priority is TicketPriority.HIGH
    assert result.tickets[0].category == "reporting reliability"


def test_get_support_tickets_handles_invalid_customer_id() -> None:
    """Ticket retrieval returns a typed validation error rather than raising."""
    result = get_support_tickets(0)

    assert result.tickets == ()
    assert result.customer_id is None
    assert result.error is not None
    assert result.error.code == "invalid_customer_id"


def test_search_knowledge_base_returns_ranked_reporting_guidance() -> None:
    """Knowledge search finds the incident playbook for a reporting issue."""
    result = search_knowledge_base("reporting reliability incident")

    assert result.error is None
    assert result.matches
    assert result.matches[0].article.article_id == "KB-187"
    assert result.matches[0].relevance_score == pytest.approx(1.0)


def test_search_knowledge_base_returns_empty_matches_for_unknown_topic() -> None:
    """A valid unmatched query has no error and no fabricated guidance."""
    result = search_knowledge_base("quantum gardening")

    assert result.error is None
    assert result.matches == ()


@pytest.mark.parametrize("invalid_query", ["", "   ", None, 104])
def test_search_knowledge_base_handles_invalid_queries(invalid_query: object) -> None:
    """Knowledge search rejects malformed query input without raising."""
    result = search_knowledge_base(invalid_query)  # type: ignore[arg-type]

    assert result.matches == ()
    assert result.error is not None
    assert result.error.code == "invalid_query"


def test_list_customers_returns_full_directory_and_filters() -> None:
    """Directory listing aggregates all accounts, total MRR, and supports filters."""
    all_customers = list_customers()
    assert all_customers.error is None
    assert all_customers.total_count >= 4
    assert all_customers.total_mrr >= Decimal("7299.00")
    assert len(all_customers.customers) >= 4

    # Test segment filter
    enterprise = list_customers(segment="enterprise")
    assert enterprise.total_count >= 1
    assert any(c.company_name == "Cedar Health Partners" for c in enterprise.customers)

    # Test status filter
    past_due = list_customers(status="past_due")
    assert past_due.total_count >= 1
    assert any(c.customer_id == 104 for c in past_due.customers)


def test_enterprise_tools_lookup_and_anomaly_detection() -> None:
    """Test customer summary, invoices, usage, interactions, churn risk, and anomaly detection."""
    from operations_agent.tools import (
        calculate_churn_risk,
        detect_usage_anomaly,
        get_customer_interactions,
        get_customer_summary,
        get_invoices,
        get_usage_metrics,
    )

    # 1. Customer Summary
    summary_104 = get_customer_summary(104)
    assert summary_104.error is None
    assert summary_104.customer is not None
    assert summary_104.customer.company_name == "Northstar Analytics"

    # 2. Invoices
    inv_104 = get_invoices(104)
    assert inv_104.error is None

    # 3. Usage Metrics
    usage_104 = get_usage_metrics(104)
    assert usage_104.error is None

    # 4. Customer Interactions
    interactions_104 = get_customer_interactions(104)
    assert interactions_104.error is None

    # 5. Churn Risk Calculation
    churn_104 = calculate_churn_risk(104)
    assert churn_104.error is None
    assert churn_104.risk_level in {"high", "medium", "critical"}
    assert churn_104.churn_probability > 0.30

    # 6. Usage Anomaly Detection
    anomaly = detect_usage_anomaly(104)
    assert anomaly.error is None


