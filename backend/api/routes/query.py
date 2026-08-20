"""POST /api/query endpoint — accepts natural language queries and returns execution results."""

from dataclasses import asdict

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from backend.ai_layer.exceptions import (
    ParseError,
    QueryTooLongError,
    UnsupportedProviderError as AIUnsupportedProviderError,
)
from backend.ai_layer.parser import AILayer
from backend.orchestrator.orchestrator import Orchestrator
from backend.orchestrator.exceptions import (
    UnsupportedActionError,
    UnsupportedProviderError as OrchestratorUnsupportedProviderError,
    ValidationError as OrchestratorValidationError,
)
from backend.api.main import success_response, error_response
from backend.api.middleware.rbac import require_role, require_not_first_time


router = APIRouter(prefix="/api")


# --- Request model ---


class QueryRequest(BaseModel):
    """Request body for the query endpoint."""

    query: str = Field(..., max_length=2000)


# --- Placeholder dependencies (to be replaced by DI wiring in task 11.1) ---

_ai_layer = AILayer()
_orchestrator = Orchestrator()


# --- Endpoint ---


@router.post("/query", dependencies=[Depends(require_role("Admin")), Depends(require_not_first_time())])
async def post_query(body: QueryRequest):
    """Accept a natural language query, parse intent, route to orchestrator, return result.

    Validation:
        - query must be non-empty and ≤ 2000 characters.

    Error responses:
        - 422: Input validation failure (empty or too-long query).
        - 502: Downstream service failure (ai_layer or orchestrator).
    """
    # Manual validation for empty/whitespace-only query
    if not body.query or not body.query.strip():
        return JSONResponse(
            status_code=422,
            content=error_response({
                "field": "query",
                "message": "Query must not be empty or whitespace-only",
            }),
        )

    # Step 1: Forward to AI Layer for intent parsing
    try:
        intent = await _ai_layer.parse_intent(body.query)
    except (ParseError, AIUnsupportedProviderError, QueryTooLongError) as exc:
        return JSONResponse(
            status_code=502,
            content=error_response({
                "service": "ai_layer",
                "message": str(exc),
            }),
        )
    except Exception as exc:
        return JSONResponse(
            status_code=502,
            content=error_response({
                "service": "ai_layer",
                "message": f"Unexpected AI Layer failure: {exc}",
            }),
        )

    # Step 2: Route intent through Orchestrator
    try:
        execution_result = await _orchestrator.route(intent)
    except (
        OrchestratorUnsupportedProviderError,
        UnsupportedActionError,
        OrchestratorValidationError,
    ) as exc:
        return JSONResponse(
            status_code=502,
            content=error_response({
                "service": "orchestrator",
                "message": str(exc),
            }),
        )
    except Exception as exc:
        return JSONResponse(
            status_code=502,
            content=error_response({
                "service": "orchestrator",
                "message": f"Unexpected Orchestrator failure: {exc}",
            }),
        )

    # Step 3: Return success
    return JSONResponse(
        status_code=200,
        content=success_response(asdict(execution_result)),
    )
