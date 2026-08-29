"""Unit tests for multi-agent execution tracing and event schema compliance."""

from datetime import UTC, datetime
from operations_agent.observability import (
    ExecutionTraceEvent,
    TraceEventType,
    create_agent_delegation_event,
    create_agent_execution_event,
    create_agent_result_event,
    create_approval_outcome_event,
    create_approval_request_event,
    create_evidence_aggregation_event,
    create_execution_trace_event,
    create_final_synthesis_event,
    create_routing_decision_event,
    create_supervisor_decision_event,
    create_tool_execution_event,
    redact_sensitive_data,
)


def test_execution_trace_event_schema_has_all_required_fields() -> None:
    """ExecutionTraceEvent requires execution_id, timestamp, event_type, agent_name, tool_name, status, and summary."""
    now = datetime.now(UTC)
    event = ExecutionTraceEvent(
        execution_id="exec-123",
        timestamp=now,
        event_type=TraceEventType.SUPERVISOR_DECISION,
        agent_name="supervisor",
        tool_name=None,
        status="decided",
        summary="Supervisor decided investigation plan.",
        metadata={"step": 1},
    )

    assert event.execution_id == "exec-123"
    assert event.timestamp == now
    assert event.event_type == "SUPERVISOR_DECISION"
    assert event.agent_name == "supervisor"
    assert event.tool_name is None
    assert event.status == "decided"
    assert event.summary == "Supervisor decided investigation plan."
    assert event.metadata == {"step": 1}


def test_all_multi_agent_trace_event_types_can_be_created() -> None:
    """Every multi-agent lifecycle phase produces a valid ExecutionTraceEvent."""
    exec_id = "exec-multi-456"

    # 1. Supervisor decision
    e_sup = create_supervisor_decision_event(
        execution_id=exec_id,
        summary="Supervisor evaluated customer churn risk objective.",
        agent_name="supervisor",
        status="decided",
    )
    assert e_sup.event_type == "SUPERVISOR_DECISION"
    assert e_sup.agent_name == "supervisor"
    assert e_sup.execution_id == exec_id

    # 2. Agent delegation
    e_del = create_agent_delegation_event(
        execution_id=exec_id,
        target_agent="billing_specialist",
        task_summary="Analyze recent billing transactions and failures.",
        supervisor_name="supervisor",
        status="delegated",
    )
    assert e_del.event_type == "AGENT_DELEGATION"
    assert e_del.agent_name == "supervisor"
    assert "billing_specialist" in e_del.summary
    assert e_del.metadata["target_agent"] == "billing_specialist"

    # 3. Agent execution
    e_exec = create_agent_execution_event(
        execution_id=exec_id,
        agent_name="billing_specialist",
        status="started",
        summary="Billing Specialist started ledger analysis.",
    )
    assert e_exec.event_type == "AGENT_EXECUTION"
    assert e_exec.agent_name == "billing_specialist"
    assert e_exec.status == "started"

    # 4. Tool execution
    e_tool = create_tool_execution_event(
        execution_id=exec_id,
        tool_name="get_transactions",
        status="completed",
        summary="Completed tool get_transactions with success result.",
        agent_name="billing_specialist",
    )
    assert e_tool.event_type == "TOOL_EXECUTION"
    assert e_tool.agent_name == "billing_specialist"
    assert e_tool.tool_name == "get_transactions"

    # 5. Agent result
    e_res = create_agent_result_event(
        execution_id=exec_id,
        agent_name="billing_specialist",
        summary="Found 1 failed renewal payment and 1 refund.",
        status="completed",
    )
    assert e_res.event_type == "AGENT_RESULT"
    assert e_res.agent_name == "billing_specialist"

    # 6. Evidence aggregation
    e_agg = create_evidence_aggregation_event(
        execution_id=exec_id,
        summary="Consolidated multi-agent findings across profile, billing, and support.",
        agent_name="supervisor",
        status="aggregated",
    )
    assert e_agg.event_type == "EVIDENCE_AGGREGATION"
    assert e_agg.agent_name == "supervisor"

    # 7. Routing decision
    e_route = create_routing_decision_event(
        execution_id=exec_id,
        next_destination="approval_gate",
        summary="Routing to approval_gate for consequential action review.",
        agent_name="supervisor",
        status="routed",
    )
    assert e_route.event_type == "ROUTING_DECISION"
    assert e_route.metadata["next_destination"] == "approval_gate"

    # 8. Approval request
    e_app_req = create_approval_request_event(
        execution_id=exec_id,
        action_summary="Send retention outreach to customer 104.",
        customer_id=104,
        agent_name="approval_gate",
        status="pending",
    )
    assert e_app_req.event_type == "APPROVAL_REQUESTED"
    assert e_app_req.agent_name == "approval_gate"
    assert e_app_req.metadata["customer_id"] == 104

    # 9. Approval outcome
    e_app_out = create_approval_outcome_event(
        execution_id=exec_id,
        decision="approved",
        reviewer_id="ops-lead-01",
        status="approved",
        summary="Human operator approved the outreach action.",
        agent_name="approval_gate",
    )
    assert e_app_out.event_type == "APPROVAL_OUTCOME"
    assert e_app_out.metadata["decision"] == "approved"
    assert e_app_out.metadata["reviewer_id"] == "ops-lead-01"

    # 10. Final synthesis
    e_synth = create_final_synthesis_event(
        execution_id=exec_id,
        summary="Supervisor finalized churn risk recommendation and uncertainty analysis.",
        agent_name="supervisor",
        status="synthesized",
    )
    assert e_synth.event_type == "FINAL_SYNTHESIS"
    assert e_synth.agent_name == "supervisor"


def test_trace_events_do_not_expose_private_chain_of_thought_or_credentials() -> None:
    """Trace events redact sensitive tokens and only carry safe summaries."""
    event = create_tool_execution_event(
        execution_id="exec-safe",
        tool_name="get_customer",
        status="completed",
        summary="Retrieved customer account standing.",
        agent_name="profile_specialist",
        metadata={
            "api_key": "super-secret-key",
            "email": "customer@example.com",
            "safe_metric": 42,
        },
    )

    assert event.metadata["api_key"] == "[REDACTED]"
    assert event.metadata["email"] == "[REDACTED]"
    assert event.metadata["safe_metric"] == 42
    assert "super-secret-key" not in event.summary
