"""Demonstrate one bounded LLM conversation with the local read-only tools."""

import logging

from operations_agent.services import ToolCallingRunner, create_chat_model


def main() -> None:
    """Ask the hosted model to retrieve a customer fact through a structured tool call."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
    runner = ToolCallingRunner(create_chat_model())
    result = runner.run("Use the available tools to tell me the account status of customer 104.")
    print(result.final_response)


if __name__ == "__main__":
    main()
