"""Typed state carried through the LangGraph tool-calling workflow."""

from datetime import UTC, datetime
from enum import StrEnum
from operator import add
from typing import Annotated, Any, TypedDict

from langchain_core.messages import AnyMessage
from langgraph.graph import add_messages
from pydantic import BaseModel, ConfigDict

from operations_agent.observability import AuditEvent, ExecutionTraceEvent


class AgentStatus(StrEnum):
    """Lifecycle states for one customer-churn investigation."""

    INVESTIGATING = "investigating"
    COMPLETED = "completed"
    LIMIT_REACHED = "limit_reached"
    FAILED = "failed"


class ActionStatus(StrEnum):
    """Outcome of an attempted tool action."""

    EXECUTED = "executed"
    FAILED = "failed"
    SKIPPED_DUPLICATE = "skipped_duplicate"
    SKIPPED_REPEATED_FAILURE = "skipped_repeated_failure"
    SKIPPED_LIMIT = "skipped_limit"


class PlanStepStatus(StrEnum):
    """Lifecycle status for one planned information-gathering step."""

    PENDING = "pending"
    COMPLETED = "completed"
    FAILED = "failed"
    NOT_NEEDED = "not_needed"


class ErrorCategory(StrEnum):
    """Failure domains that can occur during an investigation."""

    LLM = "llm"
    TOOL = "tool"
    VALIDATION = "validation"
    LIMIT = "limit"


class AgentError(BaseModel):
    """A recoverable or terminal error retained in the investigation state."""

    model_config = ConfigDict(frozen=True)

    category: ErrorCategory
    code: str
    message: str
    recoverable: bool
    occurred_at: datetime


class PlanStep(BaseModel):
    """A structured investigation step selected by the single LLM agent."""

    model_config = ConfigDict(frozen=True)

    step_id: str
    description: str
    tool_name: str
    arguments: dict[str, Any]
    status: PlanStepStatus
    result: dict[str, Any] | None = None


class CompletedAction(BaseModel):
    """An immutable record of a tool call attempted during an investigation."""

    model_config = ConfigDict(frozen=True)

    tool_call_id: str
    tool_name: str
    arguments: dict[str, Any]
    status: ActionStatus
    result: dict[str, Any]
    completed_at: datetime


class Observation(BaseModel):
    """Structured information observed from an executed or guarded tool call."""

    model_config = ConfigDict(frozen=True)

    source: str
    action_id: str
    data: dict[str, Any]
    observed_at: datetime


class FinalResult(BaseModel):
    """The terminal assistant result retained independently from chat history."""

    model_config = ConfigDict(frozen=True)

    response: str
    status: AgentStatus
    completed_at: datetime


def current_utc_time() -> datetime:
    """Return a timezone-aware timestamp for execution-state records."""
    return datetime.now(UTC)


class ToolCallingAgentState(TypedDict):
    """Explicit execution state shared by customer-churn graph nodes."""

    objective: str
    messages: Annotated[list[AnyMessage], add_messages]
    current_status: AgentStatus
    plan: list[PlanStep]
    completed_actions: Annotated[list[CompletedAction], add]
    observations: Annotated[list[Observation], add]
    final_result: FinalResult | None
    errors: Annotated[list[AgentError], add]
    iterations: int
    request_id: str
    audit_events: Annotated[list[AuditEvent], add]
    execution_trace: Annotated[list[ExecutionTraceEvent], add]
