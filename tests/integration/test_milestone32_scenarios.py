"""Integration tests for Milestone 32 synthetic enterprise investigation scenarios."""

from operations_agent.data.scenarios import DEMO_SCENARIOS, get_scenario_for_customer
from operations_agent.services.agent_service import run_multi_agent_investigation_service


def test_scenario_a_customer_104_high_churn_risk() -> None:
    """Test A: Maya Chen / Northstar Analytics exhibits multi-factor churn risk."""
    scenario = get_scenario_for_customer(104)
    assert scenario is not None

    result = run_multi_agent_investigation_service(
        "Investigate customer 104 and determine whether they are at risk of churn."
    )
    assert result.status == "completed"
    assert len(result.execution_trace) >= 15
    assert "past due" in result.findings.findings.lower() or "104" in result.findings.findings
    assert "retention" in result.recommendation.lower()
    assert any(e.event_type == "APPROVAL_REQUESTED" for e in result.execution_trace)


def test_scenario_b_customer_207_revenue_decline() -> None:
    """Test B: Customer 207 revenue contraction and payment friction."""
    scenario = get_scenario_for_customer(207)
    assert scenario is not None
    assert scenario.customer_id == 207

    result = run_multi_agent_investigation_service(
        "Investigate customer 207 and determine why their revenue has declined."
    )
    assert result.status == "completed"
    assert "207" in result.findings.findings
    assert result.execution_trace[-1].event_type == "FINAL_RESULT"


def test_scenario_c_customer_318_usage_decline() -> None:
    """Test C: Customer 318 genuine usage decline investigation."""
    scenario = get_scenario_for_customer(318)
    assert scenario is not None
    assert scenario.customer_id == 318

    result = run_multi_agent_investigation_service(
        "Investigate customer 318 and determine whether their recent usage decline represents a genuine churn risk."
    )
    assert result.status == "completed"
    assert "318" in result.findings.findings
    assert result.execution_trace[-1].event_type == "FINAL_RESULT"


def test_scenario_d_customer_421_support_escalation() -> None:
    """Test D: Customer 421 unresolved critical security ticket escalation."""
    scenario = get_scenario_for_customer(421)
    assert scenario is not None
    assert scenario.customer_id == 421

    result = run_multi_agent_investigation_service(
        "Investigate customer 421 and determine whether there is an unresolved support issue that requires escalation."
    )
    assert result.status == "completed"
    assert "421" in result.findings.findings


def test_scenario_e_customer_512_operational_action_review() -> None:
    """Test E: Customer 512 healthy account operational review requiring no action."""
    scenario = get_scenario_for_customer(512)
    assert scenario is not None
    assert scenario.customer_id == 512

    result = run_multi_agent_investigation_service(
        "Review customer 512 and determine whether any operational action is required."
    )
    assert result.status == "completed"
    assert "512" in result.findings.findings
    assert "good standing" in result.findings.findings.lower() or "healthy" in result.findings.findings.lower() or "active" in result.findings.findings.lower()
    assert "no intervention" in result.recommendation.lower() or "continue standard" in result.recommendation.lower() or "monitoring" in result.recommendation.lower()
