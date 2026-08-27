"""Human approval subgraph for consequential customer-operations proposals."""

from enum import StrEnum
from operator import add
from typing import Annotated, Any, Literal, TypedDict
from uuid import uuid4
from datetime import datetime

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph
from langgraph.types import interrupt
from pydantic import BaseModel, ConfigDict, Field

from operations_agent.graph.state import Observation, current_utc_time


class ApprovalStatus(StrEnum):
    """Human-review state for a proposed consequential action."""

    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    CANCELLED = "cancelled"
    INVALID = "invalid"


class ProposedAction(BaseModel):
    """An advisory action that cannot execute without explicit human approval."""

    model_config = ConfigDict(frozen=True)

    action_id: str
    customer_id: int = Field(gt=0)
    description: str
    rationale: str
    supporting_observation_ids: tuple[str, ...]
    requires_human_approval: bool = True


class ApprovalInput(BaseModel):
    """Validated decision supplied when resuming an interrupted approval graph."""

    decision: Literal["approved", "rejected", "cancelled"]
    reviewer_id: str = Field(min_length=1, max_length=100)
    comment: str | None = Field(default=None, max_length=500)


class ApprovalDecision(BaseModel):
    """Persisted outcome of one approval review attempt."""

    model_config = ConfigDict(frozen=True)

    status: ApprovalStatus
    reviewer_id: str | None
    comment: str | None
    decided_at: datetime


class ApprovalError(BaseModel):
    """A malformed human decision retained for audit and correction."""

    model_config = ConfigDict(frozen=True)

    code: str
    message: str


class ApprovalState(TypedDict):
    """State for the pause, validation, and decision routing workflow."""

    proposed_action: ProposedAction
    supporting_evidence: tuple[Observation, ...]
    approval_status: ApprovalStatus
    pending_approval_input: Any | None
    approval_decision: ApprovalDecision | None
    errors: Annotated[list[ApprovalError], add]


def create_retention_outreach_proposal(
    observations: tuple[Observation, ...],
    customer_id: int = 104,
) -> ProposedAction:
    """Create the prototype's advisory retention-outreach action for customer 104."""
    if customer_id != 104:
        raise ValueError("The prototype retention outreach action is only defined for customer 104.")
    return ProposedAction(
        action_id=str(uuid4()),
        customer_id=customer_id,
        description="Send a retention outreach to customer 104.",
        rationale="The investigation identified potential churn risk requiring human review.",
        supporting_observation_ids=tuple(observation.action_id for observation in observations),
    )


def build_approval_graph() -> CompiledStateGraph:
    """Build a resumable approval graph that never sends the proposed outreach."""

    def await_approval(state: ApprovalState) -> dict[str, object]:
        """Pause and expose the action plus its supporting evidence to a reviewer."""
        decision_input = interrupt(
            {
                "proposed_action": state["proposed_action"].model_dump(mode="json"),
                "supporting_evidence": [
                    observation.model_dump(mode="json") for observation in state["supporting_evidence"]
                ],
            }
        )
        return {"pending_approval_input": decision_input}

    def validate_approval(state: ApprovalState) -> dict[str, object]:
        """Validate a resumed human decision and record valid or invalid outcomes."""
        try:
            decision = ApprovalInput.model_validate(state["pending_approval_input"])
        except ValueError as error:
            return {
                "approval_status": ApprovalStatus.INVALID,
                "approval_decision": ApprovalDecision(
                    status=ApprovalStatus.INVALID,
                    reviewer_id=None,
                    comment=None,
                    decided_at=current_utc_time(),
                ),
                "errors": [ApprovalError(code="invalid_approval", message=str(error))],
            }

        status = ApprovalStatus(decision.decision)
        return {
            "approval_status": status,
            "approval_decision": ApprovalDecision(
                status=status,
                reviewer_id=decision.reviewer_id,
                comment=decision.comment,
                decided_at=current_utc_time(),
            ),
        }

    def approval_complete(state: ApprovalState) -> dict[str, object]:
        """Complete an approved review without executing the requested action."""
        del state
        return {"approval_status": ApprovalStatus.APPROVED}

    def route_after_validation(state: ApprovalState) -> Literal["await_approval", "approved", "__end__"]:
        """Pause again for invalid input, continue only for approval, otherwise end."""
        if state["approval_status"] is ApprovalStatus.INVALID:
            return "await_approval"
        if state["approval_status"] is ApprovalStatus.APPROVED:
            return "approved"
        return END

    graph = StateGraph(ApprovalState)
    graph.add_node("await_approval", await_approval)
    graph.add_node("validate_approval", validate_approval)
    graph.add_node("approved", approval_complete)
    graph.add_edge(START, "await_approval")
    graph.add_edge("await_approval", "validate_approval")
    graph.add_conditional_edges(
        "validate_approval",
        route_after_validation,
        {"await_approval": "await_approval", "approved": "approved", END: END},
    )
    graph.add_edge("approved", END)
    return graph.compile(checkpointer=InMemorySaver())
