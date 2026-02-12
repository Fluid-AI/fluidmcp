#!/usr/bin/env python3
"""
Weather MCP Server - Raw MCP SDK Version
Provides weather information with embedded UI (compatible with FluidMCP)

This version uses the raw MCP SDK (not FastMCP) to ensure compatibility
with FluidMCP's gateway proxy, following the same pattern as games-hub.
"""

import asyncio
import json
import logging
from typing import Any

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

from tools.weather import get_current_weather, get_forecast_data, search_cities

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("weather-mcp")

# Initialize MCP server
app = Server("weather-mcp")


def generate_weather_html(weather_data: dict) -> str:
    """Generate self-contained HTML with embedded CSS and JavaScript."""

    city = weather_data.get("city", "Unknown")
    temperature = weather_data.get("temperature", "--")
    condition = weather_data.get("condition", "--")
    description = weather_data.get("description", "No description")
    humidity = weather_data.get("humidity", "--")
    wind_speed = weather_data.get("wind_speed", "--")
    units = weather_data.get("units", "metric")
    timestamp = weather_data.get("timestamp", "")

    temp_symbol = "°C" if units == "metric" else "°F"

    # Weather icon mapping
    icon_map = {
        'Sunny': '☀️',
        'Cloudy': '☁️',
        'Rainy': '🌧️',
        'Stormy': '⛈️',
        'Snowy': '❄️',
        'Clear': '🌙'
    }
    weather_icon = icon_map.get(condition, '🌤️')

    # Generate complete HTML with embedded CSS and JS
    html = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Weather in {city}</title>
    <style>
        :root {{
            --bg-dark: #0f0f1e;
            --card-bg: #1a1a2e;
            --text-primary: #e0e0e0;
            --text-secondary: #a0a0a0;
            --accent-blue: #4a9eff;
            --accent-purple: #8b5cf6;
            --accent-green: #10b981;
            --border-color: #2a2a3e;
            --border-radius: 12px;
            --shadow: 0 4px 6px rgba(0,0,0,0.3);
            --shadow-hover: 0 8px 16px rgba(0,0,0,0.4);
        }}
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
            background: var(--bg-dark);
            color: var(--text-primary);
            min-height: 100vh;
            padding: 20px;
            line-height: 1.6;
        }}
        .container {{ max-width: 600px; margin: 0 auto; }}
        .header {{ text-align: center; margin-bottom: 30px; }}
        .header h1 {{ font-size: 28px; font-weight: 600; }}
        .weather-card {{
            background: var(--card-bg);
            border-radius: var(--border-radius);
            padding: 40px 32px;
            text-align: center;
            box-shadow: var(--shadow);
            border: 1px solid var(--border-color);
            transition: transform 0.3s ease, box-shadow 0.3s ease;
        }}
        .weather-card:hover {{
            transform: translateY(-2px);
            box-shadow: var(--shadow-hover);
        }}
        .city-name {{
            font-size: 32px;
            font-weight: 600;
            margin-bottom: 20px;
            color: var(--accent-blue);
        }}
        .weather-icon {{
            font-size: 80px;
            margin: 20px 0;
            animation: float 3s ease-in-out infinite;
        }}
        @keyframes float {{
            0%, 100% {{ transform: translateY(0); }}
            50% {{ transform: translateY(-10px); }}
        }}
        .temperature {{
            font-size: 64px;
            font-weight: 300;
            margin: 20px 0;
            color: var(--text-primary);
        }}
        .condition {{
            font-size: 24px;
            color: var(--text-secondary);
            margin-bottom: 12px;
            font-weight: 500;
        }}
        .description {{
            font-size: 16px;
            color: var(--text-secondary);
            margin-bottom: 32px;
            font-style: italic;
        }}
        .details-grid {{
            display: grid;
            grid-template-columns: repeat(2, 1fr);
            gap: 24px;
            margin-top: 32px;
            padding-top: 32px;
            border-top: 1px solid var(--border-color);
        }}
        .detail-item {{
            display: flex;
            flex-direction: column;
            gap: 8px;
        }}
        .detail-label {{
            font-size: 12px;
            text-transform: uppercase;
            letter-spacing: 1px;
            color: var(--text-secondary);
            font-weight: 600;
        }}
        .detail-value {{
            font-size: 28px;
            font-weight: 600;
            color: var(--accent-purple);
        }}
        .timestamp {{
            margin-top: 24px;
            font-size: 14px;
            color: var(--text-secondary);
            font-style: italic;
        }}
        .info-box {{
            background: var(--card-bg);
            border-radius: var(--border-radius);
            padding: 16px 20px;
            border: 1px solid var(--border-color);
            text-align: center;
            margin-top: 20px;
        }}
        .info-box p {{
            font-size: 13px;
            color: var(--text-secondary);
            margin: 4px 0;
        }}
        .info-box strong {{ color: var(--accent-green); }}
        @media (max-width: 600px) {{
            body {{ padding: 16px; }}
            .header h1 {{ font-size: 24px; }}
            .weather-card {{ padding: 32px 24px; }}
            .city-name {{ font-size: 28px; }}
            .temperature {{ font-size: 52px; }}
            .weather-icon {{ font-size: 64px; }}
            .condition {{ font-size: 20px; }}
            .details-grid {{ grid-template-columns: 1fr; gap: 16px; }}
            .detail-value {{ font-size: 24px; }}
        }}
    </style>
</head>
<body>
    <div class="container">
        <header class="header">
            <h1>🌤️ Weather Dashboard</h1>
        </header>

        <div class="weather-card">
            <div class="city-name">{city}</div>
            <div class="weather-icon">{weather_icon}</div>
            <div class="temperature">{temperature}{temp_symbol}</div>
            <div class="condition">{condition}</div>
            <div class="description">{description}</div>

            <div class="details-grid">
                <div class="detail-item">
                    <span class="detail-label">Humidity</span>
                    <span class="detail-value">{humidity}%</span>
                </div>
                <div class="detail-item">
                    <span class="detail-label">Wind Speed</span>
                    <span class="detail-value">{wind_speed} km/h</span>
                </div>
            </div>

            <div class="timestamp">Updated: {timestamp_display}</div>
        </div>

        <div class="info-box">
            <p><strong>Weather MCP App</strong> - Data provided via MCP protocol</p>
            <p>Units: {units_display} | Source: Mock Data (Phase 1)</p>
        </div>
    </div>
</body>
</html>"""

    # Format timestamp
    timestamp_display = timestamp.split('T')[1].split('.')[0] if 'T' in timestamp else 'Now'
    units_display = units.title()

    # Format the HTML with actual data
    return html.format(
        city=city,
        weather_icon=weather_icon,
        temperature=temperature,
        temp_symbol=temp_symbol,
        condition=condition,
        description=description,
        humidity=humidity,
        wind_speed=wind_speed,
        timestamp_display=timestamp_display,
        units_display=units_display
    )


@app.list_tools()
async def list_tools() -> list[Tool]:
    """List available weather tools"""
    return [
        Tool(
            name="get_weather",
            description="Get current weather for a city with embedded visual UI. Returns complete HTML with weather data for display.",
            inputSchema={
                "type": "object",
                "properties": {
                    "city": {
                        "type": "string",
                        "description": "City name (e.g., 'Bangalore', 'Mumbai', 'Delhi')"
                    },
                    "units": {
                        "type": "string",
                        "description": "Temperature units - 'metric' (Celsius) or 'imperial' (Fahrenheit)",
                        "enum": ["metric", "imperial"],
                        "default": "metric"
                    }
                },
                "required": ["city"]
            }
        ),
        Tool(
            name="search_city",
            description="Search for cities by name. Returns list of cities matching the query.",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "City name or partial name to search"
                    }
                },
                "required": ["query"]
            }
        ),
        Tool(
            name="get_forecast",
            description="Get weather forecast for multiple days (Phase 2 implementation pending).",
            inputSchema={
                "type": "object",
                "properties": {
                    "city": {
                        "type": "string",
                        "description": "City name"
                    },
                    "days": {
                        "type": "integer",
                        "description": "Number of forecast days (1-10)",
                        "default": 5,
                        "minimum": 1,
                        "maximum": 10
                    },
                    "units": {
                        "type": "string",
                        "description": "Temperature units",
                        "enum": ["metric", "imperial"],
                        "default": "metric"
                    }
                },
                "required": ["city"]
            }
        )
    ]


@app.call_tool()
async def call_tool(name: str, arguments: Any) -> list[TextContent]:
    """Handle tool calls"""
    try:
        # Ensure arguments is never None
        if arguments is None:
            arguments = {}

        if name == "get_weather":
            city = arguments.get("city", "")
            units = arguments.get("units", "metric")

            logger.info(f"Getting weather for: {city} (units: {units})")

            # Get weather data from tools
            weather_data = get_current_weather(city, units)

            # Generate and return embedded HTML
            html = generate_weather_html(weather_data)

            return [TextContent(type="text", text=html)]

        elif name == "search_city":
            query = arguments.get("query", "")

            logger.info(f"Searching cities: {query}")

            cities = search_cities(query)

            result = {
                "query": query,
                "results": cities,
                "count": len(cities)
            }

            return [TextContent(type="text", text=json.dumps(result, indent=2))]

        elif name == "get_forecast":
            city = arguments.get("city", "")
            days = arguments.get("days", 5)
            units = arguments.get("units", "metric")

            logger.info(f"Getting forecast for: {city} ({days} days)")

            result = {
                "message": f"Forecast for {city}",
                "note": "Full forecast implementation coming in Phase 2",
                "city": city,
                "days": days,
                "units": units
            }

            return [TextContent(type="text", text=json.dumps(result, indent=2))]

        else:
            return [TextContent(type="text", text=f"Unknown tool: {name}")]

    except Exception as e:
        logger.error(f"Error executing {name}: {str(e)}")
        return [TextContent(type="text", text=f"Error: {str(e)}")]


async def main():
    """Run the MCP server"""
    logger.info("Starting Weather MCP Server with embedded HTML")
    async with stdio_server() as (read_stream, write_stream):
        await app.run(
            read_stream,
            write_stream,
            app.create_initialization_options(),
        )


if __name__ == "__main__":
    asyncio.run(main())
