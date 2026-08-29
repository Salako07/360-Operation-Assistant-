"""LangGraph workflows for the operations agent prototype."""

from operations_agent.graph.approval import (
    ApprovalStatus,
    ProposedAction,
    build_approval_graph,
    create_retention_outreach_proposal,
)
from operations_agent.graph.multi_agent import (
    AgentDomainResult,
    AgentTaskDelegation,
    MultiAgentRunResult,
    MultiAgentSettings,
    build_multi_agent_graph,
    run_multi_agent_investigation,
)
from operations_agent.graph.workflow import (
    GraphRunResult,
    GraphSettings,
    build_tool_calling_graph,
    run_tool_calling_graph,
)

__all__ = [
    "AgentDomainResult",
    "AgentTaskDelegation",
    "GraphRunResult",
    "GraphSettings",
    "MultiAgentRunResult",
    "MultiAgentSettings",
    "ApprovalStatus",
    "ProposedAction",
    "build_tool_calling_graph",
    "build_multi_agent_graph",
    "build_approval_graph",
    "create_retention_outreach_proposal",
    "run_tool_calling_graph",
    "run_multi_agent_investigation",
]
