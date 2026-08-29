"""Tests for the LangGraph structured tool-calling workflow."""

import json
from collections.abc import Sequence
from typing import Any

import pytest
from langchain_core.messages import AIMessage, BaseMessage, ToolMessage

from operations_agent.graph import GraphSettings, run_tool_calling_graph
from operations_agent.graph.state import ActionStatus, AgentStatus, PlanStepStatus
from operations_agent.graph import workflow


class FakeGraphModel:
    """A deterministic model double that exposes LangChain's required methods."""

    def __init__(self, responses: list[AIMessage]) -> None:
        self._responses = responses
        self.bound_tools: list[Any] | None = None
        self.requests: list[list[BaseMessage]] = []

    def bind_tools(self, tools: list[Any]) -> "FakeGraphModel":
        self.bound_tools = tools
        return self

    def invoke(self, messages: Sequence[BaseMessage]) -> AIMessage:
        self.requests.append(list(messages))
        return self._responses.pop(0)


def test_graph_returns_direct_assistant_response_without_a_tool() -> None:
    """A tool-free LLM response follows agent → END."""
    model = FakeGraphModel([AIMessage(content="Customer 105 is active.")])

    result = run_tool_calling_graph(model, "What is customer 105's status?")  # type: ignore[arg-type]

    assert result.final_response == "Customer 105 is active."
    assert result.model_iterations == 1
    assert len(result.messages) == 3
    assert model.bound_tools is not None
    assert result.plan == ()


def test_graph_executes_one_tool_call_and_preserves_its_result() -> None:
    """A structured tool call follows agent → tools → agent → END."""
    model = FakeGraphModel(
        [
            AIMessage(
                content="",
                tool_calls=[
                    {"name": "get_customer", "args": {"customer_id": 104}, "id": "call_1"}
                ],
            ),
            AIMessage(content="Customer 104 is past due."),
        ]
    )

    result = run_tool_calling_graph(model, "Check customer 104.")  # type: ignore[arg-type]

    assert result.final_response == "Customer 104 is past due."
    assert result.model_iterations == 2
    assert result.current_status is AgentStatus.COMPLETED
    assert result.final_result.response == result.final_response
    assert result.completed_actions[0].tool_name == "get_customer"
    assert result.completed_actions[0].status is ActionStatus.EXECUTED
    assert result.observations[0].source == "get_customer"
    assert result.plan[0].description == "Collect account profile and current account status."
    assert result.plan[0].status is PlanStepStatus.COMPLETED
    assert [event.event_type for event in result.execution_trace] == [
        "OBJECTIVE_RECEIVED",
        "AGENT_DECISION",
        "AGENT_DECISION",
        "PLAN_CREATED",
        "TOOL_STARTED",
        "TOOL_COMPLETED",
        "AGENT_DECISION",
        "FINAL_RESULT",
    ]
    tool_completed = next(
        event for event in result.execution_trace if event.event_type == "TOOL_COMPLETED"
    )
    assert tool_completed.metadata == {"tool_call_id": "call_1", "result_category": "success"}
    assert [event.event_type for event in result.audit_events] == [
        "user_request_received",
        "model_request",
        "tool_selected",
        "tool_arguments",
        "tool_result",
        "model_request",
        "final_response",
    ]
    tool_message = next(message for message in result.messages if isinstance(message, ToolMessage))
    assert json.loads(tool_message.content)["result"]["customer"]["account_status"] == "past_due"


def test_graph_allows_multiple_tool_calls_across_iterations() -> None:
    """The tools → agent edge supports follow-up tool calls in later iterations."""
    model = FakeGraphModel(
        [
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "get_transactions",
                        "args": {"customer_id": 104},
                        "id": "call_transactions",
                    }
                ],
            ),
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "get_support_tickets",
                        "args": {"customer_id": 104},
                        "id": "call_tickets",
                    }
                ],
            ),
            AIMessage(content="The failed payment and open ticket increase churn risk."),
        ]
    )

    result = run_tool_calling_graph(model, "Investigate churn risk for customer 104.")  # type: ignore[arg-type]

    assert result.model_iterations == 3
    assert result.final_response == "The failed payment and open ticket increase churn risk."
    assert [message.name for message in result.messages if isinstance(message, ToolMessage)] == [
        "get_transactions",
        "get_support_tickets",
    ]
    assert [action.tool_name for action in result.completed_actions] == [
        "get_transactions",
        "get_support_tickets",
    ]
    assert [step.status for step in result.plan] == [
        PlanStepStatus.COMPLETED,
        PlanStepStatus.COMPLETED,
    ]


def test_graph_terminates_after_final_response() -> None:
    """The graph does not request the model again after a final response."""
    model = FakeGraphModel([AIMessage(content="Investigation complete.")])

    result = run_tool_calling_graph(model, "Complete the investigation.")  # type: ignore[arg-type]

    assert result.final_response == "Investigation complete."
    assert len(model.requests) == 1


def test_graph_enforces_maximum_model_iteration_limit() -> None:
    """A repeated tool request is replaced with a controlled terminal response."""
    model = FakeGraphModel(
        [
            AIMessage(
                content="",
                tool_calls=[
                    {"name": "get_customer", "args": {"customer_id": 104}, "id": "call_1"}
                ],
            )
        ]
    )

    result = run_tool_calling_graph(
        model,  # type: ignore[arg-type]
        "Keep looking up customer 104.",
        GraphSettings(max_iterations=1),
    )

    assert result.final_response == (
        "Tool-calling stopped because the configured execution limit was reached."
    )
    assert result.model_iterations == 1
    assert len(model.requests) == 1
    assert any(isinstance(message, ToolMessage) for message in result.messages)
    assert result.current_status is AgentStatus.LIMIT_REACHED
    assert result.final_result.status is AgentStatus.LIMIT_REACHED


def test_graph_skips_duplicate_tool_calls_and_records_the_guard_decision() -> None:
    """The same successful retrieval is not executed twice in one investigation."""
    model = FakeGraphModel(
        [
            AIMessage(
                content="",
                tool_calls=[
                    {"name": "get_customer", "args": {"customer_id": 104}, "id": "call_1"},
                    {"name": "get_customer", "args": {"customer_id": 104}, "id": "call_2"},
                ],
            ),
            AIMessage(content="Findings: duplicate avoided."),
        ]
    )

    result = run_tool_calling_graph(model, "Check customer 104 twice.")  # type: ignore[arg-type]

    assert [action.status for action in result.completed_actions] == [
        ActionStatus.EXECUTED,
        ActionStatus.SKIPPED_DUPLICATE,
    ]
    assert result.observations[1].data["error"]["code"] == "duplicate_tool_call"
    assert result.plan[1].status is PlanStepStatus.NOT_NEEDED


def test_graph_adds_a_follow_up_plan_step_after_unexpected_evidence() -> None:
    """The model can expand the plan after observing a failed payment result."""
    model = FakeGraphModel(
        [
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "get_transactions",
                        "args": {"customer_id": 104},
                        "id": "call_transactions",
                    }
                ],
            ),
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "search_knowledge_base",
                        "args": {"query": "failed payment renewal"},
                        "id": "call_guidance",
                    }
                ],
            ),
            AIMessage(content="Findings: payment recovery guidance found."),
        ]
    )

    result = run_tool_calling_graph(model, "Investigate payment risk for customer 104.")  # type: ignore[arg-type]

    assert [step.tool_name for step in result.plan] == [
        "get_transactions",
        "search_knowledge_base",
    ]
    assert all(step.status is PlanStepStatus.COMPLETED for step in result.plan)


def test_graph_records_failed_tool_step_in_the_plan() -> None:
    """Validation failures remain inspectable evidence rather than crashing the graph."""
    model = FakeGraphModel(
        [
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "get_customer",
                        "args": {"customer_id": -1},
                        "id": "call_invalid_customer",
                    }
                ],
            ),
            AIMessage(content="Findings: the customer ID is invalid."),
        ]
    )

    result = run_tool_calling_graph(model, "Investigate customer -1.")  # type: ignore[arg-type]

    assert result.completed_actions[0].status is ActionStatus.FAILED
    assert result.plan[0].status is PlanStepStatus.FAILED
    assert result.observations[0].data["error"]["code"] == "invalid_tool_arguments"


def test_graph_retries_transient_tool_failures_then_recovers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A transient failed tool call is retried with the bounded retry policy."""
    calls = 0

    def flaky_tool(name: object, arguments: object) -> dict[str, object]:
        nonlocal calls
        del name, arguments
        calls += 1
        if calls == 1:
            return {"ok": False, "error": {"code": "tool_execution_failed", "message": "down"}}
        return {"ok": True, "result": {"customer_id": 104}}

    monkeypatch.setattr(workflow, "invoke_registered_tool", flaky_tool)
    model = FakeGraphModel(
        [
            AIMessage(
                content="",
                tool_calls=[{"name": "get_customer", "args": {"customer_id": 104}, "id": "call_1"}],
            ),
            AIMessage(content="Findings: recovered."),
        ]
    )

    result = run_tool_calling_graph(
        model,  # type: ignore[arg-type]
        "Investigate customer 104.",
        GraphSettings(max_tool_retries=1, initial_retry_backoff_seconds=0),
    )

    assert calls == 2
    assert result.completed_actions[0].status is ActionStatus.EXECUTED
    assert result.errors[0].code == "tool_execution_failed"


def test_graph_retries_llm_failure_then_recovers() -> None:
    """A transient LLM exception is retried before the graph returns a response."""
    model = FakeGraphModel([RuntimeError("provider unavailable"), AIMessage(content="Findings: recovered.")])  # type: ignore[list-item]

    result = run_tool_calling_graph(
        model,  # type: ignore[arg-type]
        "Investigate customer 104.",
        GraphSettings(max_llm_retries=1, initial_retry_backoff_seconds=0),
    )

    assert result.final_response == "Findings: recovered."
    assert result.errors[0].code == "llm_request_failed"


def test_graph_records_tool_timeout_and_terminates_after_bounded_retries(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Timeouts are visible in state and do not create an unbounded retry loop."""
    timeout_calls = 0

    def timeout_tools_only(operation: Any, _timeout_seconds: float) -> object:
        nonlocal timeout_calls
        del _timeout_seconds
        timeout_calls += 1
        if timeout_calls in {2, 3}:
            raise TimeoutError("simulated tool timeout")
        return operation()

    monkeypatch.setattr(workflow, "_call_with_timeout", timeout_tools_only)
    model = FakeGraphModel(
        [
            AIMessage(
                content="",
                tool_calls=[{"name": "get_customer", "args": {"customer_id": 104}, "id": "call_1"}],
            ),
            AIMessage(content="Findings: tool timed out."),
        ]
    )

    result = run_tool_calling_graph(
        model,  # type: ignore[arg-type]
        "Investigate customer 104.",
        GraphSettings(max_tool_retries=1, initial_retry_backoff_seconds=0),
    )

    assert result.completed_actions[0].status is ActionStatus.FAILED
    assert {error.code for error in result.errors} == {"tool_timeout"}


def test_graph_blocks_repeated_failed_actions() -> None:
    """The same failed action is not retried indefinitely across graph iterations."""
    model = FakeGraphModel(
        [
            AIMessage(
                content="",
                tool_calls=[{"name": "get_customer", "args": {"customer_id": -1}, "id": "call_1"}],
            ),
            AIMessage(
                content="",
                tool_calls=[{"name": "get_customer", "args": {"customer_id": -1}, "id": "call_2"}],
            ),
            AIMessage(content="Findings: invalid ID cannot be investigated."),
        ]
    )

    result = run_tool_calling_graph(model, "Investigate customer -1.")  # type: ignore[arg-type]

    assert [action.status for action in result.completed_actions] == [
        ActionStatus.FAILED,
        ActionStatus.SKIPPED_REPEATED_FAILURE,
    ]


def test_graph_stops_when_total_tool_call_limit_is_exceeded() -> None:
    """A second tool request is blocked once the configured action budget is exhausted."""
    model = FakeGraphModel(
        [
            AIMessage(
                content="",
                tool_calls=[
                    {"name": "get_customer", "args": {"customer_id": 104}, "id": "call_1"},
                    {"name": "get_transactions", "args": {"customer_id": 104}, "id": "call_2"},
                ],
            )
        ]
    )

    result = run_tool_calling_graph(
        model,  # type: ignore[arg-type]
        "Investigate customer 104.",
        GraphSettings(max_tool_calls=1),
    )

    assert result.current_status is AgentStatus.LIMIT_REACHED
    assert result.errors[-1].code == "max_tool_calls_reached"
