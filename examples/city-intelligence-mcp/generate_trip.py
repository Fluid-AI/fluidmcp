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


def generate_html(city: str, days: int, weather_data, places_data, itinerary):
    """Generate the complete HTML page"""

    # Calculate summaries
    if weather_data and weather_data.get("forecast"):
        temps = [d["temp_high"] for d in weather_data["forecast"]]
        avg_temp = round(sum(temps) / len(temps), 1)
        conditions = list(set(d["conditions"] for d in weather_data["forecast"][:3]))
        weather_summary = ", ".join(conditions)
    else:
        avg_temp = "N/A"
        weather_summary = "Weather data unavailable"

    num_attractions = len(places_data.get("attractions", [])) if places_data else 0
    total_activities = sum(len(day["schedule"]) for day in itinerary)

    weather_json = json.dumps(weather_data or {"forecast": []})
    places_json = json.dumps(places_data or {"attractions": []})

    # Generate itinerary HTML
    itinerary_html = ""
    for day in itinerary:
        activities_html = ""
        for activity in day["schedule"]:
            emoji = "🍽️" if activity["type"] == "meal" else "📍"
            travel_str = f" • 🚗 {activity['travel_to_next_minutes']} min to next" if activity["travel_to_next_minutes"] > 0 else ""

            activities_html += f'''
            <div class="activity">
                <div class="time">{activity["time"]}</div>
                <div class="activity-details">
                    <div class="activity-name">{emoji} {activity["activity"]}</div>
                    <div class="duration">⏱️ {activity["duration_minutes"]} min{travel_str}</div>
                </div>
            </div>'''

        itinerary_html += f'''
        <div class="day">
            <div class="day-header">📅 Day {day["day"]} - {day["date"]}</div>
            {activities_html}
        </div>'''

    if not itinerary_html:
        itinerary_html = '<div style="text-align: center; padding: 40px; color: #a0a0b0;">No itinerary available</div>'

    itinerary_iframe = f'''<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
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
    {itinerary_html}
</body>
</html>'''

    # Escape for srcdoc
    import html
    itinerary_escaped = html.escape(itinerary_iframe)

    # Main HTML
    return f'''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{city} Trip Plan</title>
    <script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
    <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
    <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: #0f0f1e;
            color: #e0e0e0;
            padding: 20px;
            line-height: 1.6;
        }}
        .container {{
            max-width: 1400px;
            margin: 0 auto;
            background: #1a1a2e;
            border-radius: 12px;
            padding: 30px;
            border: 1px solid #2a2a3e;
            box-shadow: 0 10px 40px rgba(0,0,0,0.3);
        }}
        .header {{
            border-bottom: 2px solid #2a2a3e;
            padding-bottom: 20px;
            margin-bottom: 30px;
        }}
        h1 {{
            font-size: 32px;
            color: #e0e0e0;
            font-weight: 600;
        }}
        .city-name {{
            color: #8b5cf6;
            font-weight: bold;
        }}
        .subtitle {{
            color: #a0a0b0;
            font-size: 14px;
            margin-top: 8px;
        }}
        .city-cards {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
            gap: 20px;
            margin-bottom: 40px;
        }}
        .card {{
            background: #2a2a3e;
            border-radius: 12px;
            padding: 24px;
            border: 1px solid #3a3a4e;
            transition: all 0.3s ease;
        }}
        .card:hover {{
            transform: translateY(-5px);
            border-color: #8b5cf6;
            box-shadow: 0 8px 20px rgba(139,92,246,0.3);
        }}
        .card-title {{
            font-size: 12px;
            color: #a0a0b0;
            margin-bottom: 12px;
            text-transform: uppercase;
            letter-spacing: 1.5px;
            font-weight: 600;
        }}
        .card-value {{
            font-size: 36px;
            color: #8b5cf6;
            font-weight: bold;
            margin-bottom: 8px;
        }}
        .card-subtitle {{
            color: #a0a0b0;
            font-size: 14px;
        }}
        .chart-section {{
            margin: 40px 0;
        }}
        .chart-section h2 {{
            font-size: 24px;
            margin-bottom: 20px;
            color: #e0e0e0;
        }}
        .chart-container {{
            background: #16162a;
            border-radius: 12px;
            padding: 24px;
            margin-bottom: 20px;
            height: 320px;
            border: 1px solid #2a2a3e;
        }}
        .itinerary-section {{
            margin-top: 40px;
        }}
        .itinerary-section h2 {{
            font-size: 24px;
            margin-bottom: 20px;
            color: #e0e0e0;
        }}
        .itinerary-frame {{
            width: 100%;
            height: 600px;
            border: none;
            border-radius: 12px;
            background: #16162a;
            border: 1px solid #2a2a3e;
        }}
        .map-section {{
            margin: 40px 0;
        }}
        .map-section h2 {{
            font-size: 24px;
            margin-bottom: 20px;
            color: #e0e0e0;
        }}
        #map {{
            height: 500px;
            width: 100%;
            border-radius: 12px;
            border: 1px solid #2a2a3e;
        }}
        .leaflet-popup-content-wrapper {{
            background: #1a1a2e;
            color: #e0e0e0;
        }}
        .leaflet-popup-tip {{
            background: #1a1a2e;
        }}
        @media (max-width: 768px) {{
            .container {{ padding: 20px; }}
            h1 {{ font-size: 24px; }}
            .city-cards {{ grid-template-columns: 1fr; }}
            .chart-container {{ height: 250px; }}
            .itinerary-frame {{ height: 500px; }}
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🏙️ <span class="city-name">{city}</span> - {days}-Day Trip</h1>
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
                <div class="card-subtitle">Planned over {days} days</div>
            </div>
        </div>
        <div class="map-section">
            <h2>🗺️ Attractions Map</h2>
            <div id="map"></div>
        </div>
        <div class="chart-section">
            <h2>📊 Weather Forecast</h2>
            <div class="chart-container">
                <canvas id="tempChart"></canvas>
            </div>
            <div class="chart-container">
                <canvas id="precipChart"></canvas>
            </div>
        </div>
        <div class="itinerary-section">
            <h2>🗓️ Day-by-Day Itinerary</h2>
            <iframe class="itinerary-frame" srcdoc='{itinerary_escaped}'></iframe>
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
                    datasets: [
                        {{
                            label: 'High Temperature (°C)',
                            data: weatherData.forecast.map(d => d.temp_high),
                            borderColor: '#f59e0b',
                            backgroundColor: 'rgba(245,158,11,0.2)',
                            tension: 0.4,
                            fill: true
                        }},
                        {{
                            label: 'Low Temperature (°C)',
                            data: weatherData.forecast.map(d => d.temp_low),
                            borderColor: '#3b82f6',
                            backgroundColor: 'rgba(59,130,246,0.2)',
                            tension: 0.4,
                            fill: true
                        }}
                    ]
                }},
                options: {{
                    responsive: true,
                    maintainAspectRatio: false,
                    scales: {{
                        y: {{
                            ticks: {{ color: '#a0a0b0' }},
                            grid: {{ color: '#2a2a3e' }}
                        }},
                        x: {{
                            ticks: {{ color: '#a0a0b0' }},
                            grid: {{ color: '#2a2a3e' }}
                        }}
                    }},
                    plugins: {{
                        legend: {{
                            labels: {{ color: '#e0e0e0', font: {{ size: 12 }} }}
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
                        label: 'Precipitation Chance (%)',
                        data: weatherData.forecast.map(d => d.precipitation_chance),
                        backgroundColor: '#8b5cf6',
                        borderColor: '#7c3aed',
                        borderWidth: 1
                    }}]
                }},
                options: {{
                    responsive: true,
                    maintainAspectRatio: false,
                    scales: {{
                        y: {{
                            beginAtZero: true,
                            max: 100,
                            ticks: {{ color: '#a0a0b0' }},
                            grid: {{ color: '#2a2a3e' }}
                        }},
                        x: {{
                            ticks: {{ color: '#a0a0b0' }},
                            grid: {{ color: '#2a2a3e' }}
                        }}
                    }},
                    plugins: {{
                        legend: {{
                            labels: {{ color: '#e0e0e0', font: {{ size: 12 }} }}
                        }}
                    }}
                }}
            }});
        }} else {{
            document.getElementById('tempChart').parentElement.innerHTML =
                '<div style="color: #a0a0b0; text-align: center; padding: 40px;">Weather forecast data unavailable</div>';
            document.getElementById('precipChart').parentElement.innerHTML =
                '<div style="color: #a0a0b0; text-align: center; padding: 40px;">Precipitation data unavailable</div>';
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
        }} else {{
            // Show message if no attractions
            document.getElementById('map').innerHTML =
                '<div style="color: #a0a0b0; text-align: center; padding: 100px 20px; font-size: 16px;">No attractions data available</div>';
        }}
    </script>
</body>
</html>'''


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
