import json
import logging
from typing import Dict, Any, List

logger = logging.getLogger("tools")

# --- Internal Tool Handlers (Simulated APIs) ---

def fetch_user_account(account_id: str) -> Dict[str, Any]:
    """Simulated internal tool: Fetches user account details."""
    logger.info(f"Executing tool 'fetch_user_account' for ID: {account_id}")
    accounts = {
        "ACC-101": {"account_id": "ACC-101", "name": "Alice Smith", "plan": "Enterprise Tier", "balance": "$12,450.00", "status": "Active"},
        "ACC-102": {"account_id": "ACC-102", "name": "Bob Jones", "plan": "Pro Tier", "balance": "$1,250.00", "status": "Active"},
    }
    return accounts.get(
        account_id, 
        {"account_id": account_id, "name": "Valued Customer", "plan": "Standard Tier", "balance": "$500.00", "status": "Active"}
    )


def check_weather_forecast(city: str) -> Dict[str, Any]:
    """Simulated internal tool: Fetches current weather forecast."""
    logger.info(f"Executing tool 'check_weather_forecast' for city: {city}")
    weather_data = {
        "london": {"city": "London", "temperature": "18°C", "condition": "Partly Cloudy", "humidity": "65%"},
        "new york": {"city": "New York", "temperature": "24°C", "condition": "Sunny", "humidity": "45%"},
        "tokyo": {"city": "Tokyo", "temperature": "22°C", "condition": "Clear", "humidity": "55%"},
    }
    key = city.lower().strip()
    return weather_data.get(
        key,
        {"city": city, "temperature": "20°C", "condition": "Pleasant", "humidity": "50%"}
    )


def calculate_service_quote(service_type: str, hours: int) -> Dict[str, Any]:
    """Simulated internal tool: Calculates automated business service quote."""
    logger.info(f"Executing tool 'calculate_service_quote' for service: {service_type}, hours: {hours}")
    rates = {
        "ai_consulting": 150,
        "backend_development": 120,
        "database_audit": 135
    }
    rate = rates.get(service_type.lower().strip(), 100)
    total = rate * hours
    return {
        "service_type": service_type,
        "hours": hours,
        "hourly_rate": f"${rate}/hr",
        "total_estimated_quote": f"${total:,}.00"
    }


# Map tool names to python callable handlers
TOOL_HANDLERS = {
    "fetch_user_account": fetch_user_account,
    "check_weather_forecast": check_weather_forecast,
    "calculate_service_quote": calculate_service_quote,
}

# --- OpenAI Function Definitions Schema ---

TOOLS_SCHEMA: List[Dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "fetch_user_account",
            "description": "Fetch user account profile, subscription plan, and account balance details.",
            "parameters": {
                "type": "object",
                "properties": {
                    "account_id": {
                        "type": "string",
                        "description": "The customer account ID e.g. ACC-101"
                    }
                },
                "required": ["account_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "check_weather_forecast",
            "description": "Check real-time weather conditions and forecast for a specific city.",
            "parameters": {
                "type": "object",
                "properties": {
                    "city": {
                        "type": "string",
                        "description": "The name of the city e.g. London, New York, Tokyo"
                    }
                },
                "required": ["city"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "calculate_service_quote",
            "description": "Calculate automated cost quote for enterprise AI or development services.",
            "parameters": {
                "type": "object",
                "properties": {
                    "service_type": {
                        "type": "string",
                        "description": "Service type e.g. ai_consulting, backend_development, database_audit"
                    },
                    "hours": {
                        "type": "integer",
                        "description": "Estimated duration in hours"
                    }
                },
                "required": ["service_type", "hours"]
            }
        }
    }
]


def execute_tool(tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
    """Dispatches tool execution to registered python function handler."""
    handler = TOOL_HANDLERS.get(tool_name)
    if not handler:
        return {"error": f"Tool '{tool_name}' not found"}
    try:
        return handler(**arguments)
    except Exception as e:
        logger.error(f"Error executing tool '{tool_name}': {e}")
        return {"error": str(e)}
