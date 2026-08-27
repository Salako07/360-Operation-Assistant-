"""HTTP routes kept separate from model, graph, and tool implementations."""

import logging
from collections.abc import Callable

from fastapi import APIRouter, HTTPException, status

from operations_agent.api.models import AgentRunRequest, AgentRunResponse, HealthResponse

logger = logging.getLogger(__name__)


def create_router(agent_runner: Callable[[str], AgentRunResponse]) -> APIRouter:
    """Create synchronous API routes backed by the supplied application service."""
    router = APIRouter()

    @router.get("/health", response_model=HealthResponse)
    def health() -> HealthResponse:
        """Report whether the HTTP service is available."""
        return HealthResponse()

    @router.post("/agent/run", response_model=AgentRunResponse)
    def run_agent(request: AgentRunRequest) -> AgentRunResponse:
        """Run a bounded customer investigation through the application service."""
        logger.info("agent_run_requested objective_length=%d", len(request.objective))
        try:
            response = agent_runner(request.objective)
        except ValueError:
            logger.warning("agent_run_unavailable")
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Agent service configuration is unavailable.",
            ) from None
        except Exception:
            logger.exception("agent_run_failed")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Agent execution failed.",
            ) from None
        logger.info("agent_run_completed execution_id=%s status=%s", response.execution_id, response.status)
        return response

    return router
