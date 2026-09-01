import asyncio
import logging
from datetime import datetime, timezone
from typing import Optional
from openai import AsyncOpenAI
from config import settings
import database

logger = logging.getLogger("background")


async def generate_llm_summary(session_id: str, formatted_transcript: str) -> str:
    """Uses LLM to generate a concise summary of the conversation transcript."""
    if not settings.openai_api_key or settings.openai_api_key == "your_openai_api_key_here":
        logger.warning(f"OpenAI API key not set. Using rule-based summarizer for session '{session_id}'.")
        return f"Summary for session '{session_id}': User exchanged messages with Tecnvi-AI. Key topics discussed in transcript: {formatted_transcript[:120]}..."

    try:
        client = AsyncOpenAI(api_key=settings.openai_api_key)
        prompt = (
            "You are an automated session post-processor. Analyze the following conversation transcript "
            "and provide a concise, high-level summary (2-4 sentences) highlighting user requests, "
            "tool actions taken, and main outcomes.\n\n"
            f"TRANSCRIPT:\n{formatted_transcript}\n\nSUMMARY:"
        )
        response = await client.chat.completions.create(
            model=settings.llm_model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3
        )
        if response.choices and response.choices[0].message.content:
            return response.choices[0].message.content.strip()
    except Exception as e:
        logger.error(f"Error calling LLM for post-session summary on '{session_id}': {e}")
    
    return f"Session '{session_id}' completed. Transcript log analyzed with {len(formatted_transcript)} characters of session history."


async def process_post_session(session_id: str) -> None:
    """
    Background worker function executed upon WebSocket client disconnect.
    1. Fetches chronological event log from Supabase `session_events`.
    2. Constructs conversation transcript.
    3. Triggers LLM summarization.
    4. Computes session duration.
    5. Persists final summary, end_time, and duration back to `sessions` table.
    """
    logger.info(f"Starting post-session background processing for session '{session_id}'...")

    try:
        # Give a brief moment for final disconnect logs to flush
        await asyncio.sleep(0.5)

        # 1. Fetch Session Metadata & Event History from Supabase
        session_info = await database.get_session(session_id)
        events = await database.get_session_events(session_id)

        if not events:
            logger.warning(f"No events found for session '{session_id}'. Marking session completed with empty summary.")
            await database.finalize_session(session_id, "No interaction recorded during session.", 0.0)
            return

        # 2. Build Formatted Conversation Transcript
        transcript_lines = []
        for event in events:
            event_type = event.get("event_type")
            sender = event.get("sender")
            payload = event.get("payload", {})

            if event_type == "user_message":
                text = payload.get("content") or payload.get("text", "")
                transcript_lines.append(f"User: {text}")
            elif event_type == "ai_response_complete":
                text = payload.get("content") or payload.get("response", "")
                transcript_lines.append(f"AI Assistant: {text}")
            elif event_type == "tool_call_request":
                tool_name = payload.get("tool_name")
                args = payload.get("args")
                transcript_lines.append(f"[System Action] Executing Tool '{tool_name}' with args {args}")
            elif event_type == "tool_call_response":
                tool_name = payload.get("tool_name")
                result = payload.get("result")
                transcript_lines.append(f"[System Result] Tool '{tool_name}' returned: {result}")

        formatted_transcript = "\n".join(transcript_lines) if transcript_lines else "No user text recorded."

        # 3. Generate LLM Session Summary
        summary = await generate_llm_summary(session_id, formatted_transcript)

        # 4. Calculate Duration
        start_time_iso = session_info.get("start_time") if session_info else None
        duration_seconds = 0.0
        if start_time_iso:
            try:
                start_dt = datetime.fromisoformat(start_time_iso.replace("Z", "+00:00"))
                now_dt = datetime.now(timezone.utc)
                duration_seconds = round((now_dt - start_dt).total_seconds(), 2)
            except Exception as dt_err:
                logger.error(f"Error calculating duration for session '{session_id}': {dt_err}")

        # 5. Finalize Session Record in Supabase
        final_record = await database.finalize_session(
            session_id=session_id,
            summary=summary,
            duration_seconds=duration_seconds
        )

        logger.info(
            f"Successfully completed post-session automation for '{session_id}'. "
            f"Duration: {duration_seconds}s. Summary: {summary[:80]}..."
        )

    except Exception as e:
        logger.error(f"Failed to complete post-session processing for '{session_id}': {e}")
