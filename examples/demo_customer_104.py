"""Run the repeatable stakeholder customer-104 churn-investigation demonstration."""

from operations_agent.graph import create_retention_outreach_proposal, run_tool_calling_graph
from operations_agent.services import create_chat_model

OBJECTIVE = (
    "Investigate customer 104 and determine why they may be at risk of churn. "
    "Provide an evidence-based recommendation."
)


def main() -> None:
    """Run the bounded investigation and print its visible execution summary."""
    result = run_tool_calling_graph(create_chat_model(), OBJECTIVE, request_id="stakeholder-demo-104")
    proposal = create_retention_outreach_proposal(result.observations)

    print(f"Objective: {OBJECTIVE}\n")
    print("Plan:")
    for step in result.plan:
        print(f"- [{step.status}] {step.tool_name}: {step.description}")
    print("\nExecution trace:")
    for event in result.execution_trace:
        print(f"- {event.event_type} ({event.node_name}/{event.status}): {event.summary}")
    print(f"\nFinal result:\n{result.final_response}")
    print(f"\nProposed action: {proposal.description}")
    print("Approval boundary: not executed; explicit human approval is required.")


if __name__ == "__main__":
    main()
