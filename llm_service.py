import asyncio
import json
import logging
from typing import List, Dict, Any, Optional
from openai import AsyncOpenAI
from config import settings
from connection_manager import manager
import database
import tools

logger = logging.getLogger("llm_service")

_openai_client: Optional[AsyncOpenAI] = None


def get_openai_client() -> Optional[AsyncOpenAI]:
    """Initialize and return AsyncOpenAI client if API key is available."""
    global _openai_client
    if _openai_client is not None:
        return _openai_client

    if (
        not settings.openai_api_key 
        or settings.openai_api_key == "your_openai_api_key_here"
    ):
        logger.warning("OpenAI API key not configured in .env. Using mock tool calling & streaming engine.")
        return None

    try:
        _openai_client = AsyncOpenAI(api_key=settings.openai_api_key)
        return _openai_client
    except Exception as e:
        logger.error(f"Failed to initialize AsyncOpenAI client: {e}")
        return None


async def build_conversation_history(session_id: str) -> List[Dict[str, Any]]:
    """Build OpenAI compatible message history list from stored Supabase session events."""
    events = await database.get_session_events(session_id)
    messages = [
        {
            "role": "system",
            "content": (
                "You are Tecnvi-AI, an intelligent real-time enterprise AI assistant. "
                "You have access to internal tools e.g. fetching account info, checking weather, "
                "and calculating service quotes. Always execute tools when relevant."
            )
        }
    ]

    for event in events:
        event_type = event.get("event_type")
        sender = event.get("sender")
        payload = event.get("payload", {})

        if event_type == "user_message" and sender == "user":
            content = payload.get("content") or payload.get("text")
            if content:
                messages.append({"role": "user", "content": content})
        elif event_type == "ai_response_complete" and sender == "assistant":
            content = payload.get("content") or payload.get("response")
            if content:
                messages.append({"role": "assistant", "content": content})

    return messages


async def stream_mock_response_with_tools(session_id: str, prompt: str) -> str:
    """Simulates real-time token streaming and function tool execution in mock fallback mode."""
    prompt_lower = prompt.lower()
    full_response = ""

    # Simulated Tool Execution Check
    if "account" in prompt_lower or "acc-" in prompt_lower:
        tool_name = "fetch_user_account"
        args = {"account_id": "ACC-101"}
        
        # 1. Notify Client Tool Execution
        await manager.send_json(session_id, {
            "type": "tool_executing",
            "session_id": session_id,
            "tool_name": tool_name,
            "args": args
        })
        await database.log_session_event(session_id, "tool_call_request", "assistant", {"tool_name": tool_name, "args": args})
        
        await asyncio.sleep(0.3)
        result = tools.execute_tool(tool_name, args)
        
        # 2. Notify Client Tool Completed
        await manager.send_json(session_id, {
            "type": "tool_completed",
            "session_id": session_id,
            "tool_name": tool_name,
            "result": result
        })
        await database.log_session_event(session_id, "tool_call_response", "tool", {"tool_name": tool_name, "result": result})

        mock_text = f"I retrieved the account details for {result['name']} ({result['account_id']}). Your plan is {result['plan']} with a balance of {result['balance']}."

    elif "weather" in prompt_lower:
        city = "London" if "london" in prompt_lower else ("New York" if "york" in prompt_lower else "Tokyo")
        tool_name = "check_weather_forecast"
        args = {"city": city}

        await manager.send_json(session_id, {
            "type": "tool_executing",
            "session_id": session_id,
            "tool_name": tool_name,
            "args": args
        })
        await database.log_session_event(session_id, "tool_call_request", "assistant", {"tool_name": tool_name, "args": args})

        await asyncio.sleep(0.3)
        result = tools.execute_tool(tool_name, args)

        await manager.send_json(session_id, {
            "type": "tool_completed",
            "session_id": session_id,
            "tool_name": tool_name,
            "result": result
        })
        await database.log_session_event(session_id, "tool_call_response", "tool", {"tool_name": tool_name, "result": result})

        mock_text = f"The current weather in {result['city']} is {result['temperature']} with {result['condition']} conditions and {result['humidity']} humidity."

    else:
        mock_text = f"Thank you for your message regarding '{prompt}'. Tecnvi-AI processed your request with low-latency WebSocket streaming."

    tokens = mock_text.split(" ")
    for i, token in enumerate(tokens):
        token_chunk = token + (" " if i < len(tokens) - 1 else "")
        full_response += token_chunk
        await manager.send_json(session_id, {
            "type": "token",
            "session_id": session_id,
            "content": token_chunk
        })
        await asyncio.sleep(0.03)

    return full_response


async def generate_and_stream_response(session_id: str, prompt: str) -> str:
    """
    Core function handling complex LLM interactions, tool calling, and token streaming.
    """
    client = get_openai_client()
    full_response = ""

    await manager.send_json(session_id, {
        "type": "stream_start",
        "session_id": session_id
    })

    if client is None:
        full_response = await stream_mock_response_with_tools(session_id, prompt)
    else:
        try:
            messages = await build_conversation_history(session_id)

            # First Call: Stream response with function tools registered
            response_stream = await client.chat.completions.create(
                model=settings.llm_model,
                messages=messages,
                tools=tools.TOOLS_SCHEMA,
                tool_choice="auto",
                stream=True
            )

            tool_calls_data = {}
            
            async for chunk in response_stream:
                if not chunk.choices:
                    continue

                delta = chunk.choices[0].delta

                # Accumulate streaming text tokens
                if delta.content:
                    token = delta.content
                    full_response += token
                    await manager.send_json(session_id, {
                        "type": "token",
                        "session_id": session_id,
                        "content": token
                    })

                # Accumulate tool calls
                if delta.tool_calls:
                    for tool_chunk in delta.tool_calls:
                        idx = tool_chunk.index
                        if idx not in tool_calls_data:
                            tool_calls_data[idx] = {
                                "id": tool_chunk.id or "",
                                "name": tool_chunk.function.name if tool_chunk.function else "",
                                "arguments": ""
                            }
                        if tool_chunk.function and tool_chunk.function.name:
                            tool_calls_data[idx]["name"] = tool_chunk.function.name
                        if tool_chunk.function and tool_chunk.function.arguments:
                            tool_calls_data[idx]["arguments"] += tool_chunk.function.arguments

            # If tool calls were triggered by LLM
            if tool_calls_data:
                for idx, tool_data in tool_calls_data.items():
                    tool_name = tool_data["name"]
                    raw_args = tool_data["arguments"]
                    try:
                        args = json.loads(raw_args) if raw_args else {}
                    except json.JSONDecodeError:
                        args = {}

                    # 1. Notify Client Tool Execution
                    await manager.send_json(session_id, {
                        "type": "tool_executing",
                        "session_id": session_id,
                        "tool_name": tool_name,
                        "args": args
                    })
                    await database.log_session_event(session_id, "tool_call_request", "assistant", {"tool_name": tool_name, "args": args})

                    # 2. Execute Internal Tool Handler
                    result = tools.execute_tool(tool_name, args)

                    # 3. Notify Client Tool Completed
                    await manager.send_json(session_id, {
                        "type": "tool_completed",
                        "session_id": session_id,
                        "tool_name": tool_name,
                        "result": result
                    })
                    await database.log_session_event(session_id, "tool_call_response", "tool", {"tool_name": tool_name, "result": result})

                    # Append tool interaction to messages payload
                    messages.append({
                        "role": "assistant",
                        "content": None,
                        "tool_calls": [{
                            "id": tool_data["id"] or f"call_{idx}",
                            "type": "function",
                            "function": {"name": tool_name, "arguments": json.dumps(args)}
                        }]
                    })
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tool_data["id"] or f"call_{idx}",
                        "content": json.dumps(result)
                    })

                # Second Call: Resume streaming final LLM answer incorporating tool outputs
                second_stream = await client.chat.completions.create(
                    model=settings.llm_model,
                    messages=messages,
                    stream=True
                )
                async for chunk in second_stream:
                    if chunk.choices and chunk.choices[0].delta.content:
                        token = chunk.choices[0].delta.content
                        full_response += token
                        await manager.send_json(session_id, {
                            "type": "token",
                            "session_id": session_id,
                            "content": token
                        })

        except Exception as e:
            logger.error(f"Error in LLM tool streaming loop for session '{session_id}': {e}")
            await manager.send_json(session_id, {
                "type": "error",
                "session_id": session_id,
                "message": f"LLM Tool Execution Error: {str(e)}"
            })
            full_response = await stream_mock_response_with_tools(session_id, prompt)

    await manager.send_json(session_id, {
        "type": "stream_complete",
        "session_id": session_id,
        "full_response": full_response
    })

    await database.log_session_event(
        session_id=session_id,
        event_type="ai_response_complete",
        sender="assistant",
        payload={"content": full_response}
    )

    return full_response
