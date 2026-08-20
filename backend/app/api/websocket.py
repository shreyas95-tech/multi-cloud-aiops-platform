"""WebSocket server for real-time Dashboard updates.

Provides authenticated WebSocket endpoint that pushes new trend results
and deviation records to connected clients without requiring page refresh.
"""

import json
from typing import Dict, Set

import structlog
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query

from app.api.auth import decode_access_token

logger = structlog.get_logger(__name__)

router = APIRouter(tags=["websocket"])

# --- Connection Manager ---


class ConnectionManager:
    """Manages active WebSocket connections per user."""

    def __init__(self):
        # Map of user_id -> set of active WebSocket connections
        self._connections: Dict[str, Set[WebSocket]] = {}

    async def connect(self, websocket: WebSocket, user_id: str):
        """Accept and register a WebSocket connection."""
        await websocket.accept()
        if user_id not in self._connections:
            self._connections[user_id] = set()
        self._connections[user_id].add(websocket)
        logger.info("websocket_connected", user_id=user_id, total_connections=self._total_count())

    def disconnect(self, websocket: WebSocket, user_id: str):
        """Remove a WebSocket connection."""
        if user_id in self._connections:
            self._connections[user_id].discard(websocket)
            if not self._connections[user_id]:
                del self._connections[user_id]
        logger.info("websocket_disconnected", user_id=user_id, total_connections=self._total_count())

    async def send_to_user(self, user_id: str, message: dict):
        """Send a JSON message to all connections for a specific user."""
        if user_id not in self._connections:
            return

        disconnected = set()
        for ws in self._connections[user_id]:
            try:
                await ws.send_json(message)
            except Exception:
                disconnected.add(ws)

        # Clean up dead connections
        for ws in disconnected:
            self._connections[user_id].discard(ws)

    async def broadcast(self, message: dict):
        """Broadcast a message to all connected clients."""
        for user_id in list(self._connections.keys()):
            await self.send_to_user(user_id, message)

    def _total_count(self) -> int:
        return sum(len(conns) for conns in self._connections.values())


# Global connection manager instance
manager = ConnectionManager()


# --- WebSocket Endpoint ---


@router.websocket("/ws/updates")
async def websocket_updates(
    websocket: WebSocket,
    token: str = Query(default=None),
):
    """Authenticated WebSocket endpoint for real-time updates (Req 7.4).

    Clients connect with a JWT token as query parameter.
    Receives push notifications for:
    - New trend results
    - Deviation detections
    - Notification delivery status
    """
    # Authenticate via token query parameter
    if not token:
        await websocket.close(code=4001, reason="Missing authentication token")
        return

    payload = decode_access_token(token)
    if payload is None:
        await websocket.close(code=4001, reason="Invalid or expired token")
        return

    user_id = payload.get("sub")
    if not user_id:
        await websocket.close(code=4001, reason="Invalid token payload")
        return

    # Connect
    await manager.connect(websocket, user_id)

    try:
        # Keep connection alive and listen for client messages (ping/pong)
        while True:
            data = await websocket.receive_text()
            # Handle ping/pong for keep-alive
            if data == "ping":
                await websocket.send_text("pong")
    except WebSocketDisconnect:
        manager.disconnect(websocket, user_id)
    except Exception as e:
        logger.warning("websocket_error", user_id=user_id, error=str(e))
        manager.disconnect(websocket, user_id)


# --- Push Functions (called from Celery tasks) ---


async def broadcast_trend_update(report_id: str, trends: list[dict]):
    """Push new trend results to connected clients for the report owner."""
    message = {
        "type": "trend_update",
        "report_id": report_id,
        "trends": trends,
    }
    # In a production setup, we'd look up the user_id for this report
    # For now, broadcast to all (clients filter by relevance)
    await manager.broadcast(message)


async def broadcast_deviation_update(report_id: str, deviations: list[dict]):
    """Push new deviation detections to connected clients."""
    message = {
        "type": "deviation_update",
        "report_id": report_id,
        "deviations": deviations,
    }
    await manager.broadcast(message)


async def broadcast_notification_status(user_id: str, status: dict):
    """Push notification delivery status to the specific user."""
    message = {
        "type": "notification_status",
        **status,
    }
    await manager.send_to_user(user_id, message)
