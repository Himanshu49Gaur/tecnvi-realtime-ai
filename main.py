import asyncio
import json
import logging
import os
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from config import settings
from connection_manager import manager
import database
import llm_service
import background

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("main")

app = FastAPI(
    title="Realtime AI Backend (WebSockets + Supabase)",
    description="Asynchronous Python backend with bi-directional WebSockets, LLM streaming, Supabase persistence, and post-session processing.",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
async def health_check():
    """Health check REST endpoint."""
    return {
        "status": "online",
        "service": "Realtime AI Backend",
        "version": "1.0.0",
        "environment": settings.environment
    }


@app.get("/api/session/{session_id}")
async def get_session_details(session_id: str):
    """Retrieve metadata and final summary for a session."""
    session = await database.get_session(session_id)
    events = await database.get_session_events(session_id)
    return {
        "session": session,
        "event_count": len(events) if events else 0,
        "events": events
    }


@app.websocket("/ws/session/{session_id}")
async def websocket_session_endpoint(websocket: WebSocket, session_id: str):
    """
    WebSocket endpoint for real-time bi-directional conversation sessions.
    Streams LLM tokens and executes tool calls in real-time.
    Triggers automated post-session summarization upon disconnect.
    """
    await manager.connect(session_id, websocket)

    # Bootstrapping: Create session record & log session_start event in Supabase
    await database.create_session(session_id=session_id)
    await database.log_session_event(
        session_id=session_id,
        event_type="session_start",
        sender="system",
        payload={"status": "connected"}
    )

    # Send system connection confirmation frame
    await manager.send_json(session_id, {
        "type": "system",
        "status": "connected",
        "session_id": session_id,
        "message": "WebSocket session initialized successfully."
    })

    try:
        while True:
            raw_message = await websocket.receive_text()
            try:
                payload = json.loads(raw_message)
            except json.JSONDecodeError:
                payload = {"type": "message", "content": raw_message}

            msg_type = payload.get("type", "message")

            # Heartbeat Ping/Pong
            if msg_type == "ping":
                await manager.send_json(session_id, {"type": "pong"})
                continue

            # Process User Message
            user_text = payload.get("content", payload.get("text", ""))
            if not user_text:
                continue

            # Log user_message event to database
            await database.log_session_event(
                session_id=session_id,
                event_type="user_message",
                sender="user",
                payload={"content": user_text}
            )

            logger.info(f"Received message for session '{session_id}': {user_text}")

            # Trigger Real-Time LLM Streaming Engine & Tool Caller
            await llm_service.generate_and_stream_response(session_id, user_text)

    except WebSocketDisconnect:
        logger.info(f"Client disconnected for session '{session_id}'. Triggering post-session processing...")
        manager.disconnect(session_id)
        await database.log_session_event(
            session_id=session_id,
            event_type="session_end",
            sender="system",
            payload={"reason": "client_disconnect"}
        )
        asyncio.create_task(background.process_post_session(session_id))

    except Exception as e:
        logger.error(f"Unexpected error in WebSocket session '{session_id}': {e}")
        manager.disconnect(session_id)
        await database.log_session_event(
            session_id=session_id,
            event_type="session_error",
            sender="system",
            payload={"error": str(e)}
        )
        asyncio.create_task(background.process_post_session(session_id))


# Mount static directory for frontend UI
if os.path.exists("static"):
    app.mount("/", StaticFiles(directory="static", html=True), name="static")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host=settings.host, port=settings.port, reload=True)

