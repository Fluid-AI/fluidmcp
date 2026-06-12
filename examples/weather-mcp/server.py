"""
Weather MCP Server
Returns dummy weather data for a given city. No external API required.
Runs over HTTP Streamable transport.
"""

from dotenv import load_dotenv
from fastmcp import FastMCP
import os

load_dotenv()

MCP_PORT = int(os.getenv("MCP_PORT"))
TRANSPORT_TYPE = os.getenv("TRANSPORT_TYPE", "http")

mcp = FastMCP("Weather-MCP")

_DUMMY_DATA = {
    "london":    {"temp_c": 12, "condition": "Cloudy",  "humidity_pct": 75},
    "new york":  {"temp_c": 18, "condition": "Sunny",   "humidity_pct": 55},
    "tokyo":     {"temp_c": 22, "condition": "Rainy",   "humidity_pct": 80},
    "sydney":    {"temp_c": 25, "condition": "Clear",   "humidity_pct": 50},
    "paris":     {"temp_c": 15, "condition": "Overcast","humidity_pct": 70},
}


@mcp.tool()
def get_weather(city: str) -> str:
    """
    Return dummy weather information for a given city.

    Args:
        city: City name (e.g. London, Tokyo, Sydney)

    Returns:
        A short weather summary string
    """
    data = _DUMMY_DATA.get(city.lower())
    if data is None:
        known = ", ".join(k.title() for k in _DUMMY_DATA)
        return f"No data for '{city}'. Known cities: {known}."
    return (
        f"{city.title()}: {data['condition']}, "
        f"{data['temp_c']}°C, humidity {data['humidity_pct']}%"
    )


if __name__ == "__main__":
    mcp.run(transport=TRANSPORT_TYPE, port=MCP_PORT)
