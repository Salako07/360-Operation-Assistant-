"""FastAPI application factory and default ASGI application."""

import logging
import time
from collections.abc import Callable

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response

from operations_agent.api.models import AgentRunResponse
from operations_agent.api.routes import create_router
from operations_agent.config import load_api_settings
from operations_agent.services.agent_service import run_investigation

logger = logging.getLogger(__name__)


def create_app(
    agent_runner: Callable[[str], AgentRunResponse] = run_investigation,
) -> FastAPI:
    """Create the synchronous API without initializing a model during startup."""
    settings = load_api_settings()
    logging.getLogger("operations_agent").setLevel(settings.log_level)
    app = FastAPI(title="Autonomous Operations Agent", version="0.1.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.cors_origins),
        allow_credentials=False,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type"],
    )

    @app.middleware("http")
    async def log_request(request: Request, call_next: Callable[[Request], Response]) -> Response:
        started_at = time.perf_counter()
        response = await call_next(request)
        logger.info(
            "api_request method=%s path=%s status=%d elapsed_ms=%d",
            request.method,
            request.url.path,
            response.status_code,
            (time.perf_counter() - started_at) * 1_000,
        )
        return response

    app.include_router(create_router(agent_runner))
    return app


app = create_app()
