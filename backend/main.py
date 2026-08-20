"""Application entry point for the Multi-Cloud AIOps Platform.

Imports the FastAPI app, wires configured dependency instances into route
modules, and starts uvicorn when run directly.
"""

import uvicorn

# Import configured dependencies (triggers provider registration)
from backend.api.dependencies import ai_layer, monitoring_layer, orchestrator

# Wire configured instances into route modules so they use the centrally
# configured services instead of their own default instances.
from backend.api.routes import costs, query, recommendations, status

# Override module-level instances in route modules
query._ai_layer = ai_layer
query._orchestrator = orchestrator
status.monitoring_layer = monitoring_layer
costs.monitoring_layer = monitoring_layer
recommendations._ai_layer = ai_layer
recommendations._monitoring_layer = monitoring_layer

# Import the FastAPI app (after wiring so routes use the configured instances)
from backend.api.main import app  # noqa: E402


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
