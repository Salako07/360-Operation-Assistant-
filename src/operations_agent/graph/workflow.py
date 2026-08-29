"""LangGraph state machine for bounded structured tool calling."""

import json
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
from collections.abc import Callable
from typing import Literal
from uuid import uuid4

from langchain_core.messages import AIMessage, AnyMessage, HumanMessage, ToolMessage
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph
from pydantic import BaseModel, ConfigDict, Field

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
    ToolCallingAgentState,
    current_utc_time,
)
from operations_agent.models.chat_model import ChatModel
from operations_agent.observability import (
    AuditEvent,
    ExecutionTraceEvent,
    create_audit_event,
    create_execution_trace_event,
)
from operations_agent.prompts import get_customer_churn_system_message
from operations_agent.tools.registry import get_langchain_tools, invoke_registered_tool

_LIMIT_RESPONSE = "Tool-calling stopped because the configured execution limit was reached."


class GraphSettings(BaseModel):
    """Safety settings for one compiled tool-calling graph."""

    model_config = ConfigDict(frozen=True)

    max_iterations: int = Field(default=6, ge=1, le=20)
    max_tool_calls: int = Field(default=12, ge=1, le=50)
    max_tool_retries: int = Field(default=2, ge=0, le=5)
    max_llm_retries: int = Field(default=2, ge=0, le=5)
    max_repeated_failed_actions: int = Field(default=1, ge=1, le=3)
    initial_retry_backoff_seconds: float = Field(default=0.25, ge=0, le=10)
    llm_timeout_seconds: float = Field(default=30, gt=0, le=120)
    tool_timeout_seconds: float = Field(default=10, gt=0, le=60)


class GraphRunResult(BaseModel):
    """Final response and message history produced by a graph execution."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    final_response: str
    messages: tuple[AnyMessage, ...]
    model_iterations: int = Field(ge=0)
    audit_events: tuple[AuditEvent, ...]
    execution_trace: tuple[ExecutionTraceEvent, ...]
    completed_actions: tuple[CompletedAction, ...]
    observations: tuple[Observation, ...]
    plan: tuple[PlanStep, ...]
    current_status: AgentStatus
    final_result: FinalResult
    errors: tuple[AgentError, ...]


def _message_content(message: AIMessage) -> str:
    """Convert potentially structured assistant content to a display string."""
    return message.content if isinstance(message.content, str) else str(message.content)


def _call_with_timeout(operation: Callable[[], object], timeout_seconds: float) -> object:
    """Run one blocking operation with a bounded wait time."""
    executor = ThreadPoolExecutor(max_workers=1)
    future = executor.submit(operation)
    try:
        return future.result(timeout=timeout_seconds)
    except FutureTimeoutError as error:
        future.cancel()
        raise TimeoutError(f"Operation exceeded {timeout_seconds} seconds.") from error
    finally:
        executor.shutdown(wait=False, cancel_futures=True)


def _is_retryable_tool_result(result: dict[str, object]) -> bool:
    """Return whether a structured tool failure may succeed on a retry."""
    error = result.get("error")
    if not isinstance(error, dict):
        return False
    return error.get("code") in {
        "tool_execution_failed",
        "tool_timeout",
        "malformed_tool_response",
    }


def _tool_result_category(result: dict[str, object]) -> str:
    """Return a safe high-level result category even for malformed tool payloads."""
    if result.get("ok") is True:
        return "success"
    error = result.get("error")
    return str(error.get("code", "tool_failure")) if isinstance(error, dict) else "malformed_tool_response"


def build_tool_calling_graph(
    model: ChatModel,
    settings: GraphSettings | None = None,
) -> CompiledStateGraph:
    """Build the START → agent → tools → agent / END state graph.

    The graph owns control flow only. Tool contracts and execution remain in the
    existing tool registry, while model construction remains in the model factory.
    """
    resolved_settings = settings or GraphSettings()
    model_with_tools = model.bind_tools(get_langchain_tools())

    def audit_event(
        state: ToolCallingAgentState,
        event_type: str,
        details: dict[str, object],
        offset: int = 1,
    ) -> AuditEvent:
        """Create the next audit event to append to graph state."""
        return create_audit_event(
            state["request_id"],
            len(state["audit_events"]) + offset,
            event_type,
            details,
        )

    def trace_event(
        event_type: str,
        node_name: str,
        status: str,
        summary: str,
        metadata: dict[str, object] | None = None,
        *,
        agent_name: str | None = None,
        tool_name: str | None = None,
        execution_id: str = "",
    ) -> ExecutionTraceEvent:
        """Create a safe event that reports progress without exposing reasoning."""
        return create_execution_trace_event(
            event_type=event_type,
            node_name=node_name,
            status=status,
            summary=summary,
            metadata=metadata,
            execution_id=execution_id,
            agent_name=agent_name or ("investigation_agent" if node_name in {"agent", "investigation_agent"} else None),
            tool_name=tool_name,
        )

    def execute_tool_with_retries(
        tool_name: object,
        tool_arguments: object,
    ) -> tuple[dict[str, object], list[AgentError]]:
        """Invoke one tool with bounded retries for transient execution failures."""
        errors: list[AgentError] = []
        result: dict[str, object] = {}
        for attempt in range(resolved_settings.max_tool_retries + 1):
            try:
                candidate = _call_with_timeout(
                    lambda: invoke_registered_tool(tool_name, tool_arguments),
                    resolved_settings.tool_timeout_seconds,
                )
                if not isinstance(candidate, dict):
                    result = {
                        "ok": False,
                        "error": {
                            "code": "malformed_tool_response",
                            "message": "The tool registry returned a non-object response.",
                        },
                    }
                else:
                    result = candidate
            except TimeoutError as error:
                result = {
                    "ok": False,
                    "error": {"code": "tool_timeout", "message": str(error)},
                }
            except Exception as error:
                result = {
                    "ok": False,
                    "error": {"code": "tool_execution_failed", "message": str(error)},
                }

            if result.get("ok") is True or not _is_retryable_tool_result(result):
                break

            error_data = result.get("error", {})
            if not isinstance(error_data, dict):
                error_data = {"code": "malformed_tool_response", "message": "Invalid error payload."}
            errors.append(
                AgentError(
                    category=ErrorCategory.TOOL,
                    code=str(error_data.get("code", "tool_execution_failed")),
                    message=str(error_data.get("message", "Tool execution failed.")),
                    recoverable=attempt < resolved_settings.max_tool_retries,
                    occurred_at=current_utc_time(),
                )
            )
            if attempt < resolved_settings.max_tool_retries:
                time.sleep(resolved_settings.initial_retry_backoff_seconds * (2**attempt))

        if result.get("ok") is not True and not errors:
            error_data = result.get("error", {})
            if not isinstance(error_data, dict):
                error_data = {"code": "malformed_tool_response", "message": "Invalid error payload."}
            errors.append(
                AgentError(
                    category=(
                        ErrorCategory.VALIDATION
                        if error_data.get("code") == "invalid_tool_arguments"
                        else ErrorCategory.TOOL
                    ),
                    code=str(error_data.get("code", "tool_execution_failed")),
                    message=str(error_data.get("message", "Tool execution failed.")),
                    recoverable=False,
                    occurred_at=current_utc_time(),
                )
            )
        return result, errors

    def agent(state: ToolCallingAgentState) -> dict[str, object]:
        """Call the LLM with the accumulated conversation or stop at the limit."""
        if state["iterations"] >= resolved_settings.max_iterations:
            final_result = FinalResult(
                response=_LIMIT_RESPONSE,
                status=AgentStatus.LIMIT_REACHED,
                completed_at=current_utc_time(),
            )
            return {
                "messages": [AIMessage(content=_LIMIT_RESPONSE)],
                "current_status": AgentStatus.LIMIT_REACHED,
                "final_result": final_result,
                "execution_trace": [
                    trace_event(
                        "ERROR",
                        "agent",
                        "limit_reached",
                        "Agent execution stopped at the configured iteration limit.",
                        {"max_iterations": resolved_settings.max_iterations},
                    ),
                    trace_event(
                        "FINAL_RESULT",
                        "agent",
                        "limit_reached",
                        "Investigation ended without a final recommendation.",
                    ),
                ],
                "errors": [
                    AgentError(
                        category=ErrorCategory.LIMIT,
                        code="max_iterations_reached",
                        message="The configured model-iteration limit was reached.",
                        recoverable=False,
                        occurred_at=current_utc_time(),
                    )
                ],
                "audit_events": [
                    audit_event(
                        state,
                        "execution_limit_reached",
                        {"final_response": _LIMIT_RESPONSE},
                    )
                ],
            }

        model_request = audit_event(
            state,
            "model_request",
            {
                "request_number": state["iterations"] + 1,
                "message_count": len(state["messages"]),
                "available_tools": [tool.name for tool in get_langchain_tools()],
            },
        )
        events = [model_request]
        trace_events = [
            trace_event(
                "AGENT_DECISION",
                "agent",
                "evaluating",
                "Agent is evaluating the objective and available evidence.",
                {"iteration": state["iterations"] + 1},
            )
        ]
        errors: list[AgentError] = []
        response: AIMessage | None = None
        for attempt in range(resolved_settings.max_llm_retries + 1):
            try:
                candidate = _call_with_timeout(
                    lambda: model_with_tools.invoke(state["messages"]),
                    resolved_settings.llm_timeout_seconds,
                )
                if not isinstance(candidate, AIMessage):
                    raise TypeError("The configured chat model returned a non-AI message response.")
                response = candidate
                break
            except TimeoutError as error:
                error_record = AgentError(
                    category=ErrorCategory.LLM,
                    code="llm_timeout",
                    message=str(error),
                    recoverable=attempt < resolved_settings.max_llm_retries,
                    occurred_at=current_utc_time(),
                )
            except Exception as error:
                error_record = AgentError(
                    category=ErrorCategory.LLM,
                    code="llm_request_failed",
                    message=str(error),
                    recoverable=attempt < resolved_settings.max_llm_retries,
                    occurred_at=current_utc_time(),
                )
            errors.append(error_record)
            trace_events.append(
                trace_event(
                    "ERROR",
                    "agent",
                    "retrying" if error_record.recoverable else "failed",
                    "The model request failed; the agent will retry if its retry budget allows.",
                    {"code": error_record.code, "attempt": attempt + 1},
                )
            )
            events.append(
                audit_event(
                    state,
                    "llm_failure",
                    {"code": error_record.code, "attempt": attempt + 1},
                    offset=len(events) + 1,
                )
            )
            if error_record.recoverable:
                time.sleep(resolved_settings.initial_retry_backoff_seconds * (2**attempt))

        if response is None:
            failure_response = "Unable to complete the investigation because the model is unavailable."
            final_result = FinalResult(
                response=failure_response,
                status=AgentStatus.FAILED,
                completed_at=current_utc_time(),
            )
            return {
                "messages": [AIMessage(content=failure_response)],
                "iterations": state["iterations"] + 1,
                "current_status": AgentStatus.FAILED,
                "final_result": final_result,
                "errors": errors,
                "audit_events": events,
                "execution_trace": [
                    *trace_events,
                    trace_event(
                        "FINAL_RESULT",
                        "agent",
                        "failed",
                        "Investigation ended because the model remained unavailable.",
                    ),
                ],
            }

        final_result: FinalResult | None = None
        if not response.tool_calls:
            final_result = FinalResult(
                response=_message_content(response),
                status=AgentStatus.COMPLETED,
                completed_at=current_utc_time(),
            )
            events.append(
                audit_event(
                    state,
                    "final_response",
                    {"content": _message_content(response)},
                    offset=2,
                )
            )
            trace_events.append(
                trace_event(
                    "FINAL_RESULT",
                    "agent",
                    "completed",
                    "Agent produced a final recommendation from the collected evidence.",
                    {"tool_actions": len(state["completed_actions"])},
                )
            )
        else:
            trace_events.append(
                trace_event(
                    "AGENT_DECISION",
                    "agent",
                    "tool_requested",
                    "Agent requested approved information needed for the investigation.",
                    {"tools": [call.get("name") for call in response.tool_calls]},
                )
            )
        return {
            "messages": [response],
            "iterations": state["iterations"] + 1,
            "audit_events": events,
            "errors": errors,
            "current_status": (
                AgentStatus.COMPLETED if not response.tool_calls else AgentStatus.INVESTIGATING
            ),
            "final_result": final_result if not response.tool_calls else None,
            "execution_trace": trace_events,
        }

    def tools(state: ToolCallingAgentState) -> dict[str, object]:
        """Validate and execute every structured tool call from the latest AI message."""
        latest_message = state["messages"][-1]
        if not isinstance(latest_message, AIMessage):
            return {"messages": []}

        tool_messages: list[ToolMessage] = []
        events: list[AuditEvent] = []
        trace_events: list[ExecutionTraceEvent] = []
        completed_actions: list[CompletedAction] = []
        observations: list[Observation] = []
        errors: list[AgentError] = []
        action_results: dict[str, tuple[ActionStatus, dict[str, object]]] = {}
        limit_reached = False
        for tool_call in latest_message.tool_calls:
            tool_name = tool_call.get("name")
            tool_name_text = tool_name if isinstance(tool_name, str) else "unknown_tool"
            tool_arguments = tool_call.get("args")
            arguments = tool_arguments if isinstance(tool_arguments, dict) else {}
            tool_call_id = str(tool_call.get("id", "unknown_tool_call"))
            tool_errors: list[AgentError] = []
            trace_events.append(
                trace_event(
                    "TOOL_STARTED",
                    tool_name_text,
                    "started",
                    f"Started approved tool: {tool_name_text}.",
                    {"tool_call_id": tool_call_id},
                    tool_name=tool_name_text,
                    agent_name="investigation_agent",
                )
            )
            duplicate = any(
                action.tool_name == tool_name_text
                and action.arguments == arguments
                and action.status is ActionStatus.EXECUTED
                for action in [*state["completed_actions"], *completed_actions]
            )
            repeated_failures = sum(
                action.tool_name == tool_name_text
                and action.arguments == arguments
                and action.status is ActionStatus.FAILED
                for action in [*state["completed_actions"], *completed_actions]
            )
            if len(state["completed_actions"]) + len(completed_actions) >= resolved_settings.max_tool_calls:
                result = {
                    "ok": False,
                    "error": {
                        "code": "max_tool_calls_reached",
                        "message": "The configured tool-call limit was reached.",
                    },
                }
                action_status = ActionStatus.SKIPPED_LIMIT
                limit_reached = True
            elif duplicate:
                result = {
                    "ok": False,
                    "error": {
                        "code": "duplicate_tool_call",
                        "message": "This tool and argument combination has already been retrieved.",
                    },
                }
                action_status = ActionStatus.SKIPPED_DUPLICATE
            elif repeated_failures >= resolved_settings.max_repeated_failed_actions:
                result = {
                    "ok": False,
                    "error": {
                        "code": "repeated_failed_action",
                        "message": "This failed tool action has reached its retry limit.",
                    },
                }
                action_status = ActionStatus.SKIPPED_REPEATED_FAILURE
            else:
                result, tool_errors = execute_tool_with_retries(tool_name, tool_arguments)
                errors.extend(tool_errors)
                action_status = (
                    ActionStatus.EXECUTED if result.get("ok") is True else ActionStatus.FAILED
                )
            result_category = _tool_result_category(result)
            trace_events.append(
                trace_event(
                    "TOOL_COMPLETED",
                    tool_name_text,
                    action_status.value,
                    f"Completed tool: {tool_name_text} with result category {result_category}.",
                    {"tool_call_id": tool_call_id, "result_category": result_category},
                    tool_name=tool_name_text,
                    agent_name="investigation_agent",
                )
            )
            for error in tool_errors:
                trace_events.append(
                    trace_event(
                        "ERROR",
                        tool_name_text,
                        "retrying" if error.recoverable else "failed",
                        "A tool call failed; recovery was attempted when permitted.",
                        {"code": error.code},
                        tool_name=tool_name_text,
                        agent_name="investigation_agent",
                    )
                )
            completed_at = current_utc_time()
            completed_actions.append(
                CompletedAction(
                    tool_call_id=tool_call_id,
                    tool_name=tool_name_text,
                    arguments=arguments,
                    status=action_status,
                    result=result,
                    completed_at=completed_at,
                )
            )
            observations.append(
                Observation(
                    source=tool_name_text,
                    action_id=tool_call_id,
                    data=result,
                    observed_at=completed_at,
                )
            )
            action_results[tool_call_id] = (action_status, result)
            events.extend(
                [
                    audit_event(
                        state,
                        "tool_selected",
                        {"tool_name": tool_name_text},
                        offset=len(events) + 1,
                    ),
                    audit_event(
                        state,
                        "tool_arguments",
                        {"tool_name": tool_name_text, "arguments": arguments},
                        offset=len(events) + 2,
                    ),
                    audit_event(
                        state,
                        "tool_result",
                        {"tool_name": tool_name_text, "result": result},
                        offset=len(events) + 3,
                    ),
                ]
            )
            tool_messages.append(
                ToolMessage(
                    tool_call_id=tool_call_id,
                    name=tool_name_text,
                    content=json.dumps(result),
                )
            )
        updated_plan = [
            step.model_copy(
                update={
                    "status": (
                        PlanStepStatus.COMPLETED
                        if action_results[step.step_id][0] is ActionStatus.EXECUTED
                        and action_results[step.step_id][1].get("ok") is True
                        else PlanStepStatus.NOT_NEEDED
                        if action_results[step.step_id][0]
                        in {
                            ActionStatus.SKIPPED_DUPLICATE,
                            ActionStatus.SKIPPED_REPEATED_FAILURE,
                            ActionStatus.SKIPPED_LIMIT,
                        }
                        else PlanStepStatus.FAILED
                    ),
                    "result": action_results[step.step_id][1],
                }
            )
            if step.step_id in action_results
            else step
            for step in state["plan"]
        ]
        updates: dict[str, object] = {
            "messages": tool_messages,
            "completed_actions": completed_actions,
            "observations": observations,
            "plan": updated_plan,
            "audit_events": events,
            "errors": errors,
            "execution_trace": trace_events,
        }
        if limit_reached:
            final_result = FinalResult(
                response=_LIMIT_RESPONSE,
                status=AgentStatus.LIMIT_REACHED,
                completed_at=current_utc_time(),
            )
            updates.update(
                {
                    "messages": [*tool_messages, AIMessage(content=_LIMIT_RESPONSE)],
                    "current_status": AgentStatus.LIMIT_REACHED,
                    "final_result": final_result,
                    "errors": [
                        *errors,
                        AgentError(
                            category=ErrorCategory.LIMIT,
                            code="max_tool_calls_reached",
                            message="The configured tool-call limit was reached.",
                            recoverable=False,
                            occurred_at=current_utc_time(),
                        ),
                    ],
                    "execution_trace": [
                        *trace_events,
                        trace_event(
                            "ERROR",
                            "tools",
                            "limit_reached",
                            "Tool execution stopped at the configured call limit.",
                            {"max_tool_calls": resolved_settings.max_tool_calls},
                        ),
                        trace_event(
                            "FINAL_RESULT",
                            "tools",
                            "limit_reached",
                            "Investigation ended without a final recommendation.",
                        ),
                    ],
                }
            )
        return updates

    def revise_plan(state: ToolCallingAgentState) -> dict[str, object]:
        """Add structured pending steps for the LLM's latest justified tool requests."""
        latest_message = state["messages"][-1]
        if not isinstance(latest_message, AIMessage):
            return {"plan": state["plan"]}

        descriptions = {
            "get_customer": "Collect account profile and current account status.",
            "get_transactions": "Assess payment, renewal, refund, or billing risk signals.",
            "get_support_tickets": "Assess unresolved customer-impacting support issues.",
            "search_knowledge_base": "Find approved guidance relevant to observed evidence.",
        }
        planned_steps = list(state["plan"])
        added_tools: list[str] = []
        for tool_call in latest_message.tool_calls:
            step_id = str(tool_call.get("id", "unknown_tool_call"))
            if any(step.step_id == step_id for step in planned_steps):
                continue
            tool_name = tool_call.get("name")
            tool_name_text = tool_name if isinstance(tool_name, str) else "unknown_tool"
            arguments = tool_call.get("args")
            planned_steps.append(
                PlanStep(
                    step_id=step_id,
                    description=descriptions.get(
                        tool_name_text,
                        "Resolve an investigation question using an approved tool.",
                    ),
                    tool_name=tool_name_text,
                    arguments=arguments if isinstance(arguments, dict) else {},
                    status=PlanStepStatus.PENDING,
                )
            )
            added_tools.append(tool_name_text)
        event_type = "PLAN_CREATED" if not state["plan"] else "PLAN_UPDATED"
        return {
            "plan": planned_steps,
            "execution_trace": [
                trace_event(
                    event_type,
                    "revise_plan",
                    "updated",
                    "Updated the investigation plan based on the agent's requested information.",
                    {"added_tools": added_tools, "plan_steps": len(planned_steps)},
                )
            ],
        }

    def route_after_agent(state: ToolCallingAgentState) -> Literal["revise_plan", "__end__"]:
        """Revise the plan before executing any new LLM-requested tool calls."""
        latest_message = state["messages"][-1]
        if isinstance(latest_message, AIMessage) and latest_message.tool_calls:
            return "revise_plan"
        return END

    def route_after_tools(state: ToolCallingAgentState) -> Literal["agent", "__end__"]:
        """End immediately when the tool node has reached a terminal call limit."""
        return END if state["final_result"] is not None else "agent"

    graph = StateGraph(ToolCallingAgentState)
    graph.add_node("agent", agent)
    graph.add_node("revise_plan", revise_plan)
    graph.add_node("tools", tools)
    graph.add_edge(START, "agent")
    graph.add_conditional_edges(
        "agent",
        route_after_agent,
        {"revise_plan": "revise_plan", END: END},
    )
    graph.add_edge("revise_plan", "tools")
    graph.add_conditional_edges("tools", route_after_tools, {"agent": "agent", END: END})
    return graph.compile()


def run_tool_calling_graph(
    model: ChatModel,
    user_request: str,
    settings: GraphSettings | None = None,
    request_id: str | None = None,
) -> GraphRunResult:
    """Run the graph for one request and return its final assistant response."""
    graph = build_tool_calling_graph(model, settings)
    resolved_request_id = request_id or str(uuid4())
    request_event = create_audit_event(
        resolved_request_id,
        1,
        "user_request_received",
        {"request_length": len(user_request)},
    )
    final_state = graph.invoke(
        {
            "messages": [get_customer_churn_system_message(), HumanMessage(content=user_request)],
            "objective": user_request,
            "current_status": AgentStatus.INVESTIGATING,
            "plan": [],
            "completed_actions": [],
            "observations": [],
            "final_result": None,
            "errors": [],
            "iterations": 0,
            "request_id": resolved_request_id,
            "audit_events": [request_event],
            "execution_trace": [
                create_execution_trace_event(
                    "OBJECTIVE_RECEIVED",
                    "start",
                    "received",
                    "Received a customer investigation objective.",
                    {"objective_length": len(user_request)},
                    execution_id=resolved_request_id,
                    agent_name="supervisor",
                )
            ],
        },
        {"recursion_limit": (settings or GraphSettings()).max_iterations * 3 + 5},
    )
    messages = tuple(final_state["messages"])
    final_message = messages[-1]
    if not isinstance(final_message, AIMessage):
        raise RuntimeError("Graph completed without a final assistant message.")
    final_result = final_state["final_result"]
    if final_result is None:
        raise RuntimeError("Graph completed without an explicit final result.")
    execution_trace = tuple(
        event if event.execution_id else event.model_copy(update={"execution_id": resolved_request_id})
        for event in final_state["execution_trace"]
    )
    return GraphRunResult(
        final_response=final_result.response,
        messages=messages,
        model_iterations=final_state["iterations"],
        audit_events=tuple(final_state["audit_events"]),
        execution_trace=execution_trace,
        completed_actions=tuple(final_state["completed_actions"]),
        observations=tuple(final_state["observations"]),
        plan=tuple(final_state["plan"]),
        current_status=final_state["current_status"],
        final_result=final_result,
        errors=tuple(final_state["errors"]),
    )
