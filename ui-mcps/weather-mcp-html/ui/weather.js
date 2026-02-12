// Weather UI JavaScript
// MCP Apps Pattern: Receives data via postMessage, NOT fetch()

// Store the current weather data
let currentWeatherData = null;

// Listen for data from MCP client via postMessage
window.addEventListener("message", (event) => {
    const data = event.data;

    // Defensive guard: validate essential data exists
    if (!data || !data.city || data.temperature === undefined) {
        console.warn('Invalid weather data received:', data);
        return;
    }

    // MCP client sends the weather data that was returned by the tool
    console.log('Received weather data:', data);

    currentWeatherData = data;
    updateWeatherUI(data);
});

// Update UI with weather data
function updateWeatherUI(data) {
    if (!data) {
        document.getElementById('cityName').textContent = 'No data received';
        return;
    }

    // Update city name
    document.getElementById('cityName').textContent = data.city || 'Unknown';

    // Update temperature with appropriate unit symbol
    const tempSymbol = data.units === 'metric' ? '°C' : '°F';
    document.getElementById('temperature').textContent =
        `${data.temperature || '--'}${tempSymbol}`;

    // Update condition and description
    document.getElementById('condition').textContent = data.condition || '--';
    document.getElementById('description').textContent =
        data.description || 'No description available';

    // Update humidity and wind speed
    document.getElementById('humidity').textContent = `${data.humidity || '--'}%`;
    document.getElementById('windSpeed').textContent =
        `${data.wind_speed || '--'} km/h`;

    // Update weather icon based on condition
    const iconMap = {
        'Sunny': '☀️',
        'Cloudy': '☁️',
        'Rainy': '🌧️',
        'Stormy': '⛈️',
        'Snowy': '❄️',
        'Clear': '🌙'
    };
    document.getElementById('weatherIcon').textContent =
        iconMap[data.condition] || '🌤️';

    // Update unit toggle button text
    const unitToggle = document.getElementById('unitToggle');
    if (unitToggle) {
        unitToggle.textContent = data.units === 'metric' ? '°F' : '°C';
    }

    // Update timestamp
    if (data.timestamp) {
        const date = new Date(data.timestamp);
        document.getElementById('timestamp').textContent =
            `Updated: ${date.toLocaleTimeString()}`;
    }

    // Log success
    console.log('UI updated successfully with weather data');
}

// Initialize on page load
document.addEventListener('DOMContentLoaded', () => {
    console.log('Weather UI loaded, waiting for data via postMessage...');

    // Show loading state
    document.getElementById('cityName').textContent = 'Loading...';
    document.getElementById('description').textContent = 'Waiting for weather data from MCP server...';
});

// Unit toggle function (Phase 1: shows alert)
// Phase 2: Will communicate back to MCP client to re-invoke tool with different units
function toggleUnits() {
    alert('Unit toggle requires calling the MCP tool again with different units parameter.\n\nExample:\n  get_weather("Bangalore", "imperial")\n  get_weather("Mumbai", "metric")');
}

// Refresh weather function (Phase 1: shows alert)
// Phase 2: Will communicate back to MCP client to re-invoke tool
function refreshWeather() {
    alert('Refresh requires calling the MCP tool again.\n\nThe MCP client will re-fetch weather data by calling get_weather() with the same city.');
}

// Error handler for debugging
window.addEventListener('error', (event) => {
    console.error('UI Error:', event.error);
});

// Log when UI is fully ready
console.log('Weather MCP UI ready - using postMessage pattern (no fetch)');