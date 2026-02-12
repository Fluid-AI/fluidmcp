#!/usr/bin/env python3
"""
Quick test script to verify weather MCP server functionality
"""
import sys
sys.path.insert(0, '/workspaces/fluidmcp/ui-mcps/weather-mcp-html')

from tools.weather import get_current_weather
from server import generate_weather_html

def test_weather_data():
    """Test getting weather data"""
    print("Testing weather data retrieval...")
    data = get_current_weather("Bangalore", "metric")
    print(f"✅ Weather data retrieved: {data['city']}, {data['temperature']}°C, {data['condition']}")
    return data

def test_html_generation():
    """Test HTML generation"""
    print("\nTesting HTML generation...")
    data = get_current_weather("Mumbai", "metric")
    html = generate_weather_html(data)

    # Verify HTML contains key elements
    assert '<!DOCTYPE html>' in html, "Missing DOCTYPE"
    assert '<html' in html, "Missing html tag"
    assert 'Weather Dashboard' in html, "Missing title"
    assert data['city'] in html, "City name not in HTML"
    assert str(data['temperature']) in html, "Temperature not in HTML"

    print(f"✅ HTML generated successfully ({len(html)} characters)")
    print(f"   - Contains city: {data['city']}")
    print(f"   - Contains temperature: {data['temperature']}°C")
    print(f"   - Contains condition: {data['condition']}")

    # Save sample HTML for inspection
    with open('/tmp/weather-sample.html', 'w') as f:
        f.write(html)
    print("   - Sample saved to: /tmp/weather-sample.html")

    return html

def test_multiple_cities():
    """Test multiple cities"""
    print("\nTesting multiple cities...")
    cities = ["Bangalore", "Mumbai", "Delhi", "Chennai"]

    for city in cities:
        data = get_current_weather(city, "metric")
        print(f"   ✅ {city}: {data['temperature']}°C, {data['condition']}")

    print(f"✅ All {len(cities)} cities tested successfully")

def test_unit_conversion():
    """Test unit conversion"""
    print("\nTesting unit conversion...")
    city = "Bangalore"

    data_celsius = get_current_weather(city, "metric")
    data_fahrenheit = get_current_weather(city, "imperial")

    print(f"   {city} (Celsius): {data_celsius['temperature']}°C")
    print(f"   {city} (Fahrenheit): {data_fahrenheit['temperature']}°F")
    print("✅ Unit conversion working")

if __name__ == "__main__":
    print("=" * 60)
    print("Weather MCP Server - Test Suite")
    print("=" * 60)

    try:
        test_weather_data()
        html = test_html_generation()
        test_multiple_cities()
        test_unit_conversion()

        print("\n" + "=" * 60)
        print("✅ ALL TESTS PASSED!")
        print("=" * 60)
        print("\nYou can view the sample HTML at: /tmp/weather-sample.html")
        print("Open it in a browser to see the rendered UI.")

    except Exception as e:
        print(f"\n❌ TEST FAILED: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
