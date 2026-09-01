import logging
from typing import Dict, Any, Optional
from fastapi import WebSocket

logger = logging.getLogger("connection_manager")


class ConnectionManager:
    """Manages active WebSocket connections mapped by session_id."""

    def __init__(self):
        # Map of session_id -> WebSocket
        self.active_connections: Dict[str, WebSocket] = {}

    async def connect(self, session_id: str, websocket: WebSocket) -> None:
        """Accept incoming WebSocket connection and register session."""
        await websocket.accept()
        self.active_connections[session_id] = websocket
        logger.info(f"WebSocket client connected for session '{session_id}'. Total active: {len(self.active_connections)}")

    def disconnect(self, session_id: str) -> None:
        """Remove disconnected session from active connections map."""
        if session_id in self.active_connections:
            del self.active_connections[session_id]
            logger.info(f"WebSocket client disconnected for session '{session_id}'. Remaining active: {len(self.active_connections)}")

    async def send_json(self, session_id: str, message: Dict[str, Any]) -> bool:
        """Send a JSON payload frame to a specific connected session."""
        websocket = self.active_connections.get(session_id)
        if websocket:
            try:
                await websocket.send_json(message)
                return True
            except Exception as e:
                logger.error(f"Failed to send JSON frame to session '{session_id}': {e}")
                self.disconnect(session_id)
        return False

    async def broadcast(self, message: Dict[str, Any]) -> None:
        """Broadcast a JSON message frame to all active connections."""
        for session_id, websocket in list(self.active_connections.items()):
            try:
                await websocket.send_json(message)
            except Exception as e:
                logger.error(f"Failed to broadcast to session '{session_id}': {e}")
                self.disconnect(session_id)

    def is_connected(self, session_id: str) -> bool:
        """Check if a session is currently connected."""
        return session_id in self.active_connections


manager = ConnectionManager()

