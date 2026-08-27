"""Unit tests for the bounded LLM structured tool-calling loop."""

import json
from collections.abc import Sequence
from typing import Any

import pytest
from langchain_core.messages import AIMessage, BaseMessage, ToolMessage

from operations_agent.services.tool_calling import (
    ToolCallingRunner,
    ToolCallingSettings,
    ToolCallingStopReason,
)
from operations_agent.models.tools import CustomerLookupInput
from operations_agent.tools import registry
from operations_agent.tools.registry import RegisteredTool, invoke_registered_tool


class FakeToolCallingModel:
    """A deterministic model double that returns pre-configured AI messages."""

    def __init__(self, responses: list[AIMessage]) -> None:
        self._responses = responses
        self.bound_tools: list[Any] | None = None
        self.requests: list[list[BaseMessage]] = []

    def bind_tools(self, tools: list[Any]) -> "FakeToolCallingModel":
        self.bound_tools = tools
        return self

    def invoke(self, messages: Sequence[BaseMessage]) -> AIMessage:
        self.requests.append(list(messages))
        return self._responses.pop(0)


def test_runner_executes_structured_customer_tool_call_then_returns_response() -> None:
    """The loop appends the JSON tool result before requesting the final answer."""
    model = FakeToolCallingModel(
        [
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "get_customer",
                        "args": {"customer_id": 104},
                        "id": "call_customer",
                    }
                ],
            ),
            AIMessage(content="Customer 104 is currently past due."),
        ]
    )
    runner = ToolCallingRunner(model)  # type: ignore[arg-type]

    result = runner.run("What is the account status for customer 104?")

    assert result.stop_reason is ToolCallingStopReason.FINAL_RESPONSE
    assert result.final_response == "Customer 104 is currently past due."
    assert result.model_requests == 2
    assert result.tool_calls == 1
    assert [event.event_type for event in result.audit_events] == [
        "user_request_received",
        "model_request",
        "tool_selected",
        "tool_arguments",
        "tool_result",
        "model_request",
        "final_response",
    ]
    assert result.audit_events[0].request_id == result.audit_events[-1].request_id
    assert result.audit_events[4].details["result"]["result"]["customer"]["email"] == "[REDACTED]"
    assert model.bound_tools is not None
    assert {tool.name for tool in model.bound_tools} == {
        "get_customer",
        "get_transactions",
        "get_support_tickets",
        "search_knowledge_base",
    }
    tool_message = model.requests[1][-1]
    assert isinstance(tool_message, ToolMessage)
    tool_payload = json.loads(tool_message.content)
    assert tool_payload["ok"] is True
    assert tool_payload["result"]["customer"]["customer_id"] == 104


def test_runner_returns_unknown_tool_error_to_model() -> None:
    """Unknown structured tool names are recoverable conversation events."""
    model = FakeToolCallingModel(
        [
            AIMessage(
                content="",
                tool_calls=[{"name": "delete_customer", "args": {}, "id": "call_unknown"}],
            ),
            AIMessage(content="That tool is not available."),
        ]
    )

    result = ToolCallingRunner(model).run("Delete customer 104")  # type: ignore[arg-type]

    assert result.final_response == "That tool is not available."
    tool_message = model.requests[1][-1]
    assert isinstance(tool_message, ToolMessage)
    assert json.loads(tool_message.content)["error"]["code"] == "unknown_tool"


def test_registry_returns_malformed_argument_error_without_calling_tool() -> None:
    """Pydantic argument validation rejects an invalid customer ID."""
    result = invoke_registered_tool("get_transactions", {"customer_id": -1})

    assert result["ok"] is False
    assert result["error"]["code"] == "invalid_tool_arguments"


def test_registry_handles_unavailable_and_malformed_tool_responses(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Registry failure modes are always returned as structured error envelopes."""
    unavailable = RegisteredTool(
        name="unavailable_test",
        description="Unavailable test tool.",
        args_schema=CustomerLookupInput,
        function=lambda customer_id: customer_id and None,  # type: ignore[return-value]
        available=False,
    )
    malformed = RegisteredTool(
        name="malformed_test",
        description="Malformed test tool.",
        args_schema=CustomerLookupInput,
        function=lambda customer_id: f"not a Pydantic model: {customer_id}",  # type: ignore[return-value]
    )
    monkeypatch.setattr(registry, "REGISTERED_TOOLS", (unavailable, malformed))

    unavailable_result = invoke_registered_tool("unavailable_test", {"customer_id": 104})
    malformed_result = invoke_registered_tool("malformed_test", {"customer_id": 104})

    assert unavailable_result["error"]["code"] == "tool_unavailable"
    assert malformed_result["error"]["code"] == "malformed_tool_response"


def test_runner_stops_at_configured_tool_round_limit() -> None:
    """Repeated model tool requests cannot create an unbounded loop."""
    model = FakeToolCallingModel(
        [
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "get_customer",
                        "args": {"customer_id": 104},
                        "id": "call_first",
                    }
                ],
            ),
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "get_transactions",
                        "args": {"customer_id": 104},
                        "id": "call_second",
                    }
                ],
            ),
        ]
    )
    runner = ToolCallingRunner(model, ToolCallingSettings(max_tool_rounds=1))  # type: ignore[arg-type]

    result = runner.run("Investigate customer 104")

    assert result.stop_reason is ToolCallingStopReason.MAX_TOOL_ROUNDS_REACHED
    assert result.tool_calls == 1
    assert result.model_requests == 2
