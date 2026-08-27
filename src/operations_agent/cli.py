"""Command-line entry point for testing the bounded tool-calling workflow."""

import argparse
import logging
from collections.abc import Sequence

from operations_agent.graph import run_tool_calling_graph
from operations_agent.services import create_chat_model


def build_parser() -> argparse.ArgumentParser:
    """Create the command-line parser for one customer-operations request."""
    parser = argparse.ArgumentParser(
        description="Send a request to the hosted model with approved read-only tools."
    )
    parser.add_argument("request", help="Natural-language request for the model.")
    parser.add_argument(
        "--request-id",
        help="Optional correlation ID included in every audit event.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run one tool-calling request and print its structured audit result as JSON."""
    args = build_parser().parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")

    result = run_tool_calling_graph(
        create_chat_model(),
        args.request,
        request_id=args.request_id,
    )
    print(result.model_dump_json(indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
