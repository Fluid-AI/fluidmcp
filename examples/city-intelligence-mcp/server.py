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
        async with httpx.AsyncClient(timeout=30.0) as client:
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
        import traceback
        print(f"Weather error: {e}")
        traceback.print_exc()
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

    # Generate itinerary HTML with Tailwind classes
    itinerary_content = ""
    for day in itinerary:
        itinerary_content += f'''<div class="rounded-lg border bg-card p-6 shadow-sm">
            <div class="flex items-center gap-3 border-b pb-4 mb-4">
                <div class="w-1 h-6 bg-primary rounded-full"></div>
                <h3 class="text-xl font-semibold text-foreground">Day {day["day"]}</h3>
                <span class="text-muted-foreground">· {day["date"]}</span>
            </div>
            <div class="space-y-3">'''

        for activity in day["schedule"]:
            travel_text = f' <span class="text-muted-foreground">• {activity["travel_to_next_minutes"]} min travel</span>' if activity["travel_to_next_minutes"] > 0 else ''
            itinerary_content += f'''
                <div class="group flex gap-4 p-4 rounded-lg border bg-muted/30 hover:bg-muted/50 hover:border-primary/50 transition-all">
                    <div class="flex-shrink-0">
                        <span class="inline-flex items-center justify-center w-20 h-12 rounded-lg bg-primary/20 text-primary font-semibold text-sm">
                            {activity["time"]}
                        </span>
                    </div>
                    <div class="flex-1 min-w-0">
                        <h4 class="font-medium text-foreground mb-1">{activity["activity"]}</h4>
                        <p class="text-sm text-muted-foreground">
                            <span class="inline-flex items-center gap-1">
                                {activity["duration_minutes"]} min{travel_text}
                            </span>
                        </p>
                    </div>
                </div>'''

        itinerary_content += '</div></div>'

    # Wrap itinerary with complete HTML including modern Tailwind styles for iframe
    itinerary_html = f'''<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <script src="https://cdn.tailwindcss.com"></script>
    <script>
        tailwind.config = {{
            theme: {{
                extend: {{
                    colors: {{
                        border: "hsl(220 13% 18%)",
                        background: "hsl(222 47% 11%)",
                        foreground: "hsl(210 40% 98%)",
                        primary: {{
                            DEFAULT: "hsl(210 100% 60%)",
                            foreground: "hsl(222 47% 11%)"
                        }},
                        muted: {{
                            DEFAULT: "hsl(217 33% 17%)",
                            foreground: "hsl(215 20% 65%)"
                        }},
                        card: {{
                            DEFAULT: "hsl(217 33% 17%)",
                            foreground: "hsl(210 40% 98%)"
                        }}
                    }}
                }}
            }}
        }}
    </script>
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
        body {{ font-family: 'Inter', sans-serif; }}

        /* Custom Scrollbar */
        ::-webkit-scrollbar {{
            width: 10px;
        }}
        ::-webkit-scrollbar-track {{
            background: hsl(222 47% 11%);
            border-radius: 5px;
        }}
        ::-webkit-scrollbar-thumb {{
            background: hsl(217 33% 17%);
            border-radius: 5px;
            border: 2px solid hsl(222 47% 11%);
        }}
        ::-webkit-scrollbar-thumb:hover {{
            background: hsl(210 100% 60%);
        }}
        * {{
            scrollbar-width: thin;
            scrollbar-color: hsl(217 33% 17%) hsl(222 47% 11%);
        }}
    </style>
</head>
<body class="bg-background text-foreground antialiased p-4">
    <div class="space-y-6">
        {itinerary_content}
    </div>
</body>
</html>'''

    itinerary_html_escaped = html_module.escape(itinerary_html).replace('"', '&quot;')

    # Generate full HTML with Tailwind CSS (shadcn-inspired design)
    html_content = f'''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{city_name} Trip Plan</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
    <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
    <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
    <script>
        tailwind.config = {{
            theme: {{
                extend: {{
                    colors: {{
                        border: "hsl(220 13% 18%)",
                        input: "hsl(220 13% 18%)",
                        ring: "hsl(210 100% 60%)",
                        background: "hsl(222 47% 11%)",
                        foreground: "hsl(210 40% 98%)",
                        primary: {{
                            DEFAULT: "hsl(210 100% 60%)",
                            foreground: "hsl(222 47% 11%)"
                        }},
                        secondary: {{
                            DEFAULT: "hsl(217 33% 17%)",
                            foreground: "hsl(210 40% 98%)"
                        }},
                        muted: {{
                            DEFAULT: "hsl(217 33% 17%)",
                            foreground: "hsl(215 20% 65%)"
                        }},
                        accent: {{
                            DEFAULT: "hsl(210 100% 60%)",
                            foreground: "hsl(222 47% 11%)"
                        }},
                        card: {{
                            DEFAULT: "hsl(217 33% 17%)",
                            foreground: "hsl(210 40% 98%)"
                        }}
                    }},
                    borderRadius: {{
                        lg: "0.5rem",
                        md: "0.375rem",
                        sm: "0.25rem"
                    }}
                }}
            }}
        }}
    </script>
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');

        /* Custom Scrollbar */
        ::-webkit-scrollbar {{
            width: 12px;
            height: 12px;
        }}
        ::-webkit-scrollbar-track {{
            background: hsl(222 47% 11%);
            border-radius: 6px;
        }}
        ::-webkit-scrollbar-thumb {{
            background: hsl(217 33% 17%);
            border-radius: 6px;
            border: 2px solid hsl(222 47% 11%);
        }}
        ::-webkit-scrollbar-thumb:hover {{
            background: hsl(210 100% 60%);
        }}

        /* Firefox Scrollbar */
        * {{
            scrollbar-width: thin;
            scrollbar-color: hsl(217 33% 17%) hsl(222 47% 11%);
        }}

        .chart-canvas {{ height: 300px !important; }}
        #map {{ height: 500px; width: 100%; border-radius: 0.75rem; }}
        .leaflet-popup-content-wrapper {{ background: hsl(217 33% 17%); color: hsl(210 40% 98%); border: 1px solid hsl(220 13% 18%); }}
        .leaflet-popup-tip {{ background: hsl(217 33% 17%); }}
        .leaflet-container {{ border-radius: 0.75rem; }}
    </style>
</head>
<body class="bg-background text-foreground antialiased">
    <!-- Gradient Background -->
    <div class="fixed inset-0 -z-10 bg-gradient-to-br from-background via-background to-blue-950/30"></div>

    <div class="container mx-auto max-w-7xl p-4 md:p-8">
        <!-- Header Section -->
        <div class="mb-8 border-b border-border pb-6">
            <h1 class="text-4xl font-bold tracking-tight mb-2">
                <span class="text-primary">{city_name}</span>
                <span class="text-muted-foreground"> · {duration_days}-Day Trip</span>
            </h1>
            <p class="text-muted-foreground">Your personalized itinerary with live weather and local attractions</p>
        </div>

        <!-- Stats Cards -->
        <div class="grid gap-4 md:grid-cols-3 mb-8">
            <div class="group relative overflow-hidden rounded-lg border bg-card p-6 shadow-sm transition-all hover:shadow-md hover:border-primary/50">
                <div class="flex items-start justify-between">
                    <div class="space-y-2 flex-1">
                        <div class="flex items-center gap-2">
                            <div class="w-2 h-2 rounded-full bg-amber-400"></div>
                            <p class="text-xs font-semibold text-muted-foreground uppercase tracking-wider">Weather</p>
                        </div>
                        <p class="text-4xl font-bold text-foreground">{avg_temp}°C</p>
                        <p class="text-sm text-muted-foreground">{weather_summary}</p>
                    </div>
                </div>
            </div>

            <div class="group relative overflow-hidden rounded-lg border bg-card p-6 shadow-sm transition-all hover:shadow-md hover:border-primary/50">
                <div class="flex items-start justify-between">
                    <div class="space-y-2 flex-1">
                        <div class="flex items-center gap-2">
                            <div class="w-2 h-2 rounded-full bg-emerald-400"></div>
                            <p class="text-xs font-semibold text-muted-foreground uppercase tracking-wider">Attractions</p>
                        </div>
                        <p class="text-4xl font-bold text-foreground">{num_attractions}</p>
                        <p class="text-sm text-muted-foreground">Places to visit</p>
                    </div>
                </div>
            </div>

            <div class="group relative overflow-hidden rounded-lg border bg-card p-6 shadow-sm transition-all hover:shadow-md hover:border-primary/50">
                <div class="flex items-start justify-between">
                    <div class="space-y-2 flex-1">
                        <div class="flex items-center gap-2">
                            <div class="w-2 h-2 rounded-full bg-primary"></div>
                            <p class="text-xs font-semibold text-muted-foreground uppercase tracking-wider">Activities</p>
                        </div>
                        <p class="text-4xl font-bold text-foreground">{total_activities}</p>
                        <p class="text-sm text-muted-foreground">Over {duration_days} days</p>
                    </div>
                </div>
            </div>
        </div>

        <!-- Map Section -->
        <div class="mb-8 rounded-lg border bg-card p-6 shadow-sm">
            <div class="flex items-center gap-3 mb-6">
                <div class="w-1 h-6 bg-primary rounded-full"></div>
                <h2 class="text-2xl font-semibold">Attractions Map</h2>
            </div>
            <div id="map" class="rounded-lg border overflow-hidden"></div>
        </div>

        <!-- Weather Charts -->
        <div class="mb-8 space-y-4">
            <div class="flex items-center gap-3 mb-6">
                <div class="w-1 h-6 bg-primary rounded-full"></div>
                <h2 class="text-2xl font-semibold">Weather Forecast</h2>
            </div>
            <div class="grid gap-4 md:grid-cols-2">
                <div class="rounded-lg border bg-card p-6 shadow-sm">
                    <h3 class="text-sm font-medium text-muted-foreground mb-4 uppercase tracking-wider">Temperature</h3>
                    <div class="chart-canvas">
                        <canvas id="tempChart"></canvas>
                    </div>
                </div>
                <div class="rounded-lg border bg-card p-6 shadow-sm">
                    <h3 class="text-sm font-medium text-muted-foreground mb-4 uppercase tracking-wider">Precipitation</h3>
                    <div class="chart-canvas">
                        <canvas id="precipChart"></canvas>
                    </div>
                </div>
            </div>
        </div>

        <!-- Itinerary Section -->
        <div class="rounded-lg border bg-card p-6 shadow-sm">
            <div class="flex items-center gap-3 mb-6">
                <div class="w-1 h-6 bg-primary rounded-full"></div>
                <h2 class="text-2xl font-semibold">Day-by-Day Itinerary</h2>
            </div>
            <iframe class="w-full h-[600px] rounded-lg border-0 bg-background" srcdoc='{itinerary_html_escaped}'></iframe>
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
                        label: 'High',
                        data: weatherData.forecast.map(d => d.temp_high),
                        borderColor: 'hsl(210, 100%, 60%)',
                        backgroundColor: 'hsla(210, 100%, 60%, 0.1)',
                        borderWidth: 3,
                        tension: 0.4,
                        fill: true,
                        pointRadius: 5,
                        pointHoverRadius: 7,
                        pointBackgroundColor: 'hsl(210, 100%, 60%)',
                        pointBorderColor: 'hsl(222, 47%, 11%)',
                        pointBorderWidth: 2
                    }}, {{
                        label: 'Low',
                        data: weatherData.forecast.map(d => d.temp_low),
                        borderColor: 'hsl(190, 85%, 55%)',
                        backgroundColor: 'hsla(190, 85%, 55%, 0.1)',
                        borderWidth: 3,
                        tension: 0.4,
                        fill: true,
                        pointRadius: 5,
                        pointHoverRadius: 7,
                        pointBackgroundColor: 'hsl(190, 85%, 55%)',
                        pointBorderColor: 'hsl(222, 47%, 11%)',
                        pointBorderWidth: 2
                    }}]
                }},
                options: {{
                    responsive: true,
                    maintainAspectRatio: false,
                    interaction: {{ mode: 'index', intersect: false }},
                    scales: {{
                        y: {{
                            ticks: {{ color: 'hsl(215, 20%, 65%)', font: {{ size: 12 }} }},
                            grid: {{ color: 'hsl(220, 13%, 18%)', drawBorder: false }},
                            border: {{ display: false }}
                        }},
                        x: {{
                            ticks: {{ color: 'hsl(215, 20%, 65%)', font: {{ size: 12 }} }},
                            grid: {{ display: false }},
                            border: {{ display: false }}
                        }}
                    }},
                    plugins: {{
                        legend: {{
                            labels: {{ color: 'hsl(210, 40%, 98%)', font: {{ size: 13, weight: '500' }}, padding: 15 }},
                            position: 'top',
                            align: 'end'
                        }},
                        tooltip: {{
                            backgroundColor: 'hsl(217, 33%, 17%)',
                            titleColor: 'hsl(210, 40%, 98%)',
                            bodyColor: 'hsl(215, 20%, 65%)',
                            borderColor: 'hsl(220, 13%, 18%)',
                            borderWidth: 1,
                            padding: 12,
                            displayColors: true
                        }}
                    }}
                }}
            }});
            const precipCtx = document.getElementById('precipChart').getContext('2d');
            new Chart(precipCtx, {{
                type: 'bar',
                data: {{
                    labels: weatherData.forecast.map(d => d.date),
                    datasets: [{{
                        label: 'Precipitation Chance',
                        data: weatherData.forecast.map(d => d.precipitation_chance),
                        backgroundColor: 'hsl(210, 100%, 60%)',
                        borderRadius: 6,
                        borderSkipped: false
                    }}]
                }},
                options: {{
                    responsive: true,
                    maintainAspectRatio: false,
                    scales: {{
                        y: {{
                            beginAtZero: true,
                            max: 100,
                            ticks: {{ color: 'hsl(215, 20%, 65%)', font: {{ size: 12 }}, callback: function(value) {{ return value + '%'; }} }},
                            grid: {{ color: 'hsl(220, 13%, 18%)', drawBorder: false }},
                            border: {{ display: false }}
                        }},
                        x: {{
                            ticks: {{ color: 'hsl(215, 20%, 65%)', font: {{ size: 12 }} }},
                            grid: {{ display: false }},
                            border: {{ display: false }}
                        }}
                    }},
                    plugins: {{
                        legend: {{
                            labels: {{ color: 'hsl(210, 40%, 98%)', font: {{ size: 13, weight: '500' }}, padding: 15 }},
                            position: 'top',
                            align: 'end'
                        }},
                        tooltip: {{
                            backgroundColor: 'hsl(217, 33%, 17%)',
                            titleColor: 'hsl(210, 40%, 98%)',
                            bodyColor: 'hsl(215, 20%, 65%)',
                            borderColor: 'hsl(220, 13%, 18%)',
                            borderWidth: 1,
                            padding: 12,
                            callbacks: {{
                                label: function(context) {{
                                    return context.dataset.label + ': ' + context.parsed.y + '%';
                                }}
                            }}
                        }}
                    }}
                }}
            }});
        }} else {{
            // Display message when weather data is unavailable
            const tempCanvas = document.getElementById('tempChart');
            const precipCanvas = document.getElementById('precipChart');

            if (tempCanvas) {{
                const parent = tempCanvas.parentElement;
                parent.innerHTML = '<div class="flex items-center justify-center h-full text-muted-foreground"><p>Weather data unavailable</p></div>';
            }}

            if (precipCanvas) {{
                const parent = precipCanvas.parentElement;
                parent.innerHTML = '<div class="flex items-center justify-center h-full text-muted-foreground"><p>Weather data unavailable</p></div>';
            }}
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

        # Handle exceptions from gather
        if isinstance(weather, Exception):
            print(f"Weather API exception: {weather}")
            weather = None
        if isinstance(places, Exception):
            print(f"Places API exception: {places}")
            places = None

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
