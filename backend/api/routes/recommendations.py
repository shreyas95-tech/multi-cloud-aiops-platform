"""GET /api/recommendations endpoint.

Gathers monitoring data from the MonitoringLayer, passes it to the AILayer
for recommendation generation, and returns results in the APIResponse envelope.
"""

from dataclasses import asdict

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from backend.ai_layer.exceptions import InsufficientDataError
from backend.ai_layer.parser import AILayer
from backend.api.main import error_response, success_response
from backend.api.middleware.auth_middleware import get_current_user
from backend.api.middleware.rbac import require_not_first_time
from backend.models.monitoring import MonitoringData, TimePeriod
from backend.monitoring.monitoring import MonitoringLayer

router = APIRouter(prefix="/api")

# Service instances — in production these would be injected via FastAPI dependencies
_ai_layer = AILayer()
_monitoring_layer = MonitoringLayer()


@router.get("/recommendations", dependencies=[Depends(get_current_user), Depends(require_not_first_time())])
async def get_recommendations():
    """Generate and return AI-powered cost optimization recommendations.

    Workflow:
    1. Fetch costs and resource statuses from MonitoringLayer.
    2. If no data is available, return 502 with insufficient data error.
    3. Pass MonitoringData to AILayer.generate_recommendations().
    4. Limit results to max 100 recommendations.
    5. Return wrapped in APIResponse success envelope.

    Error responses:
    - 502 if monitoring layer fails (service: monitoring_layer)
    - 502 if insufficient monitoring data (service: ai_layer)
    - 502 if AI layer fails (service: ai_layer)
    """
    # Step 1: Gather monitoring data
    try:
        costs = await _monitoring_layer.get_costs()
        statuses = await _monitoring_layer.get_resource_status()
    except Exception as e:
        return JSONResponse(
            status_code=502,
            content=error_response({"service": "monitoring_layer", "message": str(e)}),
        )

    # Step 2: Check for insufficient data
    if not costs and not statuses:
        return JSONResponse(
            status_code=502,
            content=error_response(
                {
                    "service": "ai_layer",
                    "message": "Insufficient monitoring data for recommendations",
                }
            ),
        )

    # Build MonitoringData object
    default_period = _monitoring_layer._default_time_period()
    monitoring_data = MonitoringData(
        cost_entries=costs,
        resource_statuses=statuses,
        period=default_period,
    )

    # Step 3: Generate recommendations via AI Layer
    try:
        recommendations = await _ai_layer.generate_recommendations(monitoring_data)
    except InsufficientDataError as e:
        return JSONResponse(
            status_code=502,
            content=error_response(
                {
                    "service": "ai_layer",
                    "message": str(e),
                    "reason": "insufficient_data",
                    "minimum_requirement": "At least 24 hours of monitoring data with cost entries or resource statuses",
                }
            ),
        )
    except Exception as e:
        return JSONResponse(
            status_code=502,
            content=error_response({"service": "ai_layer", "message": str(e)}),
        )

    # Step 4: Limit to max 100 recommendations and convert to dicts
    recommendations_list = [asdict(rec) for rec in recommendations[:100]]

    # Step 5: Return success response
    return success_response(recommendations_list)
