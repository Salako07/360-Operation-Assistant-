"""API tests using an injected synchronous investigation service."""

from fastapi.testclient import TestClient

from operations_agent.api.main import create_app
from operations_agent.api.models import (
    AgentRunResponse,
    ExecutionSummary,
    StructuredFindings,
)
from operations_agent.graph.state import AgentStatus
from operations_agent.observability import create_execution_trace_event


def _successful_response(objective: str) -> AgentRunResponse:
    """Return a deterministic API result without creating a hosted model."""
    assert objective == "Investigate customer 104."
    return AgentRunResponse(
        execution_id="execution-104",
        status=AgentStatus.COMPLETED,
        final_result="Findings: customer is past due.",
        findings=StructuredFindings(
            findings="customer is past due.",
            evidence="Account status: past_due.",
            likely_cause="Payment failure.",
            uncertainty="No stated cancellation intent.",
        ),
        recommendation="A human should review retention outreach.",
        execution_summary=ExecutionSummary(
            model_iterations=2,
            tool_actions=3,
            observations=3,
            plan_steps=3,
        ),
        execution_trace=(
            create_execution_trace_event(
                "OBJECTIVE_RECEIVED",
                "start",
                "received",
                "Received a customer investigation objective.",
                {"objective_length": len(objective)},
            ),
        ),
    )


def test_health_endpoint_reports_service_available() -> None:
    """Health checks do not initialize or call the hosted model."""
    client = TestClient(create_app(_successful_response))

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_api_allows_configured_nextjs_development_origin() -> None:
    """Browser preflight succeeds for the default local Next.js origin."""
    client = TestClient(create_app(_successful_response))

    response = client.options(
        "/agent/run",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "POST",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:3000"


def test_agent_run_returns_structured_investigation_response() -> None:
    """The route delegates to the service and returns only its public contract."""
    client = TestClient(create_app(_successful_response))

    response = client.post("/agent/run", json={"objective": "Investigate customer 104."})

    assert response.status_code == 200
    payload = response.json()
    assert payload["execution_id"] == "execution-104"
    assert payload["status"] == "completed"
    assert payload["findings"]["evidence"] == "Account status: past_due."
    assert payload["recommendation"] == "A human should review retention outreach."
    assert payload["execution_summary"]["tool_actions"] == 3
    assert payload["execution_trace"][0]["event_type"] == "OBJECTIVE_RECEIVED"
    assert "objective" not in payload["execution_trace"][0]["metadata"]


def test_agent_run_rejects_invalid_request_body() -> None:
    """Pydantic request validation rejects blank objectives before execution."""
    client = TestClient(create_app(_successful_response))

    response = client.post("/agent/run", json={"objective": ""})

    assert response.status_code == 422


def test_agent_run_returns_safe_status_for_missing_configuration() -> None:
    """Configuration failures do not leak provider or credential details."""
    def unavailable_runner(objective: str) -> AgentRunResponse:
        del objective
        raise ValueError("LLM_API_KEY=secret")

    client = TestClient(create_app(unavailable_runner))
    response = client.post("/agent/run", json={"objective": "Investigate customer 104."})

    assert response.status_code == 503
    assert response.json()["detail"] == "Agent service configuration is unavailable."


def test_agent_run_returns_safe_status_for_unexpected_error() -> None:
    """Unexpected internal failures remain server-side details."""
    def failing_runner(objective: str) -> AgentRunResponse:
        del objective
        raise RuntimeError("internal model detail")

    client = TestClient(create_app(failing_runner))
    response = client.post("/agent/run", json={"objective": "Investigate customer 104."})

    assert response.status_code == 500
    assert response.json()["detail"] == "Agent execution failed."
