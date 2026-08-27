"""A bounded, synchronous LangChain tool-calling demonstration loop."""

import json
from enum import StrEnum
from uuid import uuid4

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, ToolMessage
from pydantic import BaseModel, ConfigDict, Field

from operations_agent.models.chat_model import ChatModel
from operations_agent.observability import AuditEvent, AuditTrail
from operations_agent.prompts import get_customer_churn_system_message
from operations_agent.tools.registry import get_langchain_tools, invoke_registered_tool


class ToolCallingStopReason(StrEnum):
    """Reason a tool-calling conversation ended."""

    FINAL_RESPONSE = "final_response"
    MAX_TOOL_ROUNDS_REACHED = "max_tool_rounds_reached"
    MAX_TOOL_CALLS_REACHED = "max_tool_calls_reached"


class ToolCallingSettings(BaseModel):
    """Explicit limits that bound one model-and-tools conversation."""

    model_config = ConfigDict(frozen=True)

    max_tool_rounds: int = Field(default=6, ge=1, le=20)
    max_tool_calls: int = Field(default=12, ge=1, le=50)


class ToolCallingResult(BaseModel):
    """Final outcome and trace metrics from one tool-calling conversation."""

    final_response: str
    stop_reason: ToolCallingStopReason
    model_requests: int = Field(ge=1)
    tool_calls: int = Field(ge=0)
    audit_events: tuple[AuditEvent, ...]


def _message_content(message: AIMessage) -> str:
    """Normalize an AI message's possibly structured content for display."""
    return message.content if isinstance(message.content, str) else str(message.content)


class ToolCallingRunner:
    """Run a bounded conversation that lets a configured model call approved tools.

    This class deliberately provides only the fundamental sequential loop. It is
    not an autonomous agent or a graph-based orchestration system.
    """

    def __init__(
        self,
        model: ChatModel,
        settings: ToolCallingSettings | None = None,
    ) -> None:
        self._model = model
        self._settings = settings or ToolCallingSettings()
        self._model_with_tools = model.bind_tools(get_langchain_tools())

    def run(self, user_request: str, request_id: str | None = None) -> ToolCallingResult:
        """Send a user request to the model and fulfill its structured tool calls."""
        messages: list[BaseMessage] = [
            get_customer_churn_system_message(),
            HumanMessage(content=user_request),
        ]
        trail = AuditTrail(request_id or str(uuid4()))
        trail.record("user_request_received", {"request_length": len(user_request)})
        model_requests = 0
        tool_rounds = 0
        tool_calls = 0

        while True:
            trail.record(
                "model_request",
                {
                    "request_number": model_requests + 1,
                    "message_count": len(messages),
                    "available_tools": [tool.name for tool in get_langchain_tools()],
                },
            )
            response = self._model_with_tools.invoke(messages)
            model_requests += 1
            if not isinstance(response, AIMessage):
                raise TypeError("The configured chat model returned a non-AI message response.")

            messages.append(response)
            if not response.tool_calls:
                final_response = _message_content(response)
                trail.record("final_response", {"content": final_response})
                return ToolCallingResult(
                    final_response=final_response,
                    stop_reason=ToolCallingStopReason.FINAL_RESPONSE,
                    model_requests=model_requests,
                    tool_calls=tool_calls,
                    audit_events=trail.events,
                )

            if tool_rounds >= self._settings.max_tool_rounds:
                return self._limit_result(
                    ToolCallingStopReason.MAX_TOOL_ROUNDS_REACHED,
                    model_requests,
                    tool_calls,
                    trail,
                )

            for tool_call in response.tool_calls:
                if tool_calls >= self._settings.max_tool_calls:
                    return self._limit_result(
                        ToolCallingStopReason.MAX_TOOL_CALLS_REACHED,
                        model_requests,
                        tool_calls,
                        trail,
                    )

                tool_name = tool_call.get("name")
                tool_arguments: object = tool_call.get("args")
                tool_call_id = str(tool_call.get("id", "unknown_tool_call"))
                trail.record("tool_selected", {"tool_name": tool_name})
                trail.record(
                    "tool_arguments",
                    {"tool_name": tool_name, "arguments": tool_arguments},
                )

                tool_result = invoke_registered_tool(tool_name, tool_arguments)
                trail.record("tool_result", {"tool_name": tool_name, "result": tool_result})
                messages.append(
                    ToolMessage(
                        tool_call_id=tool_call_id,
                        name=tool_name if isinstance(tool_name, str) else "unknown_tool",
                        content=json.dumps(tool_result),
                    )
                )
                tool_calls += 1

            tool_rounds += 1

    def _limit_result(
        self,
        stop_reason: ToolCallingStopReason,
        model_requests: int,
        tool_calls: int,
        trail: AuditTrail,
    ) -> ToolCallingResult:
        """Create an explicit safe response when a configured limit is reached."""
        response = "Tool-calling stopped because the configured execution limit was reached."
        trail.record(
            "execution_limit_reached",
            {"stop_reason": stop_reason, "final_response": response},
        )
        return ToolCallingResult(
            final_response=response,
            stop_reason=stop_reason,
            model_requests=model_requests,
            tool_calls=tool_calls,
            audit_events=trail.events,
        )
