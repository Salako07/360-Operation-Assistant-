"""Read-only accessors over the prototype's in-memory business data."""

import re

from operations_agent.data.mock_data import (
    CUSTOMERS,
    KNOWLEDGE_BASE_ARTICLES,
    SUPPORT_TICKETS,
    TRANSACTIONS,
)
from operations_agent.models.tools import (
    CustomerResult,
    KnowledgeBaseMatch,
    KnowledgeBaseSearchResult,
    SupportTicketsResult,
    ToolError,
    TransactionsResult,
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
    """Retrieve one customer profile by ID from the local customer directory.

    The tool is read-only. Unknown or invalid IDs return a typed error rather than
    raising an exception.
    """
    error = _customer_id_error(customer_id)
    if error:
        return CustomerResult(customer_id=None, error=error)

    customer = CUSTOMERS.get(customer_id)
    if customer is None:
        return CustomerResult(
            customer_id=customer_id,
            error=ToolError(
                code="customer_not_found",
                message=f"No customer exists with ID {customer_id}.",
            ),
        )
    return CustomerResult(customer_id=customer_id, customer=customer)


def get_transactions(customer_id: int) -> TransactionsResult:
    """Retrieve all locally available billing transactions for one customer.

    Results are ordered from newest to oldest. Unknown or invalid customer IDs
    return a typed error and an empty transaction collection.
    """
    error = _customer_id_error(customer_id)
    if error:
        return TransactionsResult(customer_id=None, error=error)
    if customer_id not in CUSTOMERS:
        return TransactionsResult(
            customer_id=customer_id,
            error=ToolError(
                code="customer_not_found",
                message=f"No customer exists with ID {customer_id}.",
            ),
        )

    transactions = tuple(
        transaction
        for transaction in TRANSACTIONS
        if transaction.customer_id == customer_id
    )
    return TransactionsResult(customer_id=customer_id, transactions=transactions)


def get_support_tickets(customer_id: int) -> SupportTicketsResult:
    """Retrieve all locally available support tickets for one customer.

    Results are ordered from most recently created to oldest. Unknown or invalid
    customer IDs return a typed error and an empty ticket collection.
    """
    error = _customer_id_error(customer_id)
    if error:
        return SupportTicketsResult(customer_id=None, error=error)
    if customer_id not in CUSTOMERS:
        return SupportTicketsResult(
            customer_id=customer_id,
            error=ToolError(
                code="customer_not_found",
                message=f"No customer exists with ID {customer_id}.",
            ),
        )

    tickets = tuple(ticket for ticket in SUPPORT_TICKETS if ticket.customer_id == customer_id)
    return SupportTicketsResult(customer_id=customer_id, tickets=tickets)


def _tokenize(value: str) -> set[str]:
    """Normalize text into lexical search tokens."""
    return set(_TOKEN_PATTERN.findall(value.lower()))


def search_knowledge_base(query: str) -> KnowledgeBaseSearchResult:
    """Search approved local knowledge-base articles using deterministic token overlap.

    Matching considers article titles, summaries, and tags. Blank or non-string
    queries return a typed error; unmatched valid queries return an empty result.
    """
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
    for article in KNOWLEDGE_BASE_ARTICLES:
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
