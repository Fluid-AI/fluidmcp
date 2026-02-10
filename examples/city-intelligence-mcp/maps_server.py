#!/usr/bin/env python3
"""
Maps MCP Server - Creates day-by-day itineraries from attractions
Can optionally use OSRM for real routing data (free, no API key required)
"""
import asyncio
import json
from typing import Any
from datetime import datetime, timedelta
import httpx

from mcp.server import Server
from mcp.types import Tool, TextContent
import mcp.server.stdio

# Initialize MCP server
app = Server("maps")


def calculate_visit_duration(attraction_type: str) -> int:
    """Estimate visit duration in minutes based on attraction type"""
    duration_map = {
        "museum": 120,
        "castle": 90,
        "palace": 90,
        "monument": 45,
        "memorial": 30,
        "fort": 90,
        "archaeological_site": 90,
        "ruins": 60,
        "attraction": 60,
        "viewpoint": 30,
        "artwork": 20,
        "gallery": 90,
        "theme_park": 240,
        "zoo": 180,
        "place_of_worship": 45
    }
    return duration_map.get(attraction_type, 60)  # Default 60 minutes


async def get_travel_time(lat1: float, lon1: float, lat2: float, lon2: float) -> int:
    """
    Get travel time between two points using OSRM (optional, free)
    Returns estimated travel time in minutes
    Falls back to simple estimation if OSRM fails
    """
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            route_url = f"http://router.project-osrm.org/route/v1/driving/{lon1},{lat1};{lon2},{lat2}"
            response = await client.get(
                route_url,
                params={"overview": "false"}
            )

            if response.status_code == 200:
                data = response.json()
                if "routes" in data and len(data["routes"]) > 0:
                    # Duration is in seconds, convert to minutes
                    duration_seconds = data["routes"][0]["duration"]
                    return max(5, int(duration_seconds / 60))  # Minimum 5 minutes

    except Exception:
        pass  # Fall back to estimation

    # Fallback: Simple distance-based estimation
    # Approximate: 1 degree ≈ 111 km, average speed 30 km/h in city
    lat_diff = abs(lat2 - lat1)
    lon_diff = abs(lon2 - lon1)
    distance_km = ((lat_diff ** 2 + lon_diff ** 2) ** 0.5) * 111
    travel_minutes = int((distance_km / 30) * 60)  # 30 km/h average city speed

    return max(5, min(travel_minutes, 60))  # Between 5 and 60 minutes


@app.list_tools()
async def list_tools() -> list[Tool]:
    """List available maps tools"""
    return [
        Tool(
            name="create_itinerary",
            description="Create a day-by-day itinerary from a list of attractions",
            inputSchema={
                "type": "object",
                "properties": {
                    "city": {
                        "type": "string",
                        "description": "City name"
                    },
                    "days": {
                        "type": "integer",
                        "default": 2,
                        "description": "Number of days for the trip (1-7)"
                    },
                    "attractions": {
                        "type": "array",
                        "description": "List of attractions with name, type, and coordinates",
                        "items": {
                            "type": "object",
                            "properties": {
                                "name": {"type": "string"},
                                "type": {"type": "string"},
                                "coordinates": {
                                    "type": "object",
                                    "properties": {
                                        "lat": {"type": "number"},
                                        "lon": {"type": "number"}
                                    }
                                }
                            }
                        }
                    },
                    "start_time": {
                        "type": "string",
                        "default": "09:00",
                        "description": "Daily start time (HH:MM format)"
                    },
                    "end_time": {
                        "type": "string",
                        "default": "18:00",
                        "description": "Daily end time (HH:MM format)"
                    }
                },
                "required": ["city", "attractions"]
            }
        )
    ]


@app.call_tool()
async def call_tool(name: str, arguments: Any) -> list[TextContent]:
    """Handle tool calls"""
    if name == "create_itinerary":
        try:
            city = arguments["city"]
            days = arguments.get("days", 2)
            attractions = arguments.get("attractions", [])
            start_time_str = arguments.get("start_time", "09:00")
            end_time_str = arguments.get("end_time", "18:00")

            # Validate inputs
            if days < 1 or days > 7:
                return [TextContent(
                    type="text",
                    text=json.dumps({"error": "Days must be between 1 and 7"})
                )]

            if not attractions or len(attractions) == 0:
                return [TextContent(
                    type="text",
                    text=json.dumps({
                        "error": "No attractions provided. Please provide a list of attractions."
                    })
                )]

            # Parse start and end times
            try:
                start_time = datetime.strptime(start_time_str, "%H:%M")
                end_time = datetime.strptime(end_time_str, "%H:%M")
            except ValueError:
                return [TextContent(
                    type="text",
                    text=json.dumps({
                        "error": "Invalid time format. Use HH:MM (e.g., '09:00')"
                    })
                )]

            # Calculate available hours per day
            daily_minutes = (end_time - start_time).seconds // 60

            if daily_minutes <= 0:
                return [TextContent(
                    type="text",
                    text=json.dumps({
                        "error": "End time must be after start time"
                    })
                )]

            # Create itinerary
            itinerary = []
            attractions_per_day = max(1, len(attractions) // days)

            for day_num in range(days):
                # Select attractions for this day
                start_idx = day_num * attractions_per_day
                end_idx = (day_num + 1) * attractions_per_day if day_num < days - 1 else len(attractions)
                day_attractions = attractions[start_idx:end_idx]

                if len(day_attractions) == 0:
                    continue

                # Initialize day plan
                day_date = (datetime.now() + timedelta(days=day_num)).strftime("%Y-%m-%d")
                day_plan = {
                    "day": day_num + 1,
                    "date": day_date,
                    "schedule": []
                }

                # Start time for the day
                current_time = start_time

                for i, attraction in enumerate(day_attractions):
                    # Calculate visit duration based on type
                    visit_duration = calculate_visit_duration(
                        attraction.get("type", "attraction")
                    )

                    # Check if we have time left in the day
                    minutes_used = (current_time - start_time).seconds // 60
                    if minutes_used + visit_duration > daily_minutes:
                        break  # No more time today

                    # Get coordinates
                    coords = attraction.get("coordinates", {})
                    lat = coords.get("lat", 0)
                    lon = coords.get("lon", 0)

                    # Calculate travel time to next attraction
                    travel_time = 0
                    if i < len(day_attractions) - 1:
                        next_coords = day_attractions[i + 1].get("coordinates", {})
                        next_lat = next_coords.get("lat", 0)
                        next_lon = next_coords.get("lon", 0)

                        if lat != 0 and lon != 0 and next_lat != 0 and next_lon != 0:
                            travel_time = await get_travel_time(lat, lon, next_lat, next_lon)
                        else:
                            travel_time = 20  # Default travel time

                    # Add activity to schedule
                    day_plan["schedule"].append({
                        "time": current_time.strftime("%H:%M"),
                        "activity": attraction.get("name", "Unnamed attraction"),
                        "type": attraction.get("type", "attraction"),
                        "duration_minutes": visit_duration,
                        "location": coords,
                        "travel_to_next_minutes": travel_time
                    })

                    # Advance time
                    current_time += timedelta(minutes=visit_duration + travel_time)

                    # Add lunch break after ~2 activities (around noon)
                    if i == 1 and len(day_attractions) > 3:
                        lunch_time = current_time
                        if lunch_time.hour < 13:  # Before 1 PM
                            day_plan["schedule"].append({
                                "time": current_time.strftime("%H:%M"),
                                "activity": "🍽️ Lunch break",
                                "type": "meal",
                                "duration_minutes": 60,
                                "location": {},
                                "travel_to_next_minutes": 0
                            })
                            current_time += timedelta(minutes=60)

                itinerary.append(day_plan)

            # Build result
            total_activities = sum(len(day["schedule"]) for day in itinerary)

            result = {
                "city": city,
                "days": days,
                "total_activities": total_activities,
                "start_time": start_time_str,
                "end_time": end_time_str,
                "itinerary": itinerary
            }

            return [TextContent(
                type="text",
                text=json.dumps(result, indent=2)
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
