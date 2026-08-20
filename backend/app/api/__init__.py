"""API layer - FastAPI routers for the Email Report Analysis system."""

from app.api.auth import router as auth_router
from app.api.dashboard import router as dashboard_router
from app.api.phone_numbers import router as phone_numbers_router
from app.api.websocket import router as websocket_router

__all__ = [
    "auth_router",
    "dashboard_router",
    "phone_numbers_router",
    "websocket_router",
]
