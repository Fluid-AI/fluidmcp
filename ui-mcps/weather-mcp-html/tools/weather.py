"""
Weather data fetching and mock data.
This module provides weather information for cities using mock data initially.
Future: Integrate with real weather APIs (OpenWeatherMap, WeatherAPI, etc.)
"""

from typing import Dict, Any, List
from datetime import datetime, timedelta
import random

# Mock weather database for multiple cities
MOCK_WEATHER_DATA = {
    "Bangalore": {
        "temperature": 29,
        "condition": "Sunny",
        "humidity": 65,
        "wind_speed": 12,
        "description": "Clear sky with bright sunshine",
        "icon": "sunny"
    },
    "Mumbai": {
        "temperature": 32,
        "condition": "Cloudy",
        "humidity": 78,
        "wind_speed": 15,
        "description": "Partly cloudy with humid conditions",
        "icon": "cloudy"
    },
    "Delhi": {
        "temperature": 35,
        "condition": "Sunny",
        "humidity": 45,
        "wind_speed": 8,
        "description": "Hot and sunny weather",
        "icon": "sunny"
    },
    "Chennai": {
        "temperature": 31,
        "condition": "Rainy",
        "humidity": 85,
        "wind_speed": 20,
        "description": "Monsoon showers expected",
        "icon": "rainy"
    },
    "Kolkata": {
        "temperature": 33,
        "condition": "Stormy",
        "humidity": 82,
        "wind_speed": 25,
        "description": "Thunderstorms with heavy rain",
        "icon": "stormy"
    },
    "Pune": {
        "temperature": 28,
        "condition": "Cloudy",
        "humidity": 70,
        "wind_speed": 10,
        "description": "Overcast with cool breeze",
        "icon": "cloudy"
    },
    "Hyderabad": {
        "temperature": 30,
        "condition": "Sunny",
        "humidity": 60,
        "wind_speed": 14,
        "description": "Pleasant sunny day",
        "icon": "sunny"
    },
    "Ahmedabad": {
        "temperature": 36,
        "condition": "Sunny",
        "humidity": 40,
        "wind_speed": 12,
        "description": "Very hot and dry",
        "icon": "sunny"
    },
    "Jaipur": {
        "temperature": 34,
        "condition": "Clear",
        "humidity": 35,
        "wind_speed": 9,
        "description": "Clear evening skies",
        "icon": "clear"
    },
    "Lucknow": {
        "temperature": 32,
        "condition": "Cloudy",
        "humidity": 68,
        "wind_speed": 11,
        "description": "Mild weather with clouds",
        "icon": "cloudy"
    },
    "Surat": {
        "temperature": 33,
        "condition": "Sunny",
        "humidity": 72,
        "wind_speed": 13,
        "description": "Warm and humid coastal weather",
        "icon": "sunny"
    },
    "Kanpur": {
        "temperature": 31,
        "condition": "Cloudy",
        "humidity": 65,
        "wind_speed": 10,
        "description": "Moderate weather with scattered clouds",
        "icon": "cloudy"
    },
    "Nagpur": {
        "temperature": 34,
        "condition": "Sunny",
        "humidity": 55,
        "wind_speed": 8,
        "description": "Hot and dry central plains weather",
        "icon": "sunny"
    },
    "Indore": {
        "temperature": 30,
        "condition": "Rainy",
        "humidity": 75,
        "wind_speed": 18,
        "description": "Light showers with cool breeze",
        "icon": "rainy"
    },
    "Kochi": {
        "temperature": 28,
        "condition": "Rainy",
        "humidity": 88,
        "wind_speed": 22,
        "description": "Tropical monsoon weather",
        "icon": "rainy"
    }
}

def celsius_to_fahrenheit(celsius: float) -> float:
    """Convert Celsius to Fahrenheit."""
    return (celsius * 9/5) + 32

def get_current_weather(city: str, units: str = "metric") -> Dict[str, Any]:
    """
    Get current weather data for a city (mock data initially).

    Args:
        city: City name (e.g., "Bangalore", "Mumbai", "Delhi")
        units: Temperature units - "metric" (Celsius) or "imperial" (Fahrenheit)

    Returns:
        dict with weather data including city, temperature, condition, etc.
    """
    # Normalize city name (capitalize first letter)
    city_key = city.strip().title()

    # Get mock data or return default for unknown cities
    if city_key in MOCK_WEATHER_DATA:
        data = MOCK_WEATHER_DATA[city_key].copy()
    else:
        # Default data for unknown cities
        data = {
            "temperature": 25,
            "condition": "Clear",
            "humidity": 60,
            "wind_speed": 10,
            "description": f"Weather data for {city}",
            "icon": "sunny"
        }

    # Convert temperature if imperial units requested
    temperature = data["temperature"]
    if units == "imperial":
        temperature = celsius_to_fahrenheit(temperature)

    return {
        "city": city_key,
        "temperature": round(temperature, 1),
        "condition": data["condition"],
        "humidity": data["humidity"],
        "wind_speed": data["wind_speed"],
        "description": data["description"],
        "timestamp": datetime.now().isoformat(),
        "units": units
    }

def get_forecast_data(city: str, days: int = 5, units: str = "metric") -> List[Dict[str, Any]]:
    """
    Get weather forecast data for multiple days (mock data).

    Args:
        city: City name
        days: Number of forecast days (1-10)
        units: Temperature units

    Returns:
        list of forecast entries with date, temperature, condition, etc.
    """
    # Get base weather for the city
    current = get_current_weather(city, units)
    base_temp = current["temperature"]

    forecast = []
    conditions = ["Sunny", "Cloudy", "Rainy", "Clear"]

    for i in range(min(days, 10)):  # Cap at 10 days
        date = datetime.now() + timedelta(days=i)

        # Vary temperature slightly from base
        temp_variation = random.randint(-5, 5)
        day_temp = base_temp + temp_variation

        forecast.append({
            "date": date.strftime("%Y-%m-%d"),
            "day": date.strftime("%A"),
            "temperature": round(day_temp, 1),
            "condition": conditions[i % len(conditions)],
            "humidity": random.randint(40, 90),
            "wind_speed": random.randint(5, 25)
        })

    return forecast

def search_cities(query: str) -> List[str]:
    """
    Search for cities matching the query string.

    Args:
        query: City name or partial name to search

    Returns:
        list of matching city names
    """
    query_lower = query.lower().strip()

    # Search in mock data
    matching_cities = [
        city for city in MOCK_WEATHER_DATA.keys()
        if query_lower in city.lower()
    ]

    return sorted(matching_cities)

# Future: Real API integration
# def fetch_from_weather_api(city: str, api_key: str) -> Dict[str, Any]:
#     """
#     Fetch weather data from a real weather API (OpenWeatherMap, etc.).
#
#     Args:
#         city: City name
#         api_key: API key for weather service
#
#     Returns:
#         dict with weather data from API
#     """
#     import requests
#     import os
#
#     api_url = os.getenv("WEATHER_API_URL", "https://api.openweathermap.org/data/2.5")
#
#     try:
#         response = requests.get(
#             f"{api_url}/weather",
#             params={"q": city, "appid": api_key, "units": "metric"}
#         )
#         response.raise_for_status()
#         return response.json()
#     except Exception as e:
#         # Fallback to mock data on API failure
#         print(f"API error: {e}, falling back to mock data")
#         return get_current_weather(city)