"""Pydantic request and response contracts for the agent HTTP API."""

from operations_agent.graph.state import AgentStatus
from operations_agent.observability import ExecutionTraceEvent
from pydantic import BaseModel, ConfigDict, Field


class AgentRunRequest(BaseModel):
    """HTTP request used to start one customer investigation."""

    objective: str = Field(min_length=1, max_length=2_000)


class StructuredFindings(BaseModel):
    """Sections extracted from the agent's required final response format."""

    findings: str = ""
    evidence: str = ""
    likely_cause: str = ""
    uncertainty: str = ""


class ExecutionErrorSummary(BaseModel):
    """Safe public summary of an execution error."""

    code: str
    recoverable: bool


class ExecutionSummary(BaseModel):
    """Non-secret metadata describing one completed synchronous execution."""

    model_iterations: int = Field(ge=0)
    tool_actions: int = Field(ge=0)
    observations: int = Field(ge=0)
    plan_steps: int = Field(ge=0)
    errors: tuple[ExecutionErrorSummary, ...] = ()


class AgentRunResponse(BaseModel):
    """HTTP response containing the investigation output and execution summary."""

    model_config = ConfigDict(frozen=True)

    execution_id: str
    status: AgentStatus
    final_result: str
    findings: StructuredFindings
    recommendation: str
    execution_summary: ExecutionSummary
    execution_trace: tuple[ExecutionTraceEvent, ...]


class HealthResponse(BaseModel):
    """Health response for service monitoring."""

    status: str = "ok"
