"""Synchronous FastAPI surface for the customer investigation agent."""

from typing import Any


def create_app(*args: Any, **kwargs: Any) -> Any:
    """Lazy factory to prevent circular imports during module loading."""
    from operations_agent.api.main import create_app as _create_app

    return _create_app(*args, **kwargs)


__all__ = ["create_app"]
