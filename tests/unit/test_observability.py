"""Unit tests for structured privacy-aware audit events."""

from operations_agent.observability import AuditTrail, redact_sensitive_data


def test_redact_sensitive_data_recursively_masks_credentials_and_email() -> None:
    """Nested sensitive values cannot enter the audit payload unchanged."""
    result = redact_sensitive_data(
        {
            "email": "maya@example.com",
            "nested": {"api_key": "secret-value"},
            "items": [{"authorization": "Bearer token"}],
        }
    )

    assert result == {
        "email": "[REDACTED]",
        "nested": {"api_key": "[REDACTED]"},
        "items": [{"authorization": "[REDACTED]"}],
    }


def test_audit_trail_records_ordered_events_for_one_request() -> None:
    """Events share a request ID and use strictly increasing sequence numbers."""
    trail = AuditTrail("investigation-104")
    trail.record("started", {"customer_id": 104})
    trail.record("completed", {"email": "maya@example.com"})

    assert [event.sequence for event in trail.events] == [1, 2]
    assert {event.request_id for event in trail.events} == {"investigation-104"}
    assert trail.events[1].details["email"] == "[REDACTED]"
