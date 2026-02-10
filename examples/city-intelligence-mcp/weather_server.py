#!/usr/bin/env python3
"""
Weather MCP Server - Uses Open-Meteo API for weather forecasts
Completely free, no API key required, global coverage
"""
import asyncio
import json
from typing import Any
import httpx

from mcp.server import Server
from mcp.types import Tool, TextContent
import mcp.server.stdio

# Weather code mapping (WMO Weather interpretation codes)
WEATHER_CODES = {
    0: "Clear sky",
    1: "Mainly clear",
    2: "Partly cloudy",
    3: "Overcast",
    45: "Foggy",
    48: "Rime fog",
    51: "Light drizzle",
    53: "Moderate drizzle",
    55: "Dense drizzle",
    61: "Light rain",
    63: "Moderate rain",
    65: "Heavy rain",
    71: "Light snow",
    73: "Moderate snow",
    75: "Heavy snow",
    77: "Snow grains",
    80: "Light rain showers",
    81: "Moderate rain showers",
    82: "Violent rain showers",
    85: "Light snow showers",
    86: "Heavy snow showers",
    95: "Thunderstorm",
    96: "Thunderstorm with light hail",
    99: "Thunderstorm with heavy hail"
}

# Initialize MCP server
app = Server("weather")


@app.list_tools()
async def list_tools() -> list[Tool]:
    """List available weather tools"""
    return [
        Tool(
            name="get_forecast",
            description="Get weather forecast for a city (uses free Open-Meteo API, no API key required)",
            inputSchema={
                "type": "object",
                "properties": {
                    "city": {
                        "type": "string",
                        "description": "City name (e.g., 'Jaipur', 'Paris', 'Tokyo')"
                    },
                    "days": {
                        "type": "integer",
                        "default": 3,
                        "description": "Number of forecast days (1-16)"
                    }
                },
                "required": ["city"]
            }
        )
    ]


@app.call_tool()
async def call_tool(name: str, arguments: Any) -> list[TextContent]:
    """Handle tool calls"""
    if name == "get_forecast":
        try:
            city = arguments["city"]
            days = arguments.get("days", 3)

            # Validate inputs
            if not city or not isinstance(city, str):
                return [TextContent(
                    type="text",
                    text=json.dumps({"error": "Invalid city name"})
                )]

            if days < 1 or days > 16:
                return [TextContent(
                    type="text",
                    text=json.dumps({"error": "Days must be between 1 and 16"})
                )]

            async with httpx.AsyncClient(timeout=60.0) as client:
                # Step 1: Geocode city to coordinates using Nominatim
                geo_resp = await client.get(
                    "https://nominatim.openstreetmap.org/search",
                    params={
                        "q": city,
                        "format": "json",
                        "limit": 1
                    },
                    headers={
                        "User-Agent": "FluidMCP-CityIntelligence/1.0 (Contact: github.com/fluidmcp)"
                    }
                )

                if geo_resp.status_code != 200:
                    return [TextContent(
                        type="text",
                        text=json.dumps({
                            "error": f"Geocoding service error: {geo_resp.status_code}"
                        })
                    )]

                locations = geo_resp.json()

                if not locations or len(locations) == 0:
                    return [TextContent(
                        type="text",
                        text=json.dumps({
                            "error": f"City '{city}' not found. Please check the spelling."
                        })
                    )]

                # Extract coordinates
                lat = float(locations[0]["lat"])
                lon = float(locations[0]["lon"])
                display_name = locations[0].get("display_name", city)

                # Step 2: Fetch weather forecast from Open-Meteo
                weather_resp = await client.get(
                    "https://api.open-meteo.com/v1/forecast",
                    params={
                        "latitude": lat,
                        "longitude": lon,
                        "daily": "temperature_2m_max,temperature_2m_min,precipitation_probability_max,weathercode,windspeed_10m_max",
                        "timezone": "auto",
                        "forecast_days": days
                    }
                )

                if weather_resp.status_code != 200:
                    return [TextContent(
                        type="text",
                        text=json.dumps({
                            "error": f"Weather API error: {weather_resp.status_code}"
                        })
                    )]

                weather_data = weather_resp.json()

                # Step 3: Format the response
                result = {
                    "city": city,
                    "display_name": display_name,
                    "coordinates": {
                        "lat": lat,
                        "lon": lon
                    },
                    "timezone": weather_data.get("timezone", "UTC"),
                    "forecast": []
                }

                daily = weather_data.get("daily", {})
                times = daily.get("time", [])
                temp_max = daily.get("temperature_2m_max", [])
                temp_min = daily.get("temperature_2m_min", [])
                precip_prob = daily.get("precipitation_probability_max", [])
                weather_codes = daily.get("weathercode", [])
                wind_speeds = daily.get("windspeed_10m_max", [])

                for i in range(len(times)):
                    weather_code = int(weather_codes[i]) if i < len(weather_codes) else 0

                    result["forecast"].append({
                        "date": times[i],
                        "temp_high": round(temp_max[i], 1) if i < len(temp_max) else None,
                        "temp_low": round(temp_min[i], 1) if i < len(temp_min) else None,
                        "precipitation_chance": int(precip_prob[i]) if i < len(precip_prob) and precip_prob[i] is not None else 0,
                        "weather_code": weather_code,
                        "conditions": WEATHER_CODES.get(weather_code, "Unknown"),
                        "wind_speed": round(wind_speeds[i], 1) if i < len(wind_speeds) else None
                    })

                return [TextContent(
                    type="text",
                    text=json.dumps(result, indent=2)
                )]

        except httpx.TimeoutException:
            return [TextContent(
                type="text",
                text=json.dumps({"error": "Request timeout. Please try again."})
            )]
        except httpx.RequestError as e:
            return [TextContent(
                type="text",
                text=json.dumps({"error": f"Network error: {str(e)}"})
            )]
        except Exception as e:
            return [TextContent(
                type="text",
                text=json.dumps({"error": f"Unexpected error: {str(e)}"})
            )]

    return [TextContent(
        type="text",
        text=json.dumps({"error": f"Unknown tool: {name}"})
    )]


async def main():
    """Main entry point"""
    async with mcp.server.stdio.stdio_server() as (read_stream, write_stream):
        await app.run(
            read_stream,
            write_stream,
            app.create_initialization_options(),
        )


if __name__ == "__main__":
    asyncio.run(main())
