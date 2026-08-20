"""GET /api/status endpoint — returns resource status from all cloud providers."""

import dataclasses
from typing import Optional

from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse

from backend.api.main import error_response, success_response
from backend.api.middleware.auth_middleware import get_current_user
from backend.api.middleware.rbac import require_not_first_time
from backend.monitoring.monitoring import MonitoringLayer

router = APIRouter(prefix="/api")

# Module-level monitoring layer instance; overridden via dependency injection or tests.
monitoring_layer = MonitoringLayer()


@router.get("/status", dependencies=[Depends(get_current_user), Depends(require_not_first_time())])
async def get_status(provider: Optional[str] = Query(default=None)):
    """Retrieve resource statuses across cloud providers.

    Args:
        provider: Optional provider filter ("AWS", "Azure", or "GCP").

    Returns:
        JSON envelope with a list of ResourceStatus dicts (max 500 items).
        On downstream failure, returns 502 with service identification.
    """
    try:
        statuses = await monitoring_layer.get_resource_status(provider)
        # Limit to 500 items per response
        statuses = statuses[:500]
        statuses_list = [dataclasses.asdict(s) for s in statuses]
        return success_response(statuses_list)
    except Exception as e:
        return JSONResponse(
            status_code=502,
            content=error_response(
                {"service": "monitoring_layer", "message": str(e)}
            ),
        )
