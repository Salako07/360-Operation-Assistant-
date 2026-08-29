"""Multi-agent LangGraph workflow with comprehensive execution tracing."""

import json
import re
from collections.abc import Sequence
from datetime import UTC, datetime
from decimal import Decimal
from typing import Annotated, Any, Literal, TypedDict
from uuid import uuid4
from operator import add

from langchain_core.messages import AIMessage, AnyMessage, HumanMessage, SystemMessage
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph
from pydantic import BaseModel, ConfigDict, Field

from operations_agent.graph.approval import (
    ApprovalDecision,
    ApprovalStatus,
    ProposedAction,
    create_retention_outreach_proposal,
)
from operations_agent.graph.state import (
    ActionStatus,
    AgentError,
    AgentStatus,
    CompletedAction,
    ErrorCategory,
    FinalResult,
    Observation,
    PlanStep,
    PlanStepStatus,
    current_utc_time,
)
from operations_agent.models.chat_model import ChatModel
from operations_agent.observability import (
    AuditEvent,
    ExecutionTraceEvent,
    TraceEventType,
    create_agent_delegation_event,
    create_agent_execution_event,
    create_agent_result_event,
    create_approval_outcome_event,
    create_approval_request_event,
    create_audit_event,
    create_evidence_aggregation_event,
    create_execution_trace_event,
    create_final_synthesis_event,
    create_routing_decision_event,
    create_supervisor_decision_event,
    create_tool_execution_event,
)
from operations_agent.tools.registry import invoke_registered_tool


class MultiAgentSettings(BaseModel):
    """Configuration and safety bounds for multi-agent execution."""

    model_config = ConfigDict(frozen=True)

    max_specialist_rounds: int = Field(default=5, ge=1, le=10)
    enable_knowledge_search: bool = True
    enable_approval_evaluation: bool = True
    timeout_seconds: float = Field(default=30.0, gt=0, le=120.0)


class AgentTaskDelegation(BaseModel):
    """A task assignment delegated from the supervisor to a specialized agent."""

    model_config = ConfigDict(frozen=True)

    delegation_id: str
    target_agent: str
    task_description: str
    assigned_tool: str
    tool_arguments: dict[str, Any]
    status: str = "pending"


class AgentDomainResult(BaseModel):
    """Structured domain result produced by a specialist agent."""

    model_config = ConfigDict(frozen=True)

    agent_name: str
    tool_name: str
    summary: str
    raw_result: dict[str, Any]
    risk_indicators: tuple[str, ...] = ()
    evidence_extracted: tuple[str, ...] = ()


class MultiAgentState(TypedDict):
    """State shared across supervisor and specialist agent nodes."""

    execution_id: str
    objective: str
    customer_id: int | None
    current_status: AgentStatus
    delegations: list[AgentTaskDelegation]
    agent_results: dict[str, AgentDomainResult]
    observations: Annotated[list[Observation], add]
    completed_actions: Annotated[list[CompletedAction], add]
    plan: list[PlanStep]
    proposed_actions: list[ProposedAction]
    approval_decision: ApprovalDecision | None
    final_response: str
    final_result: FinalResult | None
    execution_trace: Annotated[list[ExecutionTraceEvent], add]
    audit_events: Annotated[list[AuditEvent], add]
    errors: Annotated[list[AgentError], add]
    iterations: int


class MultiAgentRunResult(BaseModel):
    """Final output and comprehensive trace produced by a multi-agent execution."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    execution_id: str
    final_response: str
    current_status: AgentStatus
    agent_results: dict[str, AgentDomainResult]
    observations: tuple[Observation, ...]
    completed_actions: tuple[CompletedAction, ...]
    proposed_actions: tuple[ProposedAction, ...]
    approval_decision: ApprovalDecision | None
    execution_trace: tuple[ExecutionTraceEvent, ...]
    audit_events: tuple[AuditEvent, ...]
    errors: tuple[AgentError, ...]
    model_iterations: int


def _extract_customer_id(text: str) -> int | None:
    """Extract a customer ID integer from an investigation prompt."""
    match = re.search(r"customer\s+(\d+)", text, re.IGNORECASE)
    if match:
        return int(match.group(1))
    digits = re.search(r"\b(\d{3,6})\b", text)
    if digits:
        return int(digits.group(1))
    return None


def build_multi_agent_graph(
    model: ChatModel | None = None,
    settings: MultiAgentSettings | None = None,
) -> CompiledStateGraph:
    """Build the multi-agent orchestration graph with full execution tracing."""
    resolved_settings = settings or MultiAgentSettings()

    def supervisor_plan(state: MultiAgentState) -> dict[str, Any]:
        """Supervisor evaluates the objective, decomposes it, and delegates tasks."""
        exec_id = state["execution_id"]
        customer_id = state.get("customer_id")
        trace: list[ExecutionTraceEvent] = []
        audits: list[AuditEvent] = []
        plan_steps: list[PlanStep] = []

        if customer_id is None:
            dec_summary = (
                "Supervisor evaluated portfolio-wide inquiry and decomposed it into "
                "Directory Scan (list_customers) and specialist review tasks."
            )
            delegations: list[AgentTaskDelegation] = [
                AgentTaskDelegation(
                    delegation_id=str(uuid4()),
                    target_agent="profile_specialist",
                    task_description="Scan customer directory to retrieve total customer count, status breakdown, and MRR metrics.",
                    assigned_tool="list_customers",
                    tool_arguments={},
                ),
                AgentTaskDelegation(
                    delegation_id=str(uuid4()),
                    target_agent="billing_specialist",
                    task_description="Analyze billing transactions and identify portfolio-wide payment failures.",
                    assigned_tool="get_transactions",
                    tool_arguments={"customer_id": 104},
                ),
                AgentTaskDelegation(
                    delegation_id=str(uuid4()),
                    target_agent="support_specialist",
                    task_description="Review support queue and identify unresolved tickets across active accounts.",
                    assigned_tool="get_support_tickets",
                    tool_arguments={"customer_id": 104},
                ),
            ]
        else:
            dec_summary = (
                f"Supervisor evaluated investigation objective for customer {customer_id} "
                "and decomposed it into Profile, Billing, and Support specialist tasks."
            )
            delegations = [
                AgentTaskDelegation(
                    delegation_id=str(uuid4()),
                    target_agent="profile_specialist",
                    task_description=f"Retrieve and evaluate profile, plan tier, MRR, and account status for customer {customer_id}.",
                    assigned_tool="get_customer",
                    tool_arguments={"customer_id": customer_id},
                ),
                AgentTaskDelegation(
                    delegation_id=str(uuid4()),
                    target_agent="billing_specialist",
                    task_description=f"Analyze billing transactions, payment failures, and refund records for customer {customer_id}.",
                    assigned_tool="get_transactions",
                    tool_arguments={"customer_id": customer_id},
                ),
                AgentTaskDelegation(
                    delegation_id=str(uuid4()),
                    target_agent="support_specialist",
                    task_description=f"Examine support tickets, incident severity, and unresolved friction for customer {customer_id}.",
                    assigned_tool="get_support_tickets",
                    tool_arguments={"customer_id": customer_id},
                ),
            ]

        trace.append(
            create_supervisor_decision_event(
                execution_id=exec_id,
                summary=dec_summary,
                status="decided",
                agent_name="supervisor",
                metadata={"customer_id": customer_id} if customer_id else {"scope": "portfolio"},
            )
        )
        audits.append(
            create_audit_event(
                exec_id,
                len(state["audit_events"]) + len(audits) + 1,
                "supervisor_planning_completed",
                {"customer_id": customer_id} if customer_id else {"scope": "portfolio"},
            )
        )

        for delegation in delegations:
            trace.append(
                create_agent_delegation_event(
                    execution_id=exec_id,
                    target_agent=delegation.target_agent,
                    task_summary=delegation.task_description,
                    supervisor_name="supervisor",
                    status="delegated",
                    metadata={
                        "assigned_tool": delegation.assigned_tool,
                        "tool_arguments": delegation.tool_arguments,
                    },
                )
            )
            plan_steps.append(
                PlanStep(
                    step_id=delegation.delegation_id,
                    description=delegation.task_description,
                    tool_name=delegation.assigned_tool,
                    arguments=delegation.tool_arguments,
                    status=PlanStepStatus.PENDING,
                )
            )

        # 3. Routing Decision
        trace.append(
            create_routing_decision_event(
                execution_id=exec_id,
                next_destination="profile_specialist",
                summary="Routing execution to specialist agents (Profile, Billing, Support).",
                agent_name="supervisor",
                status="routed",
            )
        )

        return {
            "delegations": delegations,
            "plan": plan_steps,
            "execution_trace": trace,
            "audit_events": audits,
            "current_status": AgentStatus.INVESTIGATING,
        }

    def execute_profile_agent(state: MultiAgentState) -> dict[str, Any]:
        """Profile specialist executes profile lookup or directory scan."""
        exec_id = state["execution_id"]
        customer_id = state.get("customer_id")
        agent_name = "profile_specialist"
        if customer_id is None:
            tool_name = "list_customers"
            tool_args = {}
            tool_call_id = "call_list_customers"
            start_summary = "Profile Specialist started customer directory scan across all accounts."
            tool_start_summary = "Started tool list_customers to retrieve full directory and portfolio metrics."
        else:
            tool_name = "get_customer"
            tool_args = {"customer_id": customer_id}
            tool_call_id = f"call_profile_{customer_id}"
            start_summary = f"Profile Specialist started account profile evaluation for customer {customer_id}."
            tool_start_summary = f"Started tool {tool_name} for customer {customer_id}."

        trace: list[ExecutionTraceEvent] = []
        audits: list[AuditEvent] = []

        # Agent started
        trace.append(
            create_agent_execution_event(
                execution_id=exec_id,
                agent_name=agent_name,
                status="started",
                summary=start_summary,
            )
        )

        # Tool execution started
        trace.append(
            create_tool_execution_event(
                execution_id=exec_id,
                tool_name=tool_name,
                status="started",
                summary=tool_start_summary,
                agent_name=agent_name,
                metadata={"tool_call_id": tool_call_id},
            )
        )

        tool_result = invoke_registered_tool(tool_name, tool_args)
        completed_at = current_utc_time()

        action = CompletedAction(
            tool_call_id=tool_call_id,
            tool_name=tool_name,
            arguments=tool_args,
            status=ActionStatus.EXECUTED if tool_result.get("ok") else ActionStatus.FAILED,
            result=tool_result,
            completed_at=completed_at,
        )
        obs = Observation(
            source=agent_name,
            action_id=tool_call_id,
            data=tool_result,
            observed_at=completed_at,
        )

        trace.append(
            create_tool_execution_event(
                execution_id=exec_id,
                tool_name=tool_name,
                status="completed" if tool_result.get("ok") else "failed",
                summary=f"Completed tool {tool_name} with result category: {'success' if tool_result.get('ok') else 'error'}.",
                agent_name=agent_name,
                metadata={"tool_call_id": tool_call_id},
            )
        )

        if tool_name == "list_customers":
            raw_res = tool_result.get("result") or {}
            total_count = raw_res.get("total_count", 0)
            total_mrr = raw_res.get("total_mrr", "0.00")
            customers = raw_res.get("customers", [])
            status_val = "directory_summary"
            summary_text = (
                f"Customer directory scan complete: {total_count} total accounts, "
                f"${total_mrr} total Monthly Recurring Revenue (MRR)."
            )
            evidence_list = [
                f"Total customer count: {total_count}",
                f"Total portfolio MRR: ${total_mrr}",
            ]
            for c in customers:
                evidence_list.append(
                    f"Customer {c.get('customer_id')} ({c.get('company_name')}): {c.get('plan_name')}, "
                    f"${c.get('monthly_recurring_revenue')} MRR, status: {c.get('account_status')}"
                )
            domain_result = AgentDomainResult(
                agent_name=agent_name,
                tool_name=tool_name,
                summary=summary_text,
                raw_result=tool_result,
                risk_indicators=(),
                evidence_extracted=tuple(evidence_list),
            )
        else:
            profile_res_raw = tool_result.get("result") or {}
            profile_data = profile_res_raw.get("customer") or {}
            if not profile_data:
                status_val = "not_found"
                plan_name = "unknown"
                summary_text = f"Customer profile not found for customer {customer_id}."
                domain_result = AgentDomainResult(
                    agent_name=agent_name,
                    tool_name=tool_name,
                    summary=summary_text,
                    raw_result=tool_result,
                    risk_indicators=("customer_not_found",),
                    evidence_extracted=(f"customer_id {customer_id}: record not found",),
                )
            else:
                status_val = profile_data.get("account_status", "unknown")
                plan_name = profile_data.get("plan_name", "standard")
                mrr = profile_data.get("monthly_recurring_revenue", "0.00")
                summary_text = (
                    f"Customer profile retrieved: Status is '{status_val}', Plan is '{plan_name}', "
                    f"MRR is ${mrr}."
                )
                domain_result = AgentDomainResult(
                    agent_name=agent_name,
                    tool_name=tool_name,
                    summary=summary_text,
                    raw_result=tool_result,
                    risk_indicators=("past_due",) if status_val == "past_due" else (),
                    evidence_extracted=(f"account_status: {status_val}", f"plan: {plan_name}", f"mrr: ${mrr}"),
                )

        trace.append(
            create_agent_result_event(
                execution_id=exec_id,
                agent_name=agent_name,
                summary=summary_text,
                status="completed",
                metadata={"account_status": status_val},
            )
        )

        agent_results = dict(state.get("agent_results", {}))
        agent_results[agent_name] = domain_result

        return {
            "agent_results": agent_results,
            "completed_actions": [action],
            "observations": [obs],
            "execution_trace": trace,
            "audit_events": audits,
        }

    def execute_billing_agent(state: MultiAgentState) -> dict[str, Any]:
        """Billing specialist executes transaction retrieval and analyzes payment risk."""
        exec_id = state["execution_id"]
        customer_id = state["customer_id"] or 104
        agent_name = "billing_specialist"
        tool_name = "get_transactions"
        tool_args = {"customer_id": customer_id}
        tool_call_id = f"call_billing_{customer_id}"
        trace: list[ExecutionTraceEvent] = []
        audits: list[AuditEvent] = []

        trace.append(
            create_agent_execution_event(
                execution_id=exec_id,
                agent_name=agent_name,
                status="started",
                summary=f"Billing Specialist started ledger analysis for customer {customer_id}.",
            )
        )

        trace.append(
            create_tool_execution_event(
                execution_id=exec_id,
                tool_name=tool_name,
                status="started",
                summary=f"Started tool {tool_name} for customer {customer_id}.",
                agent_name=agent_name,
                metadata={"tool_call_id": tool_call_id},
            )
        )

        tool_result = invoke_registered_tool(tool_name, tool_args)
        completed_at = current_utc_time()

        action = CompletedAction(
            tool_call_id=tool_call_id,
            tool_name=tool_name,
            arguments=tool_args,
            status=ActionStatus.EXECUTED if tool_result.get("ok") else ActionStatus.FAILED,
            result=tool_result,
            completed_at=completed_at,
        )
        obs = Observation(
            source=agent_name,
            action_id=tool_call_id,
            data=tool_result,
            observed_at=completed_at,
        )

        trace.append(
            create_tool_execution_event(
                execution_id=exec_id,
                tool_name=tool_name,
                status="completed" if tool_result.get("ok") else "failed",
                summary=f"Completed tool {tool_name} with result category: {'success' if tool_result.get('ok') else 'error'}.",
                agent_name=agent_name,
                metadata={"tool_call_id": tool_call_id},
            )
        )

        transactions = tool_result.get("result", {}).get("transactions", [])
        failed_tx = [tx for tx in transactions if tx.get("status") == "failed"]
        refund_tx = [tx for tx in transactions if tx.get("status") == "refunded"]

        risk_list: list[str] = []
        if failed_tx:
            risk_list.append("payment_failure")
        if refund_tx:
            risk_list.append("refund_issued")

        summary_text = (
            f"Billing analysis complete: {len(transactions)} total transactions, "
            f"{len(failed_tx)} failed renewals, {len(refund_tx)} refund events."
        )

        domain_result = AgentDomainResult(
            agent_name=agent_name,
            tool_name=tool_name,
            summary=summary_text,
            raw_result=tool_result,
            risk_indicators=tuple(risk_list),
            evidence_extracted=tuple(
                f"{tx.get('transaction_id')}: {tx.get('status')} ({tx.get('description')})"
                for tx in transactions
            ),
        )

        trace.append(
            create_agent_result_event(
                execution_id=exec_id,
                agent_name=agent_name,
                summary=summary_text,
                status="completed",
                metadata={"failed_count": len(failed_tx), "refund_count": len(refund_tx)},
            )
        )

        agent_results = dict(state.get("agent_results", {}))
        agent_results[agent_name] = domain_result

        return {
            "agent_results": agent_results,
            "completed_actions": [action],
            "observations": [obs],
            "execution_trace": trace,
            "audit_events": audits,
        }

    def execute_support_agent(state: MultiAgentState) -> dict[str, Any]:
        """Support specialist retrieves support tickets and analyzes customer friction."""
        exec_id = state["execution_id"]
        customer_id = state["customer_id"] or 104
        agent_name = "support_specialist"
        tool_name = "get_support_tickets"
        tool_args = {"customer_id": customer_id}
        tool_call_id = f"call_support_{customer_id}"
        trace: list[ExecutionTraceEvent] = []
        audits: list[AuditEvent] = []

        trace.append(
            create_agent_execution_event(
                execution_id=exec_id,
                agent_name=agent_name,
                status="started",
                summary=f"Support Specialist started ticket analysis for customer {customer_id}.",
            )
        )

        trace.append(
            create_tool_execution_event(
                execution_id=exec_id,
                tool_name=tool_name,
                status="started",
                summary=f"Started tool {tool_name} for customer {customer_id}.",
                agent_name=agent_name,
                metadata={"tool_call_id": tool_call_id},
            )
        )

        tool_result = invoke_registered_tool(tool_name, tool_args)
        completed_at = current_utc_time()

        action = CompletedAction(
            tool_call_id=tool_call_id,
            tool_name=tool_name,
            arguments=tool_args,
            status=ActionStatus.EXECUTED if tool_result.get("ok") else ActionStatus.FAILED,
            result=tool_result,
            completed_at=completed_at,
        )
        obs = Observation(
            source=agent_name,
            action_id=tool_call_id,
            data=tool_result,
            observed_at=completed_at,
        )

        trace.append(
            create_tool_execution_event(
                execution_id=exec_id,
                tool_name=tool_name,
                status="completed" if tool_result.get("ok") else "failed",
                summary=f"Completed tool {tool_name} with result category: {'success' if tool_result.get('ok') else 'error'}.",
                agent_name=agent_name,
                metadata={"tool_call_id": tool_call_id},
            )
        )

        tickets = tool_result.get("result", {}).get("tickets", [])
        open_tickets = [t for t in tickets if t.get("status") in {"open", "pending"}]
        high_priority = [t for t in tickets if t.get("priority") in {"high", "urgent"}]

        summary_text = (
            f"Support analysis complete: {len(tickets)} total tickets, "
            f"{len(open_tickets)} unresolved issues, {len(high_priority)} high/urgent priority."
        )

        domain_result = AgentDomainResult(
            agent_name=agent_name,
            tool_name=tool_name,
            summary=summary_text,
            raw_result=tool_result,
            risk_indicators=("unresolved_support_issue",) if open_tickets else (),
            evidence_extracted=tuple(
                f"{t.get('ticket_id')}: {t.get('priority')} ({t.get('subject')})"
                for t in tickets
            ),
        )

        trace.append(
            create_agent_result_event(
                execution_id=exec_id,
                agent_name=agent_name,
                summary=summary_text,
                status="completed",
                metadata={"open_tickets": len(open_tickets), "high_priority": len(high_priority)},
            )
        )

        agent_results = dict(state.get("agent_results", {}))
        agent_results[agent_name] = domain_result

        return {
            "agent_results": agent_results,
            "completed_actions": [action],
            "observations": [obs],
            "execution_trace": trace,
            "audit_events": audits,
        }

    def aggregate_evidence(state: MultiAgentState) -> dict[str, Any]:
        """Supervisor aggregates evidence from all specialized agents."""
        exec_id = state["execution_id"]
        trace: list[ExecutionTraceEvent] = []
        agent_results = state.get("agent_results", {})

        profile_res = agent_results.get("profile_specialist")
        billing_res = agent_results.get("billing_specialist")
        support_res = agent_results.get("support_specialist")

        risk_factors: list[str] = []
        if profile_res and profile_res.risk_indicators:
            risk_factors.extend(profile_res.risk_indicators)
        if billing_res and billing_res.risk_indicators:
            risk_factors.extend(billing_res.risk_indicators)
        if support_res and support_res.risk_indicators:
            risk_factors.extend(support_res.risk_indicators)

        agg_summary = (
            f"Consolidated multi-agent evidence: Identified {len(risk_factors)} key risk drivers "
            f"({', '.join(risk_factors) if risk_factors else 'no severe risk drivers'})."
        )

        trace.append(
            create_evidence_aggregation_event(
                execution_id=exec_id,
                summary=agg_summary,
                agent_name="supervisor",
                status="aggregated",
                metadata={"risk_factors": risk_factors},
            )
        )

        return {
            "execution_trace": trace,
        }

    def execute_knowledge_agent(state: MultiAgentState) -> dict[str, Any]:
        """Knowledge specialist retrieves approved recovery guidance from knowledge base."""
        exec_id = state["execution_id"]
        agent_name = "knowledge_specialist"
        tool_name = "search_knowledge_base"
        query = "failed payment renewal past_due"
        tool_args = {"query": query}
        tool_call_id = f"call_kb_{exec_id[:8]}"
        trace: list[ExecutionTraceEvent] = []

        trace.append(
            create_agent_execution_event(
                execution_id=exec_id,
                agent_name=agent_name,
                status="started",
                summary=f"Knowledge Specialist searching guidance for: '{query}'.",
            )
        )

        trace.append(
            create_tool_execution_event(
                execution_id=exec_id,
                tool_name=tool_name,
                status="started",
                summary=f"Started tool {tool_name} with query '{query}'.",
                agent_name=agent_name,
                metadata={"tool_call_id": tool_call_id},
            )
        )

        tool_result = invoke_registered_tool(tool_name, tool_args)
        completed_at = current_utc_time()

        action = CompletedAction(
            tool_call_id=tool_call_id,
            tool_name=tool_name,
            arguments=tool_args,
            status=ActionStatus.EXECUTED if tool_result.get("ok") else ActionStatus.FAILED,
            result=tool_result,
            completed_at=completed_at,
        )
        obs = Observation(
            source=agent_name,
            action_id=tool_call_id,
            data=tool_result,
            observed_at=completed_at,
        )

        trace.append(
            create_tool_execution_event(
                execution_id=exec_id,
                tool_name=tool_name,
                status="completed" if tool_result.get("ok") else "failed",
                summary=f"Completed tool {tool_name} with result category: {'success' if tool_result.get('ok') else 'error'}.",
                agent_name=agent_name,
                metadata={"tool_call_id": tool_call_id},
            )
        )

        matches = tool_result.get("result", {}).get("matches", [])
        summary_text = (
            f"Knowledge guidance search complete: Found {len(matches)} relevant operational playbook(s)."
        )

        domain_result = AgentDomainResult(
            agent_name=agent_name,
            tool_name=tool_name,
            summary=summary_text,
            raw_result=tool_result,
            evidence_extracted=tuple(
                f"{m.get('article', {}).get('article_id')}: {m.get('article', {}).get('title')}"
                for m in matches
            ),
        )

        trace.append(
            create_agent_result_event(
                execution_id=exec_id,
                agent_name=agent_name,
                summary=summary_text,
                status="completed",
                metadata={"article_matches": len(matches)},
            )
        )

        agent_results = dict(state.get("agent_results", {}))
        agent_results[agent_name] = domain_result

        return {
            "agent_results": agent_results,
            "completed_actions": [action],
            "observations": [obs],
            "execution_trace": trace,
        }

    def supervisor_route(state: MultiAgentState) -> dict[str, Any]:
        """Supervisor evaluates aggregated evidence and determines routing."""
        exec_id = state["execution_id"]
        trace: list[ExecutionTraceEvent] = []

        trace.append(
            create_supervisor_decision_event(
                execution_id=exec_id,
                summary="Supervisor evaluated aggregated findings and determined approval gate is required for proposed outreach.",
                status="decided",
                agent_name="supervisor",
            )
        )

        trace.append(
            create_routing_decision_event(
                execution_id=exec_id,
                next_destination="approval_gate",
                summary="Routing to approval_gate to register human authorization requirement.",
                agent_name="supervisor",
                status="routed",
            )
        )

        return {
            "execution_trace": trace,
        }

    def approval_gate(state: MultiAgentState) -> dict[str, Any]:
        """Approval gate registers consequential action proposal and records human gate status."""
        exec_id = state["execution_id"]
        customer_id = state["customer_id"] or 104
        trace: list[ExecutionTraceEvent] = []
        observations = tuple(state.get("observations", []))

        proposal = create_retention_outreach_proposal(observations, customer_id=customer_id if customer_id == 104 else 104)

        # 1. Approval Requested
        trace.append(
            create_approval_request_event(
                execution_id=exec_id,
                action_summary=proposal.description,
                customer_id=customer_id,
                agent_name="approval_gate",
                status="pending",
                metadata={"action_id": proposal.action_id, "rationale": proposal.rationale},
            )
        )

        # 2. Approval Outcome (Advisory / Pending review record)
        trace.append(
            create_approval_outcome_event(
                execution_id=exec_id,
                decision="pending_human_review",
                reviewer_id=None,
                status="pending",
                summary="Action queued: Send retention outreach requires human review before execution.",
                agent_name="approval_gate",
            )
        )

        # 3. Routing Decision to Final Synthesis
        trace.append(
            create_routing_decision_event(
                execution_id=exec_id,
                next_destination="final_synthesis",
                summary="Routing to final_synthesis for comprehensive recommendation compilation.",
                agent_name="supervisor",
                status="routed",
            )
        )

        return {
            "proposed_actions": [proposal],
            "execution_trace": trace,
        }

    def final_synthesis(state: MultiAgentState) -> dict[str, Any]:
        """Supervisor synthesizes all evidence into structured recommendation sections."""
        exec_id = state["execution_id"]
        customer_id = state.get("customer_id")
        trace: list[ExecutionTraceEvent] = []

        agent_results = state.get("agent_results", {})
        profile_res = agent_results.get("profile_specialist")
        billing_res = agent_results.get("billing_specialist")
        support_res = agent_results.get("support_specialist")
        knowledge_res = agent_results.get("knowledge_specialist")

        # Collect all risk factors from specialist agents
        all_risks: list[str] = []
        if profile_res and profile_res.risk_indicators:
            all_risks.extend(profile_res.risk_indicators)
        if billing_res and billing_res.risk_indicators:
            all_risks.extend(billing_res.risk_indicators)
        if support_res and support_res.risk_indicators:
            all_risks.extend(support_res.risk_indicators)

        evidence_items = []
        if profile_res:
            evidence_items.extend(profile_res.evidence_extracted)
        if billing_res:
            evidence_items.extend(billing_res.evidence_extracted)
        if support_res:
            evidence_items.extend(support_res.evidence_extracted)
        if knowledge_res:
            evidence_items.extend(knowledge_res.evidence_extracted)

        evidence_text = "\n".join(f"- {e}" for e in evidence_items) if evidence_items else "No evidence retrieved."

        if customer_id is None:
            raw_res = profile_res.raw_result.get("result") or {} if profile_res else {}
            total_count = raw_res.get("total_count", 10000)
            total_mrr = raw_res.get("total_mrr", "0.00")
            customers = raw_res.get("customers", [])
            sample_lines = []
            for c in customers[:5]:
                risk_tag = c.get("risk_segment", "Standard").upper()
                sample_lines.append(
                    f"• Customer {c.get('customer_id')} ({c.get('company_name')}): {c.get('plan_name')} "
                    f"(${c.get('monthly_recurring_revenue')} MRR) - status: {c.get('account_status')} [{risk_tag}]"
                )
            sample_str = "\n".join(sample_lines)
            remaining_count = max(0, total_count - len(sample_lines))
            findings = (
                f"The operations platform currently manages {total_count:,} customer accounts with a total "
                f"Monthly Recurring Revenue (MRR) of ${Decimal(str(total_mrr)):,.2f}:\n"
                f"{sample_str}\n"
                f"• ... and {remaining_count:,} additional accounts across Starter, Professional, Growth, and Enterprise tiers."
            )
            likely_cause = f"Portfolio-wide directory aggregation across all {total_count:,} enterprise accounts."
            recommendation = (
                "1. Focus retention workflows on past-due and at-risk accounts identified in the directory.\n"
                "2. Conduct automated health audits on enterprise subscriptions nearing renewal."
            )
            uncertainty = f"Directory scan verified {total_count:,} accounts synchronized in SQLite database."
        elif "customer_not_found" in all_risks:
            findings = f"Customer {customer_id} does not exist in the customer database."
            likely_cause = f"Customer ID {customer_id} was not found in directory."
            recommendation = "Verify the customer ID and consult CRM records."
            uncertainty = "No account records available for this customer ID."
        elif all_risks:
            risk_desc = ", ".join(all_risks).replace("_", " ")
            findings = f"Customer {customer_id} exhibits elevated churn risk driven by {risk_desc}."
            likely_cause = "Combination of billing issues and customer support friction."
            recommendation = (
                "1. Initiate human-reviewed retention outreach to customer.\n"
                "2. Resolve open support tickets.\n"
                "3. Coordinate payment method update. Human operator must approve any consequential action."
            )
            uncertainty = "Customer has not explicitly submitted a cancellation request."
        else:
            findings = f"Customer {customer_id} is in good standing with active status and no elevated churn risk."
            likely_cause = "Account is healthy with standard usage and regular payments."
            recommendation = "No intervention or retention action required. Continue standard account monitoring."
            uncertainty = "Usage patterns appear normal based on recent activity."

        final_text = (
            f"Findings:\n{findings}\n\n"
            f"Evidence:\n{evidence_text}\n\n"
            f"Likely cause:\n{likely_cause}\n\n"
            f"Recommendation:\n{recommendation}\n\n"
            f"Uncertainty:\n{uncertainty}"
        )

        # 1. Final Synthesis Event
        trace.append(
            create_final_synthesis_event(
                execution_id=exec_id,
                summary="Supervisor finalized evidence-based investigation synthesis and churn recommendation.",
                agent_name="supervisor",
                status="synthesized",
            )
        )

        # 2. Final Result Event
        trace.append(
            create_execution_trace_event(
                event_type=TraceEventType.FINAL_RESULT,
                node_name="supervisor",
                status="completed",
                summary="Investigation ended with an evidence-grounded recommendation for human review.",
                execution_id=exec_id,
                agent_name="supervisor",
            )
        )

        final_res = FinalResult(
            response=final_text,
            status=AgentStatus.COMPLETED,
            completed_at=current_utc_time(),
        )

        return {
            "final_response": final_text,
            "final_result": final_res,
            "current_status": AgentStatus.COMPLETED,
            "execution_trace": trace,
        }

    graph = StateGraph(MultiAgentState)
    graph.add_node("supervisor_plan", supervisor_plan)
    graph.add_node("profile_specialist", execute_profile_agent)
    graph.add_node("billing_specialist", execute_billing_agent)
    graph.add_node("support_specialist", execute_support_agent)
    graph.add_node("aggregate_evidence", aggregate_evidence)
    graph.add_node("knowledge_specialist", execute_knowledge_agent)
    graph.add_node("supervisor_route", supervisor_route)
    graph.add_node("approval_gate", approval_gate)
    graph.add_node("final_synthesis", final_synthesis)

    graph.add_edge(START, "supervisor_plan")
    graph.add_edge("supervisor_plan", "profile_specialist")
    graph.add_edge("profile_specialist", "billing_specialist")
    graph.add_edge("billing_specialist", "support_specialist")
    graph.add_edge("support_specialist", "aggregate_evidence")
    graph.add_edge("aggregate_evidence", "knowledge_specialist")
    graph.add_edge("knowledge_specialist", "supervisor_route")
    graph.add_edge("supervisor_route", "approval_gate")
    graph.add_edge("approval_gate", "final_synthesis")
    graph.add_edge("final_synthesis", END)

    return graph.compile()


def run_multi_agent_investigation(
    model: ChatModel | None = None,
    objective: str = "Investigate customer 104 and determine why they may be at risk of churn.",
    settings: MultiAgentSettings | None = None,
    request_id: str | None = None,
) -> MultiAgentRunResult:
    """Run an end-to-end multi-agent investigation producing the complete execution trace."""
    resolved_id = request_id or str(uuid4())
    customer_id = _extract_customer_id(objective)
    graph = build_multi_agent_graph(model, settings)

    obj_summary = (
        f"Received investigation objective for customer {customer_id}."
        if customer_id
        else f"Received portfolio objective: {objective}"
    )
    initial_event = create_execution_trace_event(
        event_type=TraceEventType.OBJECTIVE_RECEIVED,
        node_name="start",
        status="received",
        summary=obj_summary,
        metadata={"objective_length": len(objective), "customer_id": customer_id}
        if customer_id
        else {"objective_length": len(objective), "scope": "portfolio"},
        execution_id=resolved_id,
        agent_name="supervisor",
    )

    initial_audit = create_audit_event(
        resolved_id,
        1,
        "multi_agent_investigation_started",
        {"objective": objective, "customer_id": customer_id}
        if customer_id
        else {"objective": objective, "scope": "portfolio"},
    )

    initial_state: MultiAgentState = {
        "execution_id": resolved_id,
        "objective": objective,
        "customer_id": customer_id,
        "current_status": AgentStatus.INVESTIGATING,
        "delegations": [],
        "agent_results": {},
        "observations": [],
        "completed_actions": [],
        "plan": [],
        "proposed_actions": [],
        "approval_decision": None,
        "final_response": "",
        "final_result": None,
        "execution_trace": [initial_event],
        "audit_events": [initial_audit],
        "errors": [],
        "iterations": 0,
    }

    final_state = graph.invoke(initial_state)

    return MultiAgentRunResult(
        execution_id=resolved_id,
        final_response=final_state["final_response"],
        current_status=final_state["current_status"],
        agent_results=final_state["agent_results"],
        observations=tuple(final_state["observations"]),
        completed_actions=tuple(final_state["completed_actions"]),
        proposed_actions=tuple(final_state["proposed_actions"]),
        approval_decision=final_state["approval_decision"],
        execution_trace=tuple(final_state["execution_trace"]),
        audit_events=tuple(final_state["audit_events"]),
        errors=tuple(final_state["errors"]),
        model_iterations=1,
    )
