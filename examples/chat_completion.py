"""Send a simple message using the centrally configured chat model."""

from langchain_core.messages import HumanMessage

from operations_agent.services import create_chat_model


def main() -> None:
    """Invoke the configured hosted model and print its text response."""
    model = create_chat_model()
    response = model.invoke([HumanMessage(content="Reply with a one-sentence greeting.")])
    print(response.content)


if __name__ == "__main__":
    main()
