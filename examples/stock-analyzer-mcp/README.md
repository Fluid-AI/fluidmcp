# Stock Analyzer MCP Server

Real-time stock data and news analyzer using Yahoo Finance with dark theme charts.

## Files

- `server.py` - Main MCP server with 5 stock analysis tools
- `test_ui.html` - Web interface for testing (port 8098)
- `metadata.json` - Server metadata for FluidMCP
- `requirements.txt` - Python dependencies (yfinance)

## Quick Start

```bash
# Start the server
fluidmcp run examples/stock-analyzer-config.json --file --start-server

# Server runs on port 8099
# MCP endpoint: http://localhost:8099/stock-analyzer/mcp
```

## Available Tools

1. `get_stock_price` - Current price and metrics
2. `get_stock_news` - Latest news articles
3. `get_stock_history` - Historical price data (text table)
4. `get_stock_chart` - Interactive HTML chart (dark theme) ⭐ NEW
5. `analyze_stock` - Comprehensive analysis
6. `compare_stocks` - Side-by-side comparison

### Enhanced Chart Features
- 🎨 Matches modern dark UI interfaces
- 📊 Interactive Chart.js visualization
- 🟣 Purple accent colors (#8b5cf6)
- 🌑 Dark background (#0f0f1e, #1a1a2e)

**Chart Types (Dropdown Selector):**
- 📊 Line Chart - Classic line graph with gradient
- 📊 Bar Chart - Bar visualization for comparisons
- 📈 Area Chart - Filled area under the line
- 🕯️ Candlestick - OHLC bars (green=bullish, red=bearish)

**Technical Indicators (Dropdown Selector):**
- 📈 7-day Moving Average (MA7) - Green dashed line
- 📈 20-day Moving Average (MA20) - Red dashed line
- 📊 Both MAs - Display both averages together
- 📊 Volume Overlay - Show volume bars on separate axis

**Interactive Controls:**
- 📋 Data Table - Show/hide full OHLC table
- 💾 CSV Export - Download with Open, High, Low, Close, Volume
- ⛶ Fullscreen - Toggle fullscreen mode for better viewing

## Ticker Formats

- US stocks: `AAPL`, `TSLA`, `GOOGL`
- Indian stocks: `RELIANCE.NS`, `INFY.NS`

## Data Source

Yahoo Finance via `yfinance` library (free, no API key required).
