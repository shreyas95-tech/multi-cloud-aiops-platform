"""FastAPI application for the Multi-Cloud AIOps Platform.

Configures CORS middleware, envelope response helpers, and exception handlers.
"""

import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from typing import Any, Optional

from backend.database import init_db, get_db


async def cleanup_blacklist():
    """Background task that purges expired token_blacklist entries every 30 minutes."""
    while True:
        await asyncio.sleep(30 * 60)  # 30 minutes
        async with get_db() as db:
            await db.execute("DELETE FROM token_blacklist WHERE expires_at < datetime('now')")
            await db.commit()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager for startup/shutdown events."""
    # Startup: initialize database and launch cleanup task
    await init_db()
    task = asyncio.create_task(cleanup_blacklist())
    yield
    # Shutdown: cancel cleanup task
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass


app = FastAPI(title="Multi-Cloud AIOps Platform", lifespan=lifespan)

# CORS middleware — allow all origins for development; restrict in production
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# --- Envelope response helpers ---


def success_response(data: Any) -> dict:
    """Wrap a successful payload in the standard API envelope."""
    return {"status": "success", "data": data, "error": None}


def error_response(error_dict: dict) -> dict:
    """Wrap an error payload in the standard API envelope."""
    return {"status": "error", "data": None, "error": error_dict}


# --- Exception handlers ---


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Return a JSON envelope for 422 validation errors with field name and rule description."""
    errors = exc.errors()
    if errors:
        first_error = errors[0]
        # Extract the field name from the loc tuple (skip 'body' prefix)
        loc = first_error.get("loc", ())
        field_name = loc[-1] if loc else "unknown"
        if field_name == "__root__":
            field_name = "body"
        message = first_error.get("msg", "Validation error")
        return JSONResponse(
            status_code=422,
            content={"status": "error", "data": None, "error": {"field": str(field_name), "message": message}},
        )
    return JSONResponse(
        status_code=422,
        content={"status": "error", "data": None, "error": {"field": "unknown", "message": "Validation error"}},
    )


@app.exception_handler(404)
async def not_found_handler(request: Request, exc):
    """Return a JSON envelope for 404 Not Found."""
    return JSONResponse(
        status_code=404,
        content={"status": "error", "data": None, "error": {"message": "Endpoint not found"}},
    )


# --- Include routers ---

from backend.api.routes.query import router as query_router  # noqa: E402
from backend.api.routes.recommendations import router as recommendations_router  # noqa: E402
from backend.api.routes.costs import router as costs_router  # noqa: E402

app.include_router(query_router)
app.include_router(recommendations_router)
app.include_router(costs_router)


# --- Root health-check endpoint ---


@app.get("/")
async def health_check():
    """Health-check endpoint returning service identification."""
    return success_response({"service": "multi-cloud-aiops"})


# --- Register routers ---

from backend.api.routes.status import router as status_router  # noqa: E402
from backend.api.routes.auth import router as auth_router  # noqa: E402
from backend.api.routes.users import router as users_router  # noqa: E402
from backend.api.routes.kb import router as kb_router  # noqa: E402

app.include_router(status_router)
app.include_router(auth_router)
app.include_router(users_router)
app.include_router(kb_router)
