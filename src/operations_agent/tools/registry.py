"""Structured, read-only tool definitions exposed to chat models."""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from langchain_core.tools import StructuredTool
from pydantic import BaseModel

from operations_agent.models.tools import CustomerLookupInput, KnowledgeBaseSearchInput
from operations_agent.tools.local_data import (
    get_customer,
    get_support_tickets,
    get_transactions,
    search_knowledge_base,
)


@dataclass(frozen=True)
class RegisteredTool:
    """A Python tool plus the Pydantic contract advertised to the model."""

    name: str
    description: str
    args_schema: type[BaseModel]
    function: Callable[..., BaseModel]
    available: bool = True

    def as_langchain_tool(self) -> StructuredTool:
        """Convert this declaration to the schema-bearing LangChain tool type."""
        return StructuredTool.from_function(
            func=self.function,
            name=self.name,
            description=self.description,
            args_schema=self.args_schema,
        )


REGISTERED_TOOLS: tuple[RegisteredTool, ...] = (
    RegisteredTool(
        name="get_customer",
        description="Retrieve the profile and account status for one customer by customer ID.",
        args_schema=CustomerLookupInput,
        function=get_customer,
    ),
    RegisteredTool(
        name="get_transactions",
        description="Retrieve the available billing transaction history for one customer by customer ID.",
        args_schema=CustomerLookupInput,
        function=get_transactions,
    ),
    RegisteredTool(
        name="get_support_tickets",
        description="Retrieve the available support-ticket history for one customer by customer ID.",
        args_schema=CustomerLookupInput,
        function=get_support_tickets,
    ),
    RegisteredTool(
        name="search_knowledge_base",
        description="Search approved internal knowledge-base articles using a focused text query.",
        args_schema=KnowledgeBaseSearchInput,
        function=search_knowledge_base,
    ),
)


def get_registered_tools() -> tuple[RegisteredTool, ...]:
    """Return the complete read-only tool allowlist for a model invocation."""
    return REGISTERED_TOOLS


def get_langchain_tools() -> list[StructuredTool]:
    """Return schema-bearing tool definitions suitable for `model.bind_tools`."""
    return [tool.as_langchain_tool() for tool in REGISTERED_TOOLS]


def find_registered_tool(name: object) -> RegisteredTool | None:
    """Find a tool only when the model requested an allowlisted string name."""
    if not isinstance(name, str):
        return None
    return next((tool for tool in REGISTERED_TOOLS if tool.name == name), None)


def invoke_registered_tool(name: object, arguments: object) -> dict[str, Any]:
    """Validate and invoke one allowlisted tool, returning a JSON-safe envelope.

    Model-provided names and arguments are untrusted. Validation and lookup
    failures become structured tool results so the model can correct its request.
    """
    tool = find_registered_tool(name)
    if tool is None:
        return {
            "ok": False,
            "error": {
                "code": "unknown_tool",
                "message": f"Tool {name!r} is not available.",
            },
        }
    if not tool.available:
        return {
            "ok": False,
            "error": {
                "code": "tool_unavailable",
                "message": f"Tool {tool.name!r} is currently unavailable.",
            },
        }
    if not isinstance(arguments, dict):
        return {
            "ok": False,
            "error": {
                "code": "invalid_tool_arguments",
                "message": f"Arguments for {tool.name} must be an object.",
            },
        }

    try:
        validated_arguments = tool.args_schema.model_validate(arguments)
    except ValueError as error:
        return {
            "ok": False,
            "error": {
                "code": "invalid_tool_arguments",
                "message": str(error),
            },
        }

    try:
        result = tool.function(**validated_arguments.model_dump())
    except Exception as error:
        return {
            "ok": False,
            "error": {
                "code": "tool_execution_failed",
                "message": f"Tool {tool.name!r} failed: {error}",
            },
        }
    if not isinstance(result, BaseModel):
        return {
            "ok": False,
            "error": {
                "code": "malformed_tool_response",
                "message": f"Tool {tool.name!r} returned an invalid response type.",
            },
        }
    return {"ok": True, "result": result.model_dump(mode="json")}
