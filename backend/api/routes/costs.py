"""GET /api/costs endpoint — Retrieve cost data across cloud providers."""

from dataclasses import asdict
from typing import Optional

from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse

from backend.api.main import error_response, success_response
from backend.api.middleware.rbac import require_role, require_not_first_time
from backend.models.monitoring import TimePeriod
from backend.monitoring.monitoring import MonitoringLayer

router = APIRouter(prefix="/api")

# Module-level monitoring layer instance; overridden in tests or via dependency wiring.
monitoring_layer = MonitoringLayer()

MAX_COST_ENTRIES = 500


@router.get("/costs", dependencies=[Depends(require_role("Admin")), Depends(require_not_first_time())])
async def get_costs(
    start: Optional[str] = Query(default=None),
    end: Optional[str] = Query(default=None),
):
    """Retrieve cost data across cloud providers.

    Query Parameters:
        start: Optional ISO 8601 date string for period start.
        end: Optional ISO 8601 date string for period end.
        Both must be provided together, or neither.

    Returns:
        JSON array of CostEntry objects (max 500) wrapped in APIResponse envelope.
        On validation error: 422 with field and message.
        On downstream failure: 502 with service and message.
    """
    # Validate: either both start and end provided, or neither
    if (start is None) != (end is None):
        missing_field = "end" if start is not None else "start"
        return JSONResponse(
            status_code=422,
            content=error_response(
                {
                    "field": missing_field,
                    "message": f"Both 'start' and 'end' query parameters must be provided together. Missing: '{missing_field}'.",
                }
            ),
        )

    # Build time period
    time_period: Optional[TimePeriod] = None
    if start is not None and end is not None:
        time_period = TimePeriod(start=start, end=end)

    # Call monitoring layer
    try:
        costs = await monitoring_layer.get_costs(time_period)
    except Exception as e:
        return JSONResponse(
            status_code=502,
            content=error_response(
                {"service": "monitoring_layer", "message": str(e)}
            ),
        )

    # Limit to max 500 entries
    costs_limited = costs[:MAX_COST_ENTRIES]

    # Convert CostEntry dataclass objects to dicts
    costs_list = [asdict(entry) for entry in costs_limited]

    return success_response(costs_list)
