#!/usr/bin/env python3
"""
Standalone City Trip Planner
Generates interactive HTML with weather, attractions, and itinerary
No MCP orchestration - direct API calls for simplicity and speed
"""
import asyncio
import json
import os
import sys
import argparse
from datetime import datetime, timedelta
import httpx
import html as html_module

# Weather code mapping (WMO)
WEATHER_CODES = {
    0: "Clear sky", 1: "Mainly clear", 2: "Partly cloudy", 3: "Overcast",
    45: "Foggy", 61: "Light rain", 63: "Moderate rain", 65: "Heavy rain",
    80: "Light rain showers", 95: "Thunderstorm"
}


async def get_weather(city: str, days: int = 3):
    """Get weather forecast from Open-Meteo"""
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            # Geocode
            geo_resp = await client.get(
                "https://nominatim.openstreetmap.org/search",
                params={"q": city, "format": "json", "limit": 1},
                headers={"User-Agent": "CityTripPlanner/1.0"}
            )
            locations = geo_resp.json()
            if not locations:
                return None

            lat, lon = float(locations[0]["lat"]), float(locations[0]["lon"])

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
                    "temp_high": round(daily["temperature_2m_max"][i], 1),
                    "temp_low": round(daily["temperature_2m_min"][i], 1),
                    "precipitation_chance": int(daily["precipitation_probability_max"][i] or 0),
                    "conditions": WEATHER_CODES.get(int(daily["weathercode"][i]), "Unknown")
                })

            return {"city": city, "forecast": forecast}
    except Exception as e:
        print(f"⚠️  Weather API error: {e}", file=sys.stderr)
        return None


async def get_attractions(city: str, limit: int = 10):
    """Get attractions using OpenTripMap API (FREE 5,000 requests/day!)"""
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            # Geocode city
            geo_resp = await client.get(
                "https://nominatim.openstreetmap.org/search",
                params={"q": city, "format": "json", "limit": 1},
                headers={"User-Agent": "CityTripPlanner/1.0"}
            )
            locations = geo_resp.json()
            if not locations:
                return None

            lat, lon = float(locations[0]["lat"]), float(locations[0]["lon"])

            await asyncio.sleep(1.1)

            # Geoapify API key (from user)
            geoapify_key = os.environ.get("GEOAPIFY_API_KEY", "f628c3a56d724117b4028da5cd72adb7")

            # Query Geoapify Places API (FREE 3,000 requests/day!)
            geo_url = "https://api.geoapify.com/v2/places"
            params = {
                "categories": "tourism.sights,tourism.attraction,heritage,entertainment.museum",
                "filter": f"circle:{lon},{lat},5000",
                "limit": limit,
                "apiKey": geoapify_key
            }

            geo_resp = await client.get(geo_url, params=params)
            if geo_resp.status_code == 200:
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

                    place_lon, place_lat = coords[0], coords[1]

                    # Get category
                    categories = props.get("categories", [])
                    attraction_type = categories[0].split(".")[-1].replace("_", " ").title() if categories else "Attraction"

                    attractions.append({
                        "name": name,
                        "type": attraction_type,
                        "coordinates": {"lat": float(place_lat), "lon": float(place_lon)}
                    })

                if attractions:
                    return {"city": city, "attractions": attractions}

            # Fallback: Try to load from fallback_attractions.json
            print(f"⚠️  Geoapify API unavailable ({geo_resp.status_code if 'geo_resp' in locals() else 'error'}). Using fallback attractions.", file=sys.stderr)
            fallback_file = os.path.join(os.path.dirname(__file__), "fallback_attractions.json")
            if os.path.exists(fallback_file):
                with open(fallback_file) as f:
                    fallback_data = json.load(f)
                    if city in fallback_data:
                        return {"city": city, "attractions": fallback_data[city][:limit]}

            return None

    except Exception as e:
        print(f"⚠️  Places API error: {e}", file=sys.stderr)
        return None


def create_itinerary(city: str, days: int, attractions: list):
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

        day_date = (datetime.now() + timedelta(days=day_num)).strftime("%Y-%m-%d")
        schedule = []
        current_time = datetime.strptime("09:00", "%H:%M")

        for i, attr in enumerate(day_attractions):
            duration = 90  # Default visit duration
            travel = 20 if i < len(day_attractions) - 1 else 0

            schedule.append({
                "time": current_time.strftime("%H:%M"),
                "activity": attr["name"],
                "type": attr["type"],
                "duration_minutes": duration,
                "travel_to_next_minutes": travel
            })

            current_time += timedelta(minutes=duration + travel)

            # Add lunch after 2 activities
            if i == 1 and len(day_attractions) > 3:
                schedule.append({
                    "time": current_time.strftime("%H:%M"),
                    "activity": "🍽️ Lunch break",
                    "type": "meal",
                    "duration_minutes": 60,
                    "travel_to_next_minutes": 0
                })
                current_time += timedelta(minutes=60)

        itinerary.append({
            "day": day_num + 1,
            "date": day_date,
            "schedule": schedule
        })

    return itinerary


def generate_html(city: str, days: int, weather: dict, places: dict, itinerary: list):
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
            <div class="flex items-center gap-2 border-b pb-4 mb-4">
                <span class="text-2xl">📅</span>
                <h3 class="text-xl font-semibold text-primary">Day {day["day"]}</h3>
                <span class="text-muted-foreground">· {day["date"]}</span>
            </div>
            <div class="space-y-3">'''

        for activity in day["schedule"]:
            travel_text = f' <span class="text-muted-foreground">• 🚗 {activity["travel_to_next_minutes"]} min to next</span>' if activity["travel_to_next_minutes"] > 0 else ''
            itinerary_content += f'''
                <div class="group flex gap-4 p-4 rounded-lg border bg-muted/30 hover:bg-muted/50 hover:border-primary/50 transition-all">
                    <div class="flex-shrink-0">
                        <span class="inline-flex items-center justify-center w-16 h-16 rounded-lg bg-primary/10 text-primary font-semibold text-sm">
                            {activity["time"]}
                        </span>
                    </div>
                    <div class="flex-1 min-w-0">
                        <h4 class="font-medium text-foreground mb-1">{activity["activity"]}</h4>
                        <p class="text-sm text-muted-foreground">
                            <span class="inline-flex items-center gap-1">
                                ⏱️ {activity["duration_minutes"]} min{travel_text}
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
                        border: "hsl(240 3.7% 15.9%)",
                        background: "hsl(240 10% 3.9%)",
                        foreground: "hsl(0 0% 98%)",
                        primary: {{
                            DEFAULT: "hsl(263 70% 50.4%)",
                            foreground: "hsl(0 0% 98%)"
                        }},
                        muted: {{
                            DEFAULT: "hsl(240 3.7% 15.9%)",
                            foreground: "hsl(240 5% 64.9%)"
                        }},
                        card: {{
                            DEFAULT: "hsl(240 10% 3.9%)",
                            foreground: "hsl(0 0% 98%)"
                        }}
                    }}
                }}
            }}
        }}
    </script>
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
        body {{ font-family: 'Inter', sans-serif; }}
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
    <title>{city} Trip Plan</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
    <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
    <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
    <script>
        tailwind.config = {{
            theme: {{
                extend: {{
                    colors: {{
                        border: "hsl(240 3.7% 15.9%)",
                        input: "hsl(240 3.7% 15.9%)",
                        ring: "hsl(263 70% 50.4%)",
                        background: "hsl(240 10% 3.9%)",
                        foreground: "hsl(0 0% 98%)",
                        primary: {{
                            DEFAULT: "hsl(263 70% 50.4%)",
                            foreground: "hsl(0 0% 98%)"
                        }},
                        secondary: {{
                            DEFAULT: "hsl(240 3.7% 15.9%)",
                            foreground: "hsl(0 0% 98%)"
                        }},
                        muted: {{
                            DEFAULT: "hsl(240 3.7% 15.9%)",
                            foreground: "hsl(240 5% 64.9%)"
                        }},
                        accent: {{
                            DEFAULT: "hsl(240 3.7% 15.9%)",
                            foreground: "hsl(0 0% 98%)"
                        }},
                        card: {{
                            DEFAULT: "hsl(240 10% 3.9%)",
                            foreground: "hsl(0 0% 98%)"
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
        .chart-canvas {{ height: 300px !important; }}
        #map {{ height: 500px; width: 100%; border-radius: 0.75rem; }}
        .leaflet-popup-content-wrapper {{ background: hsl(240 10% 3.9%); color: hsl(0 0% 98%); border: 1px solid hsl(240 3.7% 15.9%); }}
        .leaflet-popup-tip {{ background: hsl(240 10% 3.9%); }}
        .leaflet-container {{ border-radius: 0.75rem; }}
    </style>
</head>
<body class="bg-background text-foreground antialiased">
    <!-- Gradient Background -->
    <div class="fixed inset-0 -z-10 bg-gradient-to-br from-background via-background to-purple-950/20"></div>

    <div class="container mx-auto max-w-7xl p-4 md:p-8">
        <!-- Header Section -->
        <div class="mb-8 space-y-2">
            <div class="flex items-center gap-3">
                <div class="rounded-lg bg-primary/10 p-3">
                    <span class="text-3xl">🏙️</span>
                </div>
                <div>
                    <h1 class="text-4xl font-bold tracking-tight">
                        <span class="text-primary">{city}</span>
                        <span class="text-muted-foreground"> · {days}-Day Trip</span>
                    </h1>
                    <p class="text-muted-foreground mt-1">Your personalized itinerary with live weather and local attractions</p>
                </div>
            </div>
        </div>

        <!-- Stats Cards -->
        <div class="grid gap-4 md:grid-cols-3 mb-8">
            <div class="group relative overflow-hidden rounded-lg border bg-card p-6 shadow-sm transition-all hover:shadow-md hover:border-primary/50">
                <div class="flex items-center justify-between">
                    <div class="space-y-1">
                        <p class="text-sm font-medium text-muted-foreground uppercase tracking-wider">Weather</p>
                        <p class="text-3xl font-bold text-primary">{avg_temp}°C</p>
                        <p class="text-sm text-muted-foreground">{weather_summary}</p>
                    </div>
                    <div class="text-5xl opacity-20 group-hover:opacity-30 transition-opacity">☀️</div>
                </div>
            </div>

            <div class="group relative overflow-hidden rounded-lg border bg-card p-6 shadow-sm transition-all hover:shadow-md hover:border-primary/50">
                <div class="flex items-center justify-between">
                    <div class="space-y-1">
                        <p class="text-sm font-medium text-muted-foreground uppercase tracking-wider">Attractions</p>
                        <p class="text-3xl font-bold text-primary">{num_attractions}</p>
                        <p class="text-sm text-muted-foreground">Places to visit</p>
                    </div>
                    <div class="text-5xl opacity-20 group-hover:opacity-30 transition-opacity">🎯</div>
                </div>
            </div>

            <div class="group relative overflow-hidden rounded-lg border bg-card p-6 shadow-sm transition-all hover:shadow-md hover:border-primary/50">
                <div class="flex items-center justify-between">
                    <div class="space-y-1">
                        <p class="text-sm font-medium text-muted-foreground uppercase tracking-wider">Activities</p>
                        <p class="text-3xl font-bold text-primary">{total_activities}</p>
                        <p class="text-sm text-muted-foreground">Over {days} days</p>
                    </div>
                    <div class="text-5xl opacity-20 group-hover:opacity-30 transition-opacity">📅</div>
                </div>
            </div>
        </div>

        <!-- Map Section -->
        <div class="mb-8 rounded-lg border bg-card p-6 shadow-sm">
            <div class="flex items-center gap-2 mb-4">
                <span class="text-2xl">🗺️</span>
                <h2 class="text-2xl font-semibold">Attractions Map</h2>
            </div>
            <div id="map" class="rounded-lg border overflow-hidden"></div>
        </div>

        <!-- Weather Charts -->
        <div class="mb-8 space-y-4">
            <div class="flex items-center gap-2 mb-4">
                <span class="text-2xl">📊</span>
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
            <div class="flex items-center gap-2 mb-4">
                <span class="text-2xl">🗓️</span>
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
                        borderColor: 'hsl(263, 70%, 50.4%)',
                        backgroundColor: 'hsla(263, 70%, 50.4%, 0.1)',
                        borderWidth: 3,
                        tension: 0.4,
                        fill: true,
                        pointRadius: 5,
                        pointHoverRadius: 7,
                        pointBackgroundColor: 'hsl(263, 70%, 50.4%)',
                        pointBorderColor: 'hsl(240, 10%, 3.9%)',
                        pointBorderWidth: 2
                    }}, {{
                        label: 'Low',
                        data: weatherData.forecast.map(d => d.temp_low),
                        borderColor: 'hsl(217, 91%, 60%)',
                        backgroundColor: 'hsla(217, 91%, 60%, 0.1)',
                        borderWidth: 3,
                        tension: 0.4,
                        fill: true,
                        pointRadius: 5,
                        pointHoverRadius: 7,
                        pointBackgroundColor: 'hsl(217, 91%, 60%)',
                        pointBorderColor: 'hsl(240, 10%, 3.9%)',
                        pointBorderWidth: 2
                    }}]
                }},
                options: {{
                    responsive: true,
                    maintainAspectRatio: false,
                    interaction: {{ mode: 'index', intersect: false }},
                    scales: {{
                        y: {{
                            ticks: {{ color: 'hsl(240, 5%, 64.9%)', font: {{ size: 12 }} }},
                            grid: {{ color: 'hsl(240, 3.7%, 15.9%)', drawBorder: false }},
                            border: {{ display: false }}
                        }},
                        x: {{
                            ticks: {{ color: 'hsl(240, 5%, 64.9%)', font: {{ size: 12 }} }},
                            grid: {{ display: false }},
                            border: {{ display: false }}
                        }}
                    }},
                    plugins: {{
                        legend: {{
                            labels: {{ color: 'hsl(0, 0%, 98%)', font: {{ size: 13, weight: '500' }}, padding: 15 }},
                            position: 'top',
                            align: 'end'
                        }},
                        tooltip: {{
                            backgroundColor: 'hsl(240, 10%, 3.9%)',
                            titleColor: 'hsl(0, 0%, 98%)',
                            bodyColor: 'hsl(240, 5%, 64.9%)',
                            borderColor: 'hsl(240, 3.7%, 15.9%)',
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
                        backgroundColor: 'hsl(263, 70%, 50.4%)',
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
                            ticks: {{ color: 'hsl(240, 5%, 64.9%)', font: {{ size: 12 }}, callback: function(value) {{ return value + '%'; }} }},
                            grid: {{ color: 'hsl(240, 3.7%, 15.9%)', drawBorder: false }},
                            border: {{ display: false }}
                        }},
                        x: {{
                            ticks: {{ color: 'hsl(240, 5%, 64.9%)', font: {{ size: 12 }} }},
                            grid: {{ display: false }},
                            border: {{ display: false }}
                        }}
                    }},
                    plugins: {{
                        legend: {{
                            labels: {{ color: 'hsl(0, 0%, 98%)', font: {{ size: 13, weight: '500' }}, padding: 15 }},
                            position: 'top',
                            align: 'end'
                        }},
                        tooltip: {{
                            backgroundColor: 'hsl(240, 10%, 3.9%)',
                            titleColor: 'hsl(0, 0%, 98%)',
                            bodyColor: 'hsl(240, 5%, 64.9%)',
                            borderColor: 'hsl(240, 3.7%, 15.9%)',
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

async def main():
    parser = argparse.ArgumentParser(description="Generate city trip plan with weather and attractions")
    parser.add_argument("--city", required=True, help="City name (e.g., 'Tokyo', 'Paris', 'London')")
    parser.add_argument("--days", type=int, default=2, help="Number of days (1-7)")
    parser.add_argument("--output", "-o", help="Output HTML file (default: stdout)")

    args = parser.parse_args()

    if args.days < 1 or args.days > 7:
        print("Error: Days must be between 1 and 7", file=sys.stderr)
        sys.exit(1)

    print(f"🌍 Planning {args.days}-day trip to {args.city}...", file=sys.stderr)

    # Fetch data in parallel
    print("📡 Fetching weather and attractions...", file=sys.stderr)
    weather_task = get_weather(args.city, args.days + 1)
    places_task = get_attractions(args.city, args.days * 4)

    weather_data, places_data = await asyncio.gather(weather_task, places_task)

    # Create itinerary
    attractions = places_data.get("attractions", []) if places_data else []
    print(f"✅ Found {len(attractions)} attractions", file=sys.stderr)

    itinerary = create_itinerary(args.city, args.days, attractions)

    # Generate HTML
    html = generate_html(args.city, args.days, weather_data, places_data, itinerary)

    # Output
    if args.output:
        with open(args.output, 'w') as f:
            f.write(html)
        print(f"✅ Saved to {args.output}", file=sys.stderr)
    else:
        print(html)


if __name__ == "__main__":
    asyncio.run(main())
