"""End-to-end deterministic demonstration test: FastAPI → graph → tools → result."""

from collections.abc import Sequence
from typing import Any

from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage, BaseMessage
import pytest

from operations_agent.api.main import create_app
from operations_agent.services import agent_service


class DemoModel:
    """Deterministic hosted-model stand-in that selects churn-relevant tools."""

    def __init__(self) -> None:
        self.requests: list[list[BaseMessage]] = []
        self.bound_tools: list[Any] = []
        self._responses = [
            AIMessage(
                content="",
                tool_calls=[
                    {"name": "get_customer", "args": {"customer_id": 104}, "id": "profile"},
                    {"name": "get_transactions", "args": {"customer_id": 104}, "id": "billing"},
                    {"name": "get_support_tickets", "args": {"customer_id": 104}, "id": "support"},
                ],
            ),
            AIMessage(
                content=(
                    "Findings:\nCustomer 104 is past due and has an open high-priority support issue.\n\n"
                    "Evidence:\nFailed renewal payment; open ticket SUP-4821.\n\n"
                    "Likely cause:\nPayment friction and unresolved reporting reliability issues.\n\n"
                    "Recommendation:\nA human should review and approve any retention outreach.\n\n"
                    "Uncertainty:\nThe customer has not stated an intent to churn."
                )
            ),
        ]

    def bind_tools(self, tools: list[Any]) -> "DemoModel":
        self.bound_tools = tools
        return self

    def invoke(self, messages: Sequence[BaseMessage]) -> AIMessage:
        self.requests.append(list(messages))
        return self._responses.pop(0)


def test_customer_104_stakeholder_demo_flow(monkeypatch: pytest.MonkeyPatch) -> None:
    """The public API returns planning, tool, state, result, and trace artifacts."""
    model = DemoModel()
    monkeypatch.setattr(agent_service, "create_chat_model", lambda: model)
    client = TestClient(create_app(agent_service.run_investigation))

    response = client.post(
        "/agent/run",
        json={
            "objective": "Investigate customer 104 and determine why they may be at risk of churn."
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "completed"
    assert payload["execution_summary"] == {
        "model_iterations": 2,
        "tool_actions": 3,
        "observations": 3,
        "plan_steps": 3,
        "errors": [],
    }
    assert "SUP-4821" in payload["findings"]["evidence"]
    assert "human" in payload["recommendation"].lower()
    trace_types = [event["event_type"] for event in payload["execution_trace"]]
    assert "OBJECTIVE_RECEIVED" in trace_types
    assert "PLAN_CREATED" in trace_types
    assert trace_types.count("TOOL_STARTED") == 3
    assert trace_types.count("TOOL_COMPLETED") == 3
    assert trace_types[-1] == "FINAL_RESULT"
    assert {tool.name for tool in model.bound_tools} == {
        "get_customer",
        "get_customer_summary",
        "list_customers",
        "get_transactions",
        "get_invoices",
        "get_usage_metrics",
        "get_support_tickets",
        "get_customer_interactions",
        "calculate_churn_risk",
        "detect_usage_anomaly",
        "search_knowledge_base",
    }
