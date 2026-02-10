#!/usr/bin/env python3
"""
City Intelligence MCP Server - Direct API calls (no orchestration)
Calls weather, places APIs directly to avoid orchestration deadlock
"""
import asyncio
import json
import os
import html as html_module
from datetime import datetime, timedelta
from typing import Any, Dict
import httpx

from mcp.server import Server
from mcp.types import Tool, TextContent
import mcp.server.stdio

# Initialize MCP server
app = Server("city-intelligence")

# Weather code mapping
WEATHER_CODES = {
    0: "Clear sky", 1: "Mainly clear", 2: "Partly cloudy", 3: "Overcast",
    45: "Foggy", 61: "Light rain", 63: "Moderate rain", 65: "Heavy rain",
    80: "Light rain showers", 95: "Thunderstorm"
}


async def get_weather_direct(city: str, days: int = 3):
    """Get weather forecast directly from Open-Meteo API"""
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            # Geocode
            geo_resp = await client.get(
                "https://nominatim.openstreetmap.org/search",
                params={"q": city, "format": "json", "limit": 1},
                headers={"User-Agent": "FluidMCP-CityIntelligence/1.0"}
            )
            locations = geo_resp.json()
            if not locations:
                return None

            lat, lon = locations[0]["lat"], locations[0]["lon"]
            await asyncio.sleep(1.1)

            # Get weather
            weather_resp = await client.get(
                "https://api.open-meteo.com/v1/forecast",
                params={
                    "latitude": lat,
                    "longitude": lon,
                    "daily": "temperature_2m_max,temperature_2m_min,precipitation_probability_max,weathercode",
                    "timezone": "auto",
                    "forecast_days": days
                }
            )
            weather = weather_resp.json()

            daily = weather.get("daily", {})
            forecast = []
            for i in range(len(daily.get("time", []))):
                forecast.append({
                    "date": daily["time"][i],
                    "temp_high": daily["temperature_2m_max"][i],
                    "temp_low": daily["temperature_2m_min"][i],
                    "precipitation_chance": daily["precipitation_probability_max"][i],
                    "conditions": WEATHER_CODES.get(daily["weathercode"][i], "Unknown")
                })

            return {"city": city, "forecast": forecast}
    except Exception as e:
        print(f"Weather error: {e}")
        return None


async def get_attractions_direct(city: str, limit: int = 10):
    """Get attractions directly from Geoapify API"""
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            # Geocode
            geo_resp = await client.get(
                "https://nominatim.openstreetmap.org/search",
                params={"q": city, "format": "json", "limit": 1},
                headers={"User-Agent": "FluidMCP-CityIntelligence/1.0"}
            )
            locations = geo_resp.json()
            if not locations:
                return None

            lat, lon = float(locations[0]["lat"]), float(locations[0]["lon"])
            await asyncio.sleep(1.1)

            # Geoapify API
            geoapify_key = os.environ.get("GEOAPIFY_API_KEY", "f628c3a56d724117b4028da5cd72adb7")
            geo_url = "https://api.geoapify.com/v2/places"
            params = {
                "categories": "tourism.sights,tourism.attraction,heritage,entertainment.museum",
                "filter": f"circle:{lon},{lat},5000",
                "limit": limit,
                "apiKey": geoapify_key
            }

            geo_resp = await client.get(geo_url, params=params)
            if geo_resp.status_code != 200:
                # Fallback
                fallback_file = os.path.join(os.path.dirname(__file__), "fallback_attractions.json")
                if os.path.exists(fallback_file):
                    with open(fallback_file) as f:
                        fallback_data = json.load(f)
                        if city in fallback_data:
                            return {"city": city, "attractions": fallback_data[city][:limit]}
                return None

            geo_data = geo_resp.json()
            places = geo_data.get("features", [])

            attractions = []
            seen_names = set()

            for place in places[:limit]:
                props = place.get("properties", {})
                name = props.get("name", "")
                if not name or name in seen_names:
                    continue
                seen_names.add(name)

                geom = place.get("geometry", {})
                coords = geom.get("coordinates", [])
                if len(coords) < 2:
                    continue

                attractions.append({
                    "name": name,
                    "type": "Attraction",
                    "coordinates": {"lat": float(coords[1]), "lon": float(coords[0])}
                })

            return {"city": city, "attractions": attractions}
    except Exception as e:
        print(f"Attractions error: {e}")
        return None


def create_itinerary_direct(city: str, days: int, attractions: list):
    """Create day-by-day itinerary"""
    if not attractions:
        return []

    itinerary = []
    attractions_per_day = max(1, len(attractions) // days)

    for day_num in range(days):
        start_idx = day_num * attractions_per_day
        end_idx = (day_num + 1) * attractions_per_day if day_num < days - 1 else len(attractions)
        day_attractions = attractions[start_idx:end_idx]

        if not day_attractions:
            continue

        day_plan = {
            "day": day_num + 1,
            "date": (datetime.now() + timedelta(days=day_num)).strftime("%Y-%m-%d"),
            "schedule": []
        }

        current_time = datetime.strptime("09:00", "%H:%M")

        for i, attraction in enumerate(day_attractions):
            travel_time = 20  # 20 minutes
            visit_duration = 90  # 90 minutes

            day_plan["schedule"].append({
                "time": current_time.strftime("%H:%M"),
                "activity": attraction["name"],
                "duration_minutes": visit_duration,
                "travel_to_next_minutes": travel_time if i < len(day_attractions) - 1 else 0
            })

            current_time += timedelta(minutes=visit_duration + travel_time)

            # Lunch break after 2 attractions
            if i == 1:
                day_plan["schedule"].append({
                    "time": current_time.strftime("%H:%M"),
                    "activity": "🍽️ Lunch break",
                    "duration_minutes": 60,
                    "travel_to_next_minutes": 0
                })
                current_time += timedelta(minutes=60)

        itinerary.append(day_plan)

    return itinerary


def generate_html(city_name: str, duration_days: int, weather: dict, places: dict, itinerary: list):
    """Generate interactive HTML"""
    # Calculate stats
    avg_temp = "N/A"
    weather_summary = "Weather data unavailable"
    weather_json = json.dumps({"forecast": []})

    if weather and weather.get("forecast"):
        temps = [d["temp_high"] for d in weather["forecast"]]
        avg_temp = f"{sum(temps) / len(temps):.1f}"
        conditions = [d["conditions"] for d in weather["forecast"][:3]]
        weather_summary = ", ".join(set(conditions))
        weather_json = json.dumps(weather)

    num_attractions = len(places.get("attractions", [])) if places else 0
    places_json = json.dumps(places if places else {"attractions": []})
    total_activities = sum(len(day["schedule"]) for day in itinerary)

    # Generate itinerary HTML with embedded styles
    itinerary_content = ""
    for day in itinerary:
        itinerary_content += f'<div class="day"><div class="day-header">📅 Day {day["day"]} - {day["date"]}</div>'
        for activity in day["schedule"]:
            itinerary_content += f'''<div class="activity">
                <div class="time">{activity["time"]}</div>
                <div class="activity-details">
                    <div class="activity-name">{activity["activity"]}</div>
                    <div class="duration">⏱️ {activity["duration_minutes"]} min'''
            if activity["travel_to_next_minutes"] > 0:
                itinerary_content += f' • 🚗 {activity["travel_to_next_minutes"]} min to next'
            itinerary_content += '</div></div></div>'
        itinerary_content += '</div>'

    # Wrap itinerary with complete HTML including styles for iframe
    itinerary_html = f'''<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
            background: #16162a;
            color: #e0e0e0;
            padding: 20px;
        }}
        .day {{
            background: #1a1a2e;
            border-radius: 12px;
            padding: 24px;
            margin-bottom: 24px;
            border: 1px solid #2a2a3e;
        }}
        .day-header {{
            font-size: 20px;
            color: #8b5cf6;
            font-weight: 600;
            margin-bottom: 20px;
            padding-bottom: 12px;
            border-bottom: 2px solid #2a2a3e;
        }}
        .activity {{
            display: flex;
            gap: 20px;
            padding: 16px;
            margin-bottom: 12px;
            background: #2a2a3e;
            border-radius: 8px;
            border-left: 4px solid #8b5cf6;
            transition: all 0.2s ease;
        }}
        .activity:hover {{
            background: #323248;
            border-left-color: #a78bfa;
        }}
        .time {{
            color: #8b5cf6;
            font-weight: bold;
            font-size: 14px;
            min-width: 60px;
        }}
        .activity-details {{
            flex: 1;
        }}
        .activity-name {{
            font-size: 16px;
            color: #e0e0e0;
            margin-bottom: 6px;
        }}
        .duration {{
            font-size: 13px;
            color: #a0a0b0;
        }}
    </style>
</head>
<body>
    {itinerary_content}
</body>
</html>'''

    itinerary_html_escaped = html_module.escape(itinerary_html).replace('"', '&quot;')

    # Generate full HTML
    html_content = f'''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{city_name} Trip Plan</title>
    <script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
    <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
    <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; background: #0f0f1e; color: #e0e0e0; padding: 20px; }}
        .container {{ max-width: 1400px; margin: 0 auto; background: #1a1a2e; border-radius: 12px; padding: 30px; border: 1px solid #2a2a3e; }}
        .header {{ border-bottom: 2px solid #2a2a3e; padding-bottom: 20px; margin-bottom: 30px; }}
        h1 {{ font-size: 32px; color: #e0e0e0; }}
        .city-name {{ color: #8b5cf6; }}
        .subtitle {{ color: #a0a0b0; font-size: 14px; margin-top: 8px; }}
        .city-cards {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 20px; margin-bottom: 40px; }}
        .card {{ background: #2a2a3e; border-radius: 12px; padding: 24px; border: 1px solid #3a3a4e; transition: all 0.3s; }}
        .card:hover {{ transform: translateY(-5px); border-color: #8b5cf6; }}
        .card-title {{ font-size: 12px; color: #a0a0b0; margin-bottom: 12px; text-transform: uppercase; letter-spacing: 1.5px; }}
        .card-value {{ font-size: 36px; color: #8b5cf6; font-weight: bold; }}
        .card-subtitle {{ color: #a0a0b0; font-size: 14px; margin-top: 8px; }}
        .chart-section {{ margin: 40px 0; }}
        .chart-section h2 {{ font-size: 24px; margin-bottom: 20px; }}
        .chart-container {{ background: #16162a; border-radius: 12px; padding: 24px; margin-bottom: 20px; height: 320px; border: 1px solid #2a2a3e; }}
        .itinerary-section {{ margin-top: 40px; }}
        .itinerary-section h2 {{ font-size: 24px; margin-bottom: 20px; }}
        .itinerary-frame {{ width: 100%; height: 600px; border: none; border-radius: 12px; background: #16162a; }}
        body {{ font-family: -apple-system, sans-serif; background: #16162a; color: #e0e0e0; padding: 20px; margin: 0; }}
        .day {{ background: #1a1a2e; border-radius: 8px; padding: 20px; margin-bottom: 20px; border: 1px solid #2a2a3e; }}
        .day-header {{ font-size: 20px; color: #8b5cf6; margin-bottom: 15px; border-bottom: 1px solid #2a2a3e; padding-bottom: 10px; }}
        .activity {{ display: flex; gap: 15px; padding: 15px; margin-bottom: 10px; background: #2a2a3e; border-radius: 6px; border-left: 3px solid #8b5cf6; }}
        .time {{ color: #8b5cf6; font-weight: bold; min-width: 60px; }}
        .activity-details {{ flex: 1; }}
        .activity-name {{ font-size: 16px; margin-bottom: 5px; }}
        .duration {{ font-size: 12px; color: #a0a0b0; }}
        .map-section {{ margin: 40px 0; }}
        .map-section h2 {{ font-size: 24px; margin-bottom: 20px; }}
        #map {{ height: 500px; width: 100%; border-radius: 12px; border: 1px solid #2a2a3e; }}
        .leaflet-popup-content-wrapper {{ background: #1a1a2e; color: #e0e0e0; }}
        .leaflet-popup-tip {{ background: #1a1a2e; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🏙️ <span class="city-name">{city_name}</span> - {duration_days}-Day Trip</h1>
            <div class="subtitle">Your personalized itinerary with live weather and local attractions</div>
        </div>
        <div class="city-cards">
            <div class="card">
                <div class="card-title">☀️ Weather</div>
                <div class="card-value">{avg_temp}°C</div>
                <div class="card-subtitle">{weather_summary}</div>
            </div>
            <div class="card">
                <div class="card-title">🎯 Attractions</div>
                <div class="card-value">{num_attractions}</div>
                <div class="card-subtitle">Places to visit</div>
            </div>
            <div class="card">
                <div class="card-title">📅 Activities</div>
                <div class="card-value">{total_activities}</div>
                <div class="card-subtitle">Planned over {duration_days} days</div>
            </div>
        </div>
        <div class="map-section">
            <h2>🗺️ Attractions Map</h2>
            <div id="map"></div>
        </div>
        <div class="chart-section">
            <h2>📊 Weather Forecast</h2>
            <div class="chart-container"><canvas id="tempChart"></canvas></div>
            <div class="chart-container"><canvas id="precipChart"></canvas></div>
        </div>
        <div class="itinerary-section">
            <h2>🗓️ Day-by-Day Itinerary</h2>
            <iframe class="itinerary-frame" srcdoc='{itinerary_html_escaped}'></iframe>
        </div>
    </div>
    <script>
        const weatherData = {weather_json};
        const placesData = {places_json};
        if (weatherData.forecast && weatherData.forecast.length > 0) {{
            const tempCtx = document.getElementById('tempChart').getContext('2d');
            new Chart(tempCtx, {{
                type: 'line',
                data: {{
                    labels: weatherData.forecast.map(d => d.date),
                    datasets: [{{
                        label: 'High Temperature (°C)',
                        data: weatherData.forecast.map(d => d.temp_high),
                        borderColor: '#f59e0b',
                        backgroundColor: 'rgba(245,158,11,0.2)',
                        tension: 0.4,
                        fill: true
                    }}, {{
                        label: 'Low Temperature (°C)',
                        data: weatherData.forecast.map(d => d.temp_low),
                        borderColor: '#3b82f6',
                        backgroundColor: 'rgba(59,130,246,0.2)',
                        tension: 0.4,
                        fill: true
                    }}]
                }},
                options: {{
                    responsive: true,
                    maintainAspectRatio: false,
                    scales: {{
                        y: {{ ticks: {{ color: '#a0a0b0' }}, grid: {{ color: '#2a2a3e' }} }},
                        x: {{ ticks: {{ color: '#a0a0b0' }}, grid: {{ color: '#2a2a3e' }} }}
                    }},
                    plugins: {{ legend: {{ labels: {{ color: '#e0e0e0' }} }} }}
                }}
            }});
            const precipCtx = document.getElementById('precipChart').getContext('2d');
            new Chart(precipCtx, {{
                type: 'bar',
                data: {{
                    labels: weatherData.forecast.map(d => d.date),
                    datasets: [{{
                        label: 'Precipitation (%)',
                        data: weatherData.forecast.map(d => d.precipitation_chance),
                        backgroundColor: '#8b5cf6'
                    }}]
                }},
                options: {{
                    responsive: true,
                    maintainAspectRatio: false,
                    scales: {{
                        y: {{ beginAtZero: true, max: 100, ticks: {{ color: '#a0a0b0' }}, grid: {{ color: '#2a2a3e' }} }},
                        x: {{ ticks: {{ color: '#a0a0b0' }}, grid: {{ color: '#2a2a3e' }} }}
                    }},
                    plugins: {{ legend: {{ labels: {{ color: '#e0e0e0' }} }} }}
                }}
            }});
        }}

        // Initialize Leaflet map
        if (placesData.attractions && placesData.attractions.length > 0) {{
            // Get first attraction's coordinates for initial center
            const firstAttraction = placesData.attractions[0];
            const centerLat = firstAttraction.coordinates.lat;
            const centerLon = firstAttraction.coordinates.lon;

            // Initialize map
            const map = L.map('map').setView([centerLat, centerLon], 13);

            // Add OpenStreetMap tiles (free, no API key needed)
            L.tileLayer('https://{{s}}.tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png', {{
                attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
                maxZoom: 19
            }}).addTo(map);

            // Add markers for each attraction
            const bounds = [];
            placesData.attractions.forEach((attraction, index) => {{
                const lat = attraction.coordinates.lat;
                const lon = attraction.coordinates.lon;

                // Create marker
                const marker = L.marker([lat, lon]).addTo(map);

                // Create popup content
                const popupContent = `
                    <div style="font-family: -apple-system, sans-serif;">
                        <strong style="font-size: 14px; color: #8b5cf6;">${{attraction.name}}</strong><br>
                        <span style="font-size: 12px; color: #a0a0b0;">${{attraction.type || 'Attraction'}}</span>
                    </div>
                `;
                marker.bindPopup(popupContent);

                // Add to bounds for auto-fit
                bounds.push([lat, lon]);
            }});

            // Fit map to show all markers
            if (bounds.length > 1) {{
                map.fitBounds(bounds, {{ padding: [50, 50] }});
            }}
        }}
    </script>
</body>
</html>'''

    return html_content


@app.list_tools()
async def list_tools() -> list[Tool]:
    """List available city intelligence tools"""
    return [
        Tool(
            name="plan_city_trip",
            description="Plan a multi-day trip to any city with weather forecast, attractions, and itinerary (calls APIs directly - no orchestration)",
            inputSchema={
                "type": "object",
                "properties": {
                    "city_name": {
                        "type": "string",
                        "description": "City name (e.g., 'Tokyo', 'Paris', 'Mumbai')"
                    },
                    "duration_days": {
                        "type": "integer",
                        "default": 2,
                        "description": "Trip duration in days (1-7)"
                    }
                },
                "required": ["city_name"]
            }
        )
    ]


@app.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    """Handle tool calls"""
    if name == "plan_city_trip":
        city_name = arguments.get("city_name", "")
        duration_days = arguments.get("duration_days", 2)

        if not city_name:
            return [TextContent(
                type="text",
                text="Error: city_name is required"
            )]

        # Call APIs directly (parallel execution)
        weather_task = get_weather_direct(city_name, duration_days + 1)
        places_task = get_attractions_direct(city_name, limit=10)

        weather, places = await asyncio.gather(weather_task, places_task, return_exceptions=True)

        # Create itinerary
        attractions = places.get("attractions", []) if places and isinstance(places, dict) else []
        itinerary = create_itinerary_direct(city_name, duration_days, attractions)

        # Generate HTML
        html_output = generate_html(city_name, duration_days, weather, places, itinerary)

        return [TextContent(type="text", text=html_output)]

    return [TextContent(type="text", text="Unknown tool")]


async def main():
    """Run the MCP server"""
    async with mcp.server.stdio.stdio_server() as (read_stream, write_stream):
        await app.run(
            read_stream,
            write_stream,
            app.create_initialization_options()
        )


if __name__ == "__main__":
    asyncio.run(main())
