"""Structured audit events and privacy-aware logging for operations workflows."""

import json
import logging
from collections.abc import Mapping
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

logger = logging.getLogger(__name__)

_SENSITIVE_FIELD_FRAGMENTS = (
    "api_key",
    "authorization",
    "password",
    "secret",
    "token",
    "email",
)
_REDACTED_VALUE = "[REDACTED]"


class AuditEvent(BaseModel):
    """One ordered, privacy-aware event emitted during an application request."""

    model_config = ConfigDict(frozen=True)

    request_id: str
    sequence: int = Field(ge=1)
    occurred_at: datetime
    event_type: str
    details: dict[str, Any]


class TraceEventType(StrEnum):
    """Event types representing multi-agent execution and orchestration steps."""

    OBJECTIVE_RECEIVED = "OBJECTIVE_RECEIVED"
    SUPERVISOR_DECISION = "SUPERVISOR_DECISION"
    AGENT_DELEGATION = "AGENT_DELEGATION"
    AGENT_EXECUTION = "AGENT_EXECUTION"
    TOOL_EXECUTION = "TOOL_EXECUTION"
    AGENT_RESULT = "AGENT_RESULT"
    EVIDENCE_AGGREGATION = "EVIDENCE_AGGREGATION"
    ROUTING_DECISION = "ROUTING_DECISION"
    APPROVAL_REQUESTED = "APPROVAL_REQUESTED"
    APPROVAL_OUTCOME = "APPROVAL_OUTCOME"
    FINAL_SYNTHESIS = "FINAL_SYNTHESIS"
    PLAN_CREATED = "PLAN_CREATED"
    PLAN_UPDATED = "PLAN_UPDATED"
    TOOL_STARTED = "TOOL_STARTED"
    TOOL_COMPLETED = "TOOL_COMPLETED"
    AGENT_DECISION = "AGENT_DECISION"
    ERROR = "ERROR"
    FINAL_RESULT = "FINAL_RESULT"


class ExecutionTraceEvent(BaseModel):
    """Safe stakeholder-facing event describing agent progress, not private reasoning."""

    model_config = ConfigDict(frozen=True)

    execution_id: str = ""
    timestamp: datetime
    event_type: str
    agent_name: str | None = None
    tool_name: str | None = None
    status: str
    summary: str
    node_name: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


def create_execution_trace_event(
    event_type: str | TraceEventType,
    node_name: str = "",
    status: str = "completed",
    summary: str = "",
    metadata: Mapping[str, Any] | None = None,
    *,
    execution_id: str = "",
    agent_name: str | None = None,
    tool_name: str | None = None,
    timestamp: datetime | None = None,
) -> ExecutionTraceEvent:
    """Create a redacted, human-readable execution event safe for API consumers."""
    resolved_type = event_type.value if isinstance(event_type, TraceEventType) else str(event_type)
    return ExecutionTraceEvent(
        execution_id=execution_id,
        timestamp=timestamp or datetime.now(UTC),
        event_type=resolved_type,
        agent_name=agent_name,
        tool_name=tool_name,
        status=status,
        summary=summary,
        node_name=node_name or agent_name or "",
        metadata=redact_sensitive_data(dict(metadata or {})),
    )


def create_supervisor_decision_event(
    execution_id: str,
    summary: str,
    status: str = "decided",
    agent_name: str = "supervisor",
    metadata: Mapping[str, Any] | None = None,
) -> ExecutionTraceEvent:
    """Create a trace event recording a high-level supervisor decision."""
    return create_execution_trace_event(
        event_type=TraceEventType.SUPERVISOR_DECISION,
        node_name=agent_name,
        status=status,
        summary=summary,
        metadata=metadata,
        execution_id=execution_id,
        agent_name=agent_name,
    )


def create_agent_delegation_event(
    execution_id: str,
    target_agent: str,
    task_summary: str,
    supervisor_name: str = "supervisor",
    status: str = "delegated",
    metadata: Mapping[str, Any] | None = None,
) -> ExecutionTraceEvent:
    """Create a trace event recording a supervisor delegating a task to a specialized agent."""
    details = dict(metadata or {})
    details["target_agent"] = target_agent
    return create_execution_trace_event(
        event_type=TraceEventType.AGENT_DELEGATION,
        node_name=supervisor_name,
        status=status,
        summary=f"Delegated to {target_agent}: {task_summary}",
        metadata=details,
        execution_id=execution_id,
        agent_name=supervisor_name,
    )


def create_agent_execution_event(
    execution_id: str,
    agent_name: str,
    status: str = "started",
    summary: str = "",
    metadata: Mapping[str, Any] | None = None,
) -> ExecutionTraceEvent:
    """Create a trace event recording the execution of a specialized agent."""
    return create_execution_trace_event(
        event_type=TraceEventType.AGENT_EXECUTION,
        node_name=agent_name,
        status=status,
        summary=summary or f"Agent {agent_name} is actively executing task.",
        metadata=metadata,
        execution_id=execution_id,
        agent_name=agent_name,
    )


def create_tool_execution_event(
    execution_id: str,
    tool_name: str,
    status: str = "executed",
    summary: str = "",
    agent_name: str | None = None,
    metadata: Mapping[str, Any] | None = None,
) -> ExecutionTraceEvent:
    """Create a trace event recording tool invocation and execution."""
    return create_execution_trace_event(
        event_type=TraceEventType.TOOL_EXECUTION,
        node_name=agent_name or tool_name,
        status=status,
        summary=summary or f"Executed tool {tool_name}.",
        metadata=metadata,
        execution_id=execution_id,
        agent_name=agent_name,
        tool_name=tool_name,
    )


def create_agent_result_event(
    execution_id: str,
    agent_name: str,
    summary: str,
    status: str = "completed",
    metadata: Mapping[str, Any] | None = None,
) -> ExecutionTraceEvent:
    """Create a trace event recording the result returned by a specialized agent."""
    return create_execution_trace_event(
        event_type=TraceEventType.AGENT_RESULT,
        node_name=agent_name,
        status=status,
        summary=summary,
        metadata=metadata,
        execution_id=execution_id,
        agent_name=agent_name,
    )


def create_evidence_aggregation_event(
    execution_id: str,
    summary: str,
    agent_name: str = "supervisor",
    status: str = "aggregated",
    metadata: Mapping[str, Any] | None = None,
) -> ExecutionTraceEvent:
    """Create a trace event recording evidence consolidation across specialist agents."""
    return create_execution_trace_event(
        event_type=TraceEventType.EVIDENCE_AGGREGATION,
        node_name=agent_name,
        status=status,
        summary=summary,
        metadata=metadata,
        execution_id=execution_id,
        agent_name=agent_name,
    )


def create_routing_decision_event(
    execution_id: str,
    next_destination: str,
    summary: str,
    agent_name: str = "supervisor",
    status: str = "routed",
    metadata: Mapping[str, Any] | None = None,
) -> ExecutionTraceEvent:
    """Create a trace event recording a workflow routing decision."""
    details = dict(metadata or {})
    details["next_destination"] = next_destination
    return create_execution_trace_event(
        event_type=TraceEventType.ROUTING_DECISION,
        node_name=agent_name,
        status=status,
        summary=summary,
        metadata=details,
        execution_id=execution_id,
        agent_name=agent_name,
    )


def create_approval_request_event(
    execution_id: str,
    action_summary: str,
    customer_id: int,
    agent_name: str = "approval_gate",
    status: str = "pending",
    metadata: Mapping[str, Any] | None = None,
) -> ExecutionTraceEvent:
    """Create a trace event recording a human-approval request for a consequential action."""
    details = dict(metadata or {})
    details["customer_id"] = customer_id
    return create_execution_trace_event(
        event_type=TraceEventType.APPROVAL_REQUESTED,
        node_name=agent_name,
        status=status,
        summary=f"Human approval requested for customer {customer_id}: {action_summary}",
        metadata=details,
        execution_id=execution_id,
        agent_name=agent_name,
    )


def create_approval_outcome_event(
    execution_id: str,
    decision: str,
    reviewer_id: str | None = None,
    status: str = "decided",
    summary: str = "",
    agent_name: str = "approval_gate",
    metadata: Mapping[str, Any] | None = None,
) -> ExecutionTraceEvent:
    """Create a trace event recording the human approval review decision."""
    details = dict(metadata or {})
    details["decision"] = decision
    if reviewer_id:
        details["reviewer_id"] = reviewer_id
    return create_execution_trace_event(
        event_type=TraceEventType.APPROVAL_OUTCOME,
        node_name=agent_name,
        status=status,
        summary=summary or f"Human approval decision: {decision}.",
        metadata=details,
        execution_id=execution_id,
        agent_name=agent_name,
    )


def create_final_synthesis_event(
    execution_id: str,
    summary: str,
    agent_name: str = "supervisor",
    status: str = "synthesized",
    metadata: Mapping[str, Any] | None = None,
) -> ExecutionTraceEvent:
    """Create a trace event recording final evidence-based synthesis."""
    return create_execution_trace_event(
        event_type=TraceEventType.FINAL_SYNTHESIS,
        node_name=agent_name,
        status=status,
        summary=summary,
        metadata=metadata,
        execution_id=execution_id,
        agent_name=agent_name,
    )


def create_audit_event(
    request_id: str,
    sequence: int,
    event_type: str,
    details: Mapping[str, Any] | None = None,
) -> AuditEvent:
    """Create and emit one redacted JSON audit event."""
    event = AuditEvent(
        request_id=request_id,
        sequence=sequence,
        occurred_at=datetime.now(UTC),
        event_type=event_type,
        details=redact_sensitive_data(dict(details or {})),
    )
    logger.info("audit_event=%s", json.dumps(event.model_dump(mode="json"), sort_keys=True))
    return event


def redact_sensitive_data(value: Any) -> Any:
    """Recursively remove credential and email values before logging or tracing."""
    if isinstance(value, Mapping):
        return {
            str(key): (
                _REDACTED_VALUE
                if any(fragment in str(key).lower() for fragment in _SENSITIVE_FIELD_FRAGMENTS)
                else redact_sensitive_data(item)
            )
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [redact_sensitive_data(item) for item in value]
    return value


class AuditTrail:
    """Collect and log ordered audit events for one in-process request.

    Events remain in memory for this prototype and are returned to the caller.
    A later persistence adapter can consume the same `AuditEvent` contract.
    """

    def __init__(self, request_id: str) -> None:
        self._request_id = request_id
        self._events: list[AuditEvent] = []

    @property
    def events(self) -> tuple[AuditEvent, ...]:
        """Return the immutable chronological audit trace."""
        return tuple(self._events)

    def record(self, event_type: str, details: Mapping[str, Any] | None = None) -> AuditEvent:
        """Append one redacted event and emit it as a JSON log entry."""
        event = create_audit_event(
            self._request_id,
            len(self._events) + 1,
            event_type,
            details,
        )
        self._events.append(event)
        return event
