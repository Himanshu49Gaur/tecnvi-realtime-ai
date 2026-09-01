import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from supabase import AsyncClient, create_async_client
from config import settings

logger = logging.getLogger("database")
logging.basicConfig(level=logging.INFO)

# Global async client instance
_supabase_client: Optional[AsyncClient] = None

# In-memory fallbacks for resilient local testing if DB credentials are invalid/unreachable
_in_memory_sessions: Dict[str, Dict[str, Any]] = {}
_in_memory_events: Dict[str, List[Dict[str, Any]]] = {}


async def get_supabase_client() -> Optional[AsyncClient]:
    """Initialize and return the async Supabase client instance."""
    global _supabase_client
    if _supabase_client is not None:
        return _supabase_client

    if (
        not settings.supabase_url 
        or "your-project.supabase.co" in settings.supabase_url
        or not settings.supabase_key
        or "your_supabase_anon_or_service_key" in settings.supabase_key
    ):
        logger.warning(
            "Supabase credentials not configured in .env. Using in-memory database fallback."
        )
        return None

    try:
        _supabase_client = await create_async_client(
            settings.supabase_url, 
            settings.supabase_key
        )
        logger.info("Successfully connected to Supabase async client.")
        return _supabase_client
    except Exception as e:
        logger.error(f"Failed to initialize Supabase async client: {e}. Falling back to in-memory store.")
        return None


async def create_session(session_id: str, user_id: str = "anonymous") -> Dict[str, Any]:
    """Create a new session record in the sessions table."""
    now_iso = datetime.now(timezone.utc).isoformat()
    session_data = {
        "session_id": session_id,
        "user_id": user_id,
        "start_time": now_iso,
        "status": "active",
        "created_at": now_iso
    }
    
    # Store in memory fallback first
    _in_memory_sessions[session_id] = session_data.copy()
    _in_memory_events.setdefault(session_id, [])

    client = await get_supabase_client()
    if client:
        try:
            response = await client.table("sessions").insert(session_data).execute()
            if response.data:
                logger.info(f"Created session '{session_id}' in Supabase.")
                return response.data[0]
        except Exception as e:
            logger.error(f"Supabase error in create_session('{session_id}'): {e}")

    return session_data


async def log_session_event(
    session_id: str, 
    event_type: str, 
    sender: str, 
    payload: Dict[str, Any]
) -> Dict[str, Any]:
    """Log a detailed event frame into session_events table."""
    now_iso = datetime.now(timezone.utc).isoformat()
    event_data = {
        "session_id": session_id,
        "event_type": event_type,
        "sender": sender,
        "payload": payload,
        "timestamp": now_iso
    }

    # Store in memory fallback
    _in_memory_events.setdefault(session_id, []).append(event_data)

    client = await get_supabase_client()
    if client:
        try:
            response = await client.table("session_events").insert(event_data).execute()
            if response.data:
                logger.debug(f"Logged event '{event_type}' for session '{session_id}'.")
                return response.data[0]
        except Exception as e:
            logger.error(f"Supabase error in log_session_event('{session_id}'): {e}")

    return event_data


async def get_session_events(session_id: str) -> List[Dict[str, Any]]:
    """Retrieve all event logs for a session ordered by timestamp ascending."""
    client = await get_supabase_client()
    if client:
        try:
            response = (
                await client.table("session_events")
                .select("*")
                .eq("session_id", session_id)
                .order("timestamp", desc=False)
                .execute()
            )
            if response.data is not None:
                return response.data
        except Exception as e:
            logger.error(f"Supabase error in get_session_events('{session_id}'): {e}")

    return _in_memory_events.get(session_id, [])


async def get_session(session_id: str) -> Optional[Dict[str, Any]]:
    """Get high-level metadata for a session."""
    client = await get_supabase_client()
    if client:
        try:
            response = (
                await client.table("sessions")
                .select("*")
                .eq("session_id", session_id)
                .single()
                .execute()
            )
            if response.data:
                return response.data
        except Exception as e:
            logger.error(f"Supabase error in get_session('{session_id}'): {e}")

    return _in_memory_sessions.get(session_id)


async def finalize_session(
    session_id: str, 
    summary: str, 
    duration_seconds: float
) -> Dict[str, Any]:
    """Update session with end_time, duration, summary, and completed status."""
    now_iso = datetime.now(timezone.utc).isoformat()
    update_data = {
        "end_time": now_iso,
        "duration_seconds": duration_seconds,
        "summary": summary,
        "status": "completed"
    }

    # Update in memory fallback
    if session_id in _in_memory_sessions:
        _in_memory_sessions[session_id].update(update_data)

    client = await get_supabase_client()
    if client:
        try:
            response = (
                await client.table("sessions")
                .update(update_data)
                .eq("session_id", session_id)
                .execute()
            )
            if response.data:
                logger.info(f"Finalized session '{session_id}' in Supabase.")
                return response.data[0]
        except Exception as e:
            logger.error(f"Supabase error in finalize_session('{session_id}'): {e}")

    return _in_memory_sessions.get(session_id, update_data)
