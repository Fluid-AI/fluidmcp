#!/usr/bin/env python3
"""
Places MCP Server - Uses OpenTripMap API for global tourist attractions
Free tier: 5,000 requests/day with API key
"""
import asyncio
import json
import os
from typing import Any
import httpx

from mcp.server import Server
from mcp.types import Tool, TextContent
import mcp.server.stdio

# Initialize MCP server
app = Server("places")


@app.list_tools()
async def list_tools() -> list[Tool]:
    """List available places tools"""
    return [
        Tool(
            name="get_attractions",
            description="Get tourist attractions and points of interest in a city (uses free OpenStreetMap data)",
            inputSchema={
                "type": "object",
                "properties": {
                    "city": {
                        "type": "string",
                        "description": "City name (e.g., 'Jaipur', 'Paris', 'Tokyo')"
                    },
                    "limit": {
                        "type": "integer",
                        "default": 10,
                        "description": "Maximum number of attractions to return (1-50)"
                    },
                    "radius_km": {
                        "type": "number",
                        "default": 5.0,
                        "description": "Search radius in kilometers from city center (1-20)"
                    }
                },
                "required": ["city"]
            }
        )
    ]


@app.call_tool()
async def call_tool(name: str, arguments: Any) -> list[TextContent]:
    """Handle tool calls"""
    if name == "get_attractions":
        try:
            city = arguments["city"]
            limit = arguments.get("limit", 10)
            radius_km = arguments.get("radius_km", 5.0)

            # Validate inputs
            if not city or not isinstance(city, str):
                return [TextContent(
                    type="text",
                    text=json.dumps({"error": "Invalid city name"})
                )]

            if limit < 1 or limit > 50:
                return [TextContent(
                    type="text",
                    text=json.dumps({"error": "Limit must be between 1 and 50"})
                )]

            if radius_km < 1 or radius_km > 20:
                return [TextContent(
                    type="text",
                    text=json.dumps({"error": "Radius must be between 1 and 20 km"})
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

                # Rate limit: Wait 1 second after Nominatim call (their requirement)
                await asyncio.sleep(1.1)

                # Step 2: Query OpenTripMap API (FREE 5,000 requests/day!)
                # Get API key from environment or use test key
                otm_api_key = os.environ.get("OPENTRIPMAP_API_KEY", "5ae2e3f221c38a28845f05b6c2fb5d9ab1ef5c5e85c7a53cc1b3c92a")

                radius_meters = int(radius_km * 1000)

                # OpenTripMap radius endpoint - finds POIs within radius
                otm_url = "https://api.opentripmap.com/0.1/en/places/radius"
                params = {
                    "radius": radius_meters,
                    "lon": lon,
                    "lat": lat,
                    "kinds": "interesting_places,tourist_facilities,museums,cultural,historic,architecture,monuments",
                    "limit": limit * 2,  # Get extra to filter
                    "apikey": otm_api_key
                }

                otm_resp = await client.get(otm_url, params=params, timeout=30.0)

                if otm_resp.status_code != 200:
                    return [TextContent(
                        type="text",
                        text=json.dumps({
                            "error": f"OpenTripMap API error: {otm_resp.status_code} - {otm_resp.text[:200]}",
                            "city": city,
                            "attractions": []
                        })
                    )]

                otm_data = otm_resp.json()

                # Step 3: Format attractions from OpenTripMap
                attractions = []
                seen_names = set()  # Avoid duplicates

                places = otm_data if isinstance(otm_data, list) else []

                for place in places:
                    name = place.get("name", "")

                    # Skip unnamed places
                    if not name or name == "":
                        continue

                    # Skip duplicates
                    if name in seen_names:
                        continue
                    seen_names.add(name)

                    # Get coordinates from point object
                    point = place.get("point", {})
                    elem_lat = point.get("lat")
                    elem_lon = point.get("lon")

                    if elem_lat is None or elem_lon is None:
                        continue

                    # Get distance
                    distance = place.get("dist", 0)

                    # Get kinds (types of attraction)
                    kinds = place.get("kinds", "")
                    attraction_type = kinds.split(",")[0].replace("_", " ").title() if kinds else "Attraction"

                    description = f"{attraction_type} • {int(distance)}m from center"

                    attraction = {
                        "name": name,
                        "type": attraction_type,
                        "description": description,
                        "coordinates": {
                            "lat": float(elem_lat),
                            "lon": float(elem_lon)
                        }
                    }

                    # Add xid for getting more details if needed
                    if place.get("xid"):
                        attraction["xid"] = place["xid"]

                    attractions.append(attraction)

                    # Stop if we have enough
                    if len(attractions) >= limit:
                        break

                # Sort attractions by distance from city center (optional improvement)
                def distance(attr):
                    """Calculate approximate distance from city center"""
                    lat_diff = attr["coordinates"]["lat"] - lat
                    lon_diff = attr["coordinates"]["lon"] - lon
                    return lat_diff ** 2 + lon_diff ** 2

                attractions.sort(key=distance)

                # Build result
                result = {
                    "city": city,
                    "display_name": display_name,
                    "center_coordinates": {
                        "lat": lat,
                        "lon": lon
                    },
                    "search_radius_km": radius_km,
                    "attractions_found": len(attractions),
                    "attractions": attractions[:limit]  # Ensure we don't exceed limit
                }

                return [TextContent(
                    type="text",
                    text=json.dumps(result, indent=2)
                )]

        except httpx.TimeoutException:
            return [TextContent(
                type="text",
                text=json.dumps({
                    "error": "Request timeout. The Overpass API may be busy. Please try again."
                })
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
