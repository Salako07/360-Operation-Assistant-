"""Integration test verifying end-to-end multi-agent execution and complete trace generation."""

from fastapi.testclient import TestClient
from operations_agent.api.main import create_app
from operations_agent.graph import (
    MultiAgentRunResult,
    run_multi_agent_investigation,
)
from operations_agent.graph.state import AgentStatus
from operations_agent.services.agent_service import run_multi_agent_investigation_service


def test_end_to_end_multi_agent_investigation_trace() -> None:
    """An end-to-end multi-agent investigation generates all expected trace event categories."""
    objective = "Investigate customer 104 and determine why they may be at risk of churn."
    request_id = "test-multi-e2e-104"

    result = run_multi_agent_investigation(
        objective=objective,
        request_id=request_id,
    )

    assert isinstance(result, MultiAgentRunResult)
    assert result.execution_id == request_id
    assert result.current_status is AgentStatus.COMPLETED
    assert len(result.execution_trace) >= 10

    # Verify each event has required fields populated
    for event in result.execution_trace:
        assert event.execution_id == request_id
        assert event.timestamp is not None
        assert event.event_type != ""
        assert event.status != ""
        assert event.summary != ""

    event_types = [event.event_type for event in result.execution_trace]

    # Verify all 10 multi-agent event categories are present:
    # 1. Supervisor decision
    assert "SUPERVISOR_DECISION" in event_types
    # 2. Agent delegation
    assert "AGENT_DELEGATION" in event_types
    # 3. Agent execution
    assert "AGENT_EXECUTION" in event_types
    # 4. Tool execution
    assert "TOOL_EXECUTION" in event_types
    # 5. Agent results
    assert "AGENT_RESULT" in event_types
    # 6. Evidence aggregation
    assert "EVIDENCE_AGGREGATION" in event_types
    # 7. Routing decisions
    assert "ROUTING_DECISION" in event_types
    # 8. Approval requests
    assert "APPROVAL_REQUESTED" in event_types
    # 9. Approval outcomes
    assert "APPROVAL_OUTCOME" in event_types
    # 10. Final synthesis
    assert "FINAL_SYNTHESIS" in event_types
    # Final result
    assert "FINAL_RESULT" in event_types

    # Verify specific agent names are present where applicable
    agents_in_trace = {event.agent_name for event in result.execution_trace if event.agent_name}
    assert "supervisor" in agents_in_trace
    assert "profile_specialist" in agents_in_trace
    assert "billing_specialist" in agents_in_trace
    assert "support_specialist" in agents_in_trace
    assert "approval_gate" in agents_in_trace

    # Verify tools in trace
    tools_in_trace = {event.tool_name for event in result.execution_trace if event.tool_name}
    assert "get_customer" in tools_in_trace
    assert "get_transactions" in tools_in_trace
    assert "get_support_tickets" in tools_in_trace

    # Verify structured final output
    assert "Findings:" in result.final_response
    assert "Evidence:" in result.final_response
    assert "Likely cause:" in result.final_response
    assert "Recommendation:" in result.final_response
    assert "Uncertainty:" in result.final_response


def test_multi_agent_investigation_api_integration() -> None:
    """The FastAPI API endpoint exposes the multi-agent execution trace contract."""
    client = TestClient(create_app(run_multi_agent_investigation_service))

    response = client.post(
        "/agent/run",
        json={"objective": "Investigate customer 104 and determine why they may be at risk of churn."},
    )

    assert response.status_code == 200
    payload = response.json()

    assert payload["status"] == "completed"
    assert payload["execution_id"] != ""
    assert "Findings" in payload["findings"]["findings"] or payload["findings"]["findings"] != ""
    assert "SUP-4821" in payload["findings"]["evidence"] or "ticket" in payload["findings"]["evidence"].lower()
    assert payload["execution_summary"]["tool_actions"] >= 3

    # Verify trace payload for frontend timeline reconstruction
    trace = payload["execution_trace"]
    assert len(trace) >= 10

    first_event = trace[0]
    assert "execution_id" in first_event
    assert "timestamp" in first_event
    assert "event_type" in first_event
    assert "agent_name" in first_event
    assert "tool_name" in first_event
    assert "status" in first_event
    assert "summary" in first_event
