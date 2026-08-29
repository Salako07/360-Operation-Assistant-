"""Contract tests for the Customer Churn Investigation evaluation suite."""

from operations_agent.evaluations import CHURN_EVALUATION_SCENARIOS
from operations_agent.evaluations.scenarios import ExpectedAssessment


def test_churn_evaluation_suite_covers_required_business_conditions() -> None:
    """The suite includes each required customer-investigation outcome."""
    assessments = {scenario.expected_assessment for scenario in CHURN_EVALUATION_SCENARIOS}

    assert assessments == {
        ExpectedAssessment.CHURN_RISK,
        ExpectedAssessment.INSUFFICIENT_INFORMATION,
        ExpectedAssessment.NO_APPARENT_CHURN_RISK,
        ExpectedAssessment.INVALID_CUSTOMER,
    }


def test_all_scenarios_require_the_structured_final_response_sections() -> None:
    """Every scenario evaluates the final response format expected by operations."""
    for scenario in CHURN_EVALUATION_SCENARIOS:
        assert scenario.required_final_sections == (
            "Findings:",
            "Evidence:",
            "Likely cause:",
            "Recommendation:",
            "Uncertainty:",
        )
