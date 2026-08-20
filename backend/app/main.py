"""FastAPI application entry point for Email Report Analysis."""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# Initialize structured logging
import app.logging_config  # noqa: F401

from app.api.auth import router as auth_router
from app.api.admin import router as admin_router
from app.api.ai import router as ai_router
from app.api.dashboard import router as dashboard_router
from app.api.phone_numbers import router as phone_numbers_router
from app.api.upload import router as upload_router
from app.api.websocket import router as websocket_router
from app.database import init_db


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Create database tables on startup and start email scheduler."""
    await init_db()
    # Start background email polling (if enabled in .env)
    from app.scheduler import start_scheduler, stop_scheduler
    start_scheduler()
    yield
    stop_scheduler()


app = FastAPI(
    title="ReportPulse",
    description="AI-powered report monitoring with trend detection and WhatsApp alerts",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register routers
app.include_router(auth_router, prefix="/api")
app.include_router(admin_router, prefix="/api")
app.include_router(ai_router, prefix="/api")
app.include_router(dashboard_router, prefix="/api")
app.include_router(phone_numbers_router, prefix="/api")
app.include_router(upload_router, prefix="/api")
app.include_router(websocket_router)


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "ok"}
