"""Tests for the Customer Churn Investigation Agent role prompt."""

from operations_agent.prompts import CUSTOMER_CHURN_INVESTIGATION_PROMPT


def test_churn_agent_prompt_defines_role_tools_and_autonomy_boundaries() -> None:
    """The role prompt directs investigation without prescribing a fixed sequence."""
    assert "Customer Churn Investigation Agent" in CUSTOMER_CHURN_INVESTIGATION_PROMPT
    assert "There is no required tool sequence" in CUSTOMER_CHURN_INVESTIGATION_PROMPT
    assert "get_customer(customer_id)" in CUSTOMER_CHURN_INVESTIGATION_PROMPT
    assert "get_transactions(customer_id)" in CUSTOMER_CHURN_INVESTIGATION_PROMPT
    assert "get_support_tickets(customer_id)" in CUSTOMER_CHURN_INVESTIGATION_PROMPT
    assert "search_knowledge_base(query)" in CUSTOMER_CHURN_INVESTIGATION_PROMPT
    assert "Do not modify data" in CUSTOMER_CHURN_INVESTIGATION_PROMPT


def test_churn_agent_prompt_requires_structured_evidence_based_final_response() -> None:
    """Final answers must separate facts, inference, recommendation, and uncertainty."""
    for section in ("Findings:", "Evidence:", "Likely cause:", "Recommendation:", "Uncertainty:"):
        assert section in CUSTOMER_CHURN_INVESTIGATION_PROMPT