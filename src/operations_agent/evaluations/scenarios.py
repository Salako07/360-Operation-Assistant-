"""Static evaluation scenarios for manual or automated model quality checks."""

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class ExpectedAssessment(StrEnum):
    """Expected high-level conclusion for an evaluation scenario."""

    CHURN_RISK = "churn_risk"
    INSUFFICIENT_INFORMATION = "insufficient_information"
    NO_APPARENT_CHURN_RISK = "no_apparent_churn_risk"
    INVALID_CUSTOMER = "invalid_customer"


class EvaluationScenario(BaseModel):
    """A bounded scenario and the human-review expectations for its response."""

    model_config = ConfigDict(frozen=True)

    scenario_id: str
    objective: str
    expected_assessment: ExpectedAssessment
    minimum_expected_tools: tuple[str, ...] = ()
    expected_evidence: tuple[str, ...] = ()
    required_final_sections: tuple[str, ...] = Field(
        default=("Findings:", "Evidence:", "Likely cause:", "Recommendation:", "Uncertainty:")
    )


CHURN_EVALUATION_SCENARIOS: tuple[EvaluationScenario, ...] = (
    EvaluationScenario(
        scenario_id="customer-104-churn-risk",
        objective=(
            "Investigate customer 104 and determine why they may be at risk of churn. "
            "Provide an evidence-based recommendation."
        ),
        expected_assessment=ExpectedAssessment.CHURN_RISK,
        minimum_expected_tools=("get_customer", "get_transactions", "get_support_tickets"),
        expected_evidence=(
            "past_due",
            "Card declined by issuing bank",
            "SUP-4821",
        ),
    ),
    EvaluationScenario(
        scenario_id="customer-107-insufficient-information",
        objective=(
            "Investigate customer 107 for churn risk. Explain whether the available "
            "information is sufficient for a recommendation."
        ),
        expected_assessment=ExpectedAssessment.INSUFFICIENT_INFORMATION,
        minimum_expected_tools=("get_customer", "get_transactions", "get_support_tickets"),
        expected_evidence=("no transaction", "no support"),
    ),
    EvaluationScenario(
        scenario_id="customer-105-no-apparent-risk",
        objective="Investigate customer 105 for churn risk and provide an evidence-based recommendation.",
        expected_assessment=ExpectedAssessment.NO_APPARENT_CHURN_RISK,
        minimum_expected_tools=("get_customer", "get_transactions", "get_support_tickets"),
        expected_evidence=("active", "succeeded", "SUP-4802"),
    ),
    EvaluationScenario(
        scenario_id="invalid-customer-id",
        objective="Investigate customer 999 for churn risk and provide an evidence-based recommendation.",
        expected_assessment=ExpectedAssessment.INVALID_CUSTOMER,
        minimum_expected_tools=("get_customer",),
        expected_evidence=("customer_not_found",),
    ),
)
