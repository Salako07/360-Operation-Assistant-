"""Structured audit events and privacy-aware logging for operations workflows."""

import json
import logging
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

logger = logging.getLogger(__name__)

_SENSITIVE_FIELD_FRAGMENTS = (
    "api_key",
    "authorization",
    "password",
    "secret",
    "token",
    "email",
)
_REDACTED_VALUE = "[REDACTED]"


class AuditEvent(BaseModel):
    """One ordered, privacy-aware event emitted during an application request."""

    model_config = ConfigDict(frozen=True)

    request_id: str
    sequence: int = Field(ge=1)
    occurred_at: datetime
    event_type: str
    details: dict[str, Any]


class ExecutionTraceEvent(BaseModel):
    """Safe stakeholder-facing event describing agent progress, not private reasoning."""

    model_config = ConfigDict(frozen=True)

    timestamp: datetime
    event_type: str
    node_name: str
    status: str
    metadata: dict[str, Any]
    summary: str


def create_execution_trace_event(
    event_type: str,
    node_name: str,
    status: str,
    summary: str,
    metadata: Mapping[str, Any] | None = None,
) -> ExecutionTraceEvent:
    """Create a redacted, human-readable execution event safe for API consumers."""
    return ExecutionTraceEvent(
        timestamp=datetime.now(UTC),
        event_type=event_type,
        node_name=node_name,
        status=status,
        metadata=redact_sensitive_data(dict(metadata or {})),
        summary=summary,
    )


def create_audit_event(
    request_id: str,
    sequence: int,
    event_type: str,
    details: Mapping[str, Any] | None = None,
) -> AuditEvent:
    """Create and emit one redacted JSON audit event."""
    event = AuditEvent(
        request_id=request_id,
        sequence=sequence,
        occurred_at=datetime.now(UTC),
        event_type=event_type,
        details=redact_sensitive_data(dict(details or {})),
    )
    logger.info("audit_event=%s", json.dumps(event.model_dump(mode="json"), sort_keys=True))
    return event


def redact_sensitive_data(value: Any) -> Any:
    """Recursively remove credential and email values before logging or tracing."""
    if isinstance(value, Mapping):
        return {
            str(key): (
                _REDACTED_VALUE
                if any(fragment in str(key).lower() for fragment in _SENSITIVE_FIELD_FRAGMENTS)
                else redact_sensitive_data(item)
            )
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [redact_sensitive_data(item) for item in value]
    return value


class AuditTrail:
    """Collect and log ordered audit events for one in-process request.

    Events remain in memory for this prototype and are returned to the caller.
    A later persistence adapter can consume the same `AuditEvent` contract.
    """

    def __init__(self, request_id: str) -> None:
        self._request_id = request_id
        self._events: list[AuditEvent] = []

    @property
    def events(self) -> tuple[AuditEvent, ...]:
        """Return the immutable chronological audit trace."""
        return tuple(self._events)

    def record(self, event_type: str, details: Mapping[str, Any] | None = None) -> AuditEvent:
        """Append one redacted event and emit it as a JSON log entry."""
        event = create_audit_event(
            self._request_id,
            len(self._events) + 1,
            event_type,
            details,
        )
        self._events.append(event)
        return event
