"""Unit tests for the command-line request parser."""

from operations_agent.cli import build_parser


def test_cli_parser_accepts_request_and_optional_correlation_id() -> None:
    """CLI inputs become the model request and audit correlation identifier."""
    arguments = build_parser().parse_args(
        ["Investigate customer 104", "--request-id", "cli-test-104"]
    )

    assert arguments.request == "Investigate customer 104"
    assert arguments.request_id == "cli-test-104"
