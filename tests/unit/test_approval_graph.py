"""Tests for the resumable human-in-the-loop approval workflow."""

from langgraph.types import Command

from operations_agent.graph.approval import (
    ApprovalState,
    ApprovalStatus,
    build_approval_graph,
    create_retention_outreach_proposal,
)
from operations_agent.graph.state import Observation, current_utc_time


def _initial_state() -> ApprovalState:
    """Create a pending proposal and evidence payload for one approval test."""
    observation = Observation(
        source="get_support_tickets",
        action_id="call_ticket_104",
        data={"ok": True, "result": {"ticket_id": "SUP-4821"}},
        observed_at=current_utc_time(),
    )
    proposal = create_retention_outreach_proposal((observation,))
    return {
        "proposed_action": proposal,
        "supporting_evidence": (observation,),
        "approval_status": ApprovalStatus.PENDING,
        "pending_approval_input": None,
        "approval_decision": None,
        "errors": [],
    }


def _config(thread_id: str) -> dict[str, dict[str, str]]:
    """Create an isolated LangGraph checkpoint thread configuration."""
    return {"configurable": {"thread_id": thread_id}}


def test_approval_pauses_then_records_approved_human_decision() -> None:
    """Only a valid human approval reaches the approved completion node."""
    graph = build_approval_graph()
    config = _config("approval-test")

    interrupted = graph.invoke(_initial_state(), config)
    final_state = graph.invoke(
        Command(resume={"decision": "approved", "reviewer_id": "ops-17"}),
        config,
    )

    assert "__interrupt__" in interrupted
    assert interrupted["__interrupt__"][0].value["proposed_action"]["customer_id"] == 104
    assert final_state["approval_status"] is ApprovalStatus.APPROVED
    assert final_state["approval_decision"].reviewer_id == "ops-17"
    assert final_state["proposed_action"].description == "Send a retention outreach to customer 104."


def test_rejection_records_decision_and_ends_without_execution() -> None:
    """Rejection is terminal and does not take the approved continuation path."""
    graph = build_approval_graph()
    config = _config("rejection-test")

    graph.invoke(_initial_state(), config)
    final_state = graph.invoke(
        Command(resume={"decision": "rejected", "reviewer_id": "ops-18", "comment": "Not now."}),
        config,
    )

    assert final_state["approval_status"] is ApprovalStatus.REJECTED
    assert final_state["approval_decision"].comment == "Not now."


def test_invalid_approval_is_recorded_and_pauses_for_corrected_decision() -> None:
    """Malformed approval input is visible in state and requires another review input."""
    graph = build_approval_graph()
    config = _config("invalid-test")

    graph.invoke(_initial_state(), config)
    interrupted = graph.invoke(Command(resume={"decision": "maybe"}), config)
    checkpoint_state = graph.get_state(config).values

    assert "__interrupt__" in interrupted
    assert checkpoint_state["approval_status"] is ApprovalStatus.INVALID
    assert checkpoint_state["approval_decision"].status is ApprovalStatus.INVALID
    assert checkpoint_state["errors"][0].code == "invalid_approval"


def test_cancellation_records_decision_and_ends_without_execution() -> None:
    """Cancellation is terminal and leaves the action purely advisory."""
    graph = build_approval_graph()
    config = _config("cancellation-test")

    graph.invoke(_initial_state(), config)
    final_state = graph.invoke(
        Command(resume={"decision": "cancelled", "reviewer_id": "ops-19"}),
        config,
    )

    assert final_state["approval_status"] is ApprovalStatus.CANCELLED
    assert final_state["approval_decision"].status is ApprovalStatus.CANCELLED
