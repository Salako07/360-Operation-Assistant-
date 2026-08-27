"""Application service that runs the LangGraph agent for API callers."""

import re
from uuid import uuid4

from operations_agent.api.models import (
    AgentRunResponse,
    ExecutionErrorSummary,
    ExecutionSummary,
    StructuredFindings,
)
from operations_agent.graph import run_tool_calling_graph
from operations_agent.services.model_factory import create_chat_model

_SECTION_PATTERN = re.compile(
    r"^(Findings|Evidence|Likely cause|Recommendation|Uncertainty):\s*(.*?)(?=^(?:Findings|Evidence|Likely cause|Recommendation|Uncertainty):|\Z)",
    re.IGNORECASE | re.MULTILINE | re.DOTALL,
)


def _extract_sections(response: str) -> dict[str, str]:
    """Extract required labelled response sections without relying on model internals."""
    return {name.lower(): content.strip() for name, content in _SECTION_PATTERN.findall(response)}


def run_investigation(objective: str) -> AgentRunResponse:
    """Run one configured customer investigation and convert it to an API contract."""
    execution_id = str(uuid4())
    result = run_tool_calling_graph(
        create_chat_model(),
        objective,
        request_id=execution_id,
    )
    sections = _extract_sections(result.final_response)
    return AgentRunResponse(
        execution_id=execution_id,
        status=result.current_status,
        final_result=result.final_response,
        findings=StructuredFindings(
            findings=sections.get("findings", ""),
            evidence=sections.get("evidence", ""),
            likely_cause=sections.get("likely cause", ""),
            uncertainty=sections.get("uncertainty", ""),
        ),
        recommendation=sections.get("recommendation", ""),
        execution_summary=ExecutionSummary(
            model_iterations=result.model_iterations,
            tool_actions=len(result.completed_actions),
            observations=len(result.observations),
            plan_steps=len(result.plan),
            errors=tuple(
                ExecutionErrorSummary(code=error.code, recoverable=error.recoverable)
                for error in result.errors
            ),
        ),
        execution_trace=result.execution_trace,
    )
