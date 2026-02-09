#!/usr/bin/env python3
"""
Real-Time Stock + News Analyzer MCP Server
Provides stock data and news analysis using Yahoo Finance
"""

import asyncio
import json
import logging
from datetime import datetime, timedelta
from typing import Any

from mcp.server import Server
from mcp.types import (
    Tool,
    TextContent,
    ImageContent,
    EmbeddedResource,
)
import mcp.server.stdio

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("stock-analyzer-mcp")

# Initialize MCP server
app = Server("stock-analyzer")


def safe_import_yfinance():
    """Safely import yfinance with error handling"""
    try:
        import yfinance as yf
        return yf
    except ImportError:
        logger.error("yfinance not installed. Install with: pip install yfinance")
        raise


def generate_chart_html(ticker: str, data: list) -> str:
    """Generate self-contained HTML with Chart.js visualization"""
    dates = [d['date'] for d in data]
    opens = [d['open'] for d in data]
    highs = [d['high'] for d in data]
    lows = [d['low'] for d in data]
    closes = [d['close'] for d in data]
    volumes = [d['volume'] for d in data]

    # Calculate moving averages
    def moving_avg(data_list, window):
        result = []
        for i in range(len(data_list)):
            if i < window - 1:
                result.append(None)
            else:
                result.append(sum(data_list[i-window+1:i+1]) / window)
        return result

    ma7 = moving_avg(closes, 7)
    ma20 = moving_avg(closes, 20)

    return f'''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{ticker} Stock Chart</title>
    <script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
    <style>
        *{{margin:0;padding:0;box-sizing:border-box}}
        body{{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;background:#0f0f1e;min-height:100vh;padding:20px}}
        .container{{max-width:1200px;margin:0 auto;background:#1a1a2e;border-radius:12px;padding:30px;box-shadow:0 10px 40px rgba(0,0,0,0.3);border:1px solid #2a2a3e}}
        .header{{display:flex;justify-content:space-between;align-items:center;margin-bottom:30px;padding-bottom:20px;border-bottom:2px solid #2a2a3e}}
        h1{{color:#e0e0e0;font-size:28px}}
        .ticker{{color:#8b5cf6;font-weight:bold}}
        .controls{{display:flex;gap:10px;flex-wrap:wrap}}
        select,button{{padding:10px 16px;border-radius:8px;font-size:13px;cursor:pointer;transition:all 0.3s;background:#2a2a3e;color:#e0e0e0}}
        button{{background:#8b5cf6;color:white;border:none}}
        button:hover{{background:#7c3aed;transform:translateY(-1px);box-shadow:0 4px 12px rgba(139,92,246,0.4)}}
        select{{border:1px solid #3a3a4e}}
        select:hover{{border-color:#8b5cf6}}
        select:focus{{outline:none;border-color:#8b5cf6}}
        .chart-container{{position:relative;height:400px;margin-bottom:30px;background:#16162a;border-radius:8px;padding:15px}}
        .stats{{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:20px;margin-top:30px}}
        .stat-card{{background:#2a2a3e;color:white;padding:20px;border-radius:8px;text-align:center;border:1px solid #3a3a4e}}
        .stat-label{{font-size:11px;opacity:0.7;margin-bottom:8px;text-transform:uppercase;letter-spacing:1px;color:#a0a0b0}}
        .stat-value{{font-size:24px;font-weight:bold;color:#8b5cf6}}
        .data-table{{width:100%;margin-top:30px;border-collapse:collapse;display:none}}
        .data-table th,.data-table td{{padding:12px;text-align:left;border-bottom:1px solid #2a2a3e;color:#e0e0e0}}
        .data-table th{{background:#2a2a3e;font-weight:600;color:#a0a0b0;text-transform:uppercase;font-size:11px;letter-spacing:0.5px}}
        .data-table tr:hover{{background:#1f1f2e}}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>📈 <span class="ticker">{ticker}</span> Stock Analysis</h1>
            <div class="controls">
                <select id="chartTypeSelect" onchange="updateChart()">
                    <option value="line">📊 Line Chart</option>
                    <option value="bar">📊 Bar Chart</option>
                    <option value="area">📈 Area Chart</option>
                    <option value="candlestick">🕯️ Candlestick</option>
                </select>
                <select id="indicatorSelect" onchange="updateChart()">
                    <option value="none">No Indicators</option>
                    <option value="ma7">7-day MA</option>
                    <option value="ma20">20-day MA</option>
                    <option value="both">Both MAs</option>
                    <option value="volume">Volume Overlay</option>
                </select>
                <button onclick="toggleTable()">📋 Data Table</button>
                <button onclick="downloadCSV()">💾 CSV Export</button>
                <button onclick="toggleFullscreen()">⛶ Fullscreen</button>
            </div>
        </div>
        <div class="chart-container"><canvas id="chart"></canvas></div>
        <div class="stats">
            <div class="stat-card"><div class="stat-label">Current</div><div class="stat-value">${closes[-1]:.2f}</div></div>
            <div class="stat-card"><div class="stat-label">Change</div><div class="stat-value">{((closes[-1]-closes[0])/closes[0]*100):.2f}%</div></div>
            <div class="stat-card"><div class="stat-label">High</div><div class="stat-value">${max(highs):.2f}</div></div>
            <div class="stat-card"><div class="stat-label">Low</div><div class="stat-value">${min(lows):.2f}</div></div>
        </div>
        <table class="data-table" id="table">
            <thead><tr><th>Date</th><th>Open</th><th>High</th><th>Low</th><th>Close</th><th>Volume</th></tr></thead>
            <tbody>{"".join([f"<tr><td>{d['date']}</td><td>${d['open']:.2f}</td><td>${d['high']:.2f}</td><td>${d['low']:.2f}</td><td>${d['close']:.2f}</td><td>{d['volume']:,}</td></tr>" for d in data])}</tbody>
        </table>
    </div>
    <script>
        const data={{
            labels:{json.dumps(dates)},
            opens:{json.dumps(opens)},
            highs:{json.dumps(highs)},
            lows:{json.dumps(lows)},
            closes:{json.dumps(closes)},
            volumes:{json.dumps(volumes)},
            ma7:{json.dumps(ma7)},
            ma20:{json.dumps(ma20)}
        }};
        let chart;
        function createChart(type,indicator){{
            if(chart)chart.destroy();
            const datasets=[];

            // Main price dataset
            if(type==='candlestick'){{
                datasets.push({{
                    label:'OHLC',
                    data:data.closes,
                    type:'bar',
                    borderColor:'#8b5cf6',
                    backgroundColor:data.closes.map((c,i)=>c>=data.opens[i]?'rgba(34,197,94,0.7)':'rgba(239,68,68,0.7)'),
                    borderWidth:1
                }});
            }}else if(type==='area'){{
                datasets.push({{
                    label:'Price ($)',
                    data:data.closes,
                    borderColor:'#8b5cf6',
                    backgroundColor:'rgba(139,92,246,0.2)',
                    fill:true,
                    tension:0.4,
                    borderWidth:2,
                    pointRadius:2,
                    pointHoverRadius:5
                }});
            }}else{{
                datasets.push({{
                    label:'Price ($)',
                    data:data.closes,
                    borderColor:'#8b5cf6',
                    backgroundColor:type==='bar'?'rgba(139,92,246,0.7)':'rgba(139,92,246,0.1)',
                    tension:0.4,
                    borderWidth:2,
                    pointRadius:type==='line'?3:0,
                    pointHoverRadius:5,
                    fill:type==='bar'
                }});
            }}

            // Add indicators
            if(indicator==='ma7'||indicator==='both'){{
                datasets.push({{
                    label:'7-day MA',
                    data:data.ma7,
                    borderColor:'#22c55e',
                    borderDash:[5,5],
                    borderWidth:2,
                    pointRadius:0,
                    fill:false,
                    tension:0.4
                }});
            }}
            if(indicator==='ma20'||indicator==='both'){{
                datasets.push({{
                    label:'20-day MA',
                    data:data.ma20,
                    borderColor:'#ef4444',
                    borderDash:[5,5],
                    borderWidth:2,
                    pointRadius:0,
                    fill:false,
                    tension:0.4
                }});
            }}
            if(indicator==='volume'){{
                datasets.push({{
                    label:'Volume',
                    data:data.volumes,
                    type:'bar',
                    yAxisID:'volume',
                    backgroundColor:'rgba(139,92,246,0.3)',
                    borderWidth:0
                }});
            }}

            const scales={{
                x:{{ticks:{{color:'#a0a0b0',font:{{size:10}}}},grid:{{color:'#2a2a3e',drawBorder:false}}}},
                y:{{beginAtZero:false,ticks:{{color:'#a0a0b0',font:{{size:11}},callback:v=>'$'+v.toFixed(2)}},grid:{{color:'#2a2a3e',drawBorder:false}}}}
            }};

            if(indicator==='volume'){{
                scales.volume={{position:'right',beginAtZero:true,ticks:{{color:'#a0a0b0',font:{{size:10}}}},grid:{{display:false}}}};
            }}

            chart=new Chart(document.getElementById('chart'),{{
                type:type==='candlestick'?'bar':type==='area'?'line':type,
                data:{{labels:data.labels,datasets:datasets}},
                options:{{
                    responsive:true,
                    maintainAspectRatio:false,
                    interaction:{{mode:'index',intersect:false}},
                    plugins:{{
                        legend:{{display:true,labels:{{color:'#e0e0e0',font:{{size:12}}}}}},
                        tooltip:{{
                            backgroundColor:'rgba(26,26,46,0.95)',
                            titleColor:'#e0e0e0',
                            bodyColor:'#a0a0b0',
                            borderColor:'#8b5cf6',
                            borderWidth:1
                        }}
                    }},
                    scales:scales
                }}
            }});
        }}
        function updateChart(){{
            const type=document.getElementById('chartTypeSelect').value;
            const indicator=document.getElementById('indicatorSelect').value;
            createChart(type,indicator);
        }}
        function toggleTable(){{
            const t=document.getElementById('table');
            t.style.display=t.style.display==='none'?'table':'none';
        }}
        function downloadCSV(){{
            let csv='Date,Open,High,Low,Close,Volume\\n';
            data.labels.forEach((d,i)=>{{
                csv+=`${{d}},${{data.opens[i]}},${{data.highs[i]}},${{data.lows[i]}},${{data.closes[i]}},${{data.volumes[i]}}\\n`;
            }});
            const a=document.createElement('a');
            a.href='data:text/csv;charset=utf-8,'+encodeURIComponent(csv);
            a.download='{ticker}_stock_data.csv';
            a.click();
        }}
        function toggleFullscreen(){{
            const container=document.querySelector('.container');
            if(!document.fullscreenElement){{
                container.requestFullscreen().catch(err=>alert('Error enabling fullscreen: '+err.message));
            }}else{{
                document.exitFullscreen();
            }}
        }}
        createChart('line','none');
    </script>
</body>
</html>'''


@app.list_tools()
async def list_tools() -> list[Tool]:
    """List available stock analysis tools"""
    return [
        Tool(
            name="get_stock_price",
            description="Get real-time stock price and key metrics for a given ticker symbol",
            inputSchema={
                "type": "object",
                "properties": {
                    "ticker": {
                        "type": "string",
                        "description": "Stock ticker symbol (e.g., AAPL, GOOGL, MSFT)",
                    },
                },
                "required": ["ticker"],
            },
        ),
        Tool(
            name="get_stock_news",
            description="Get latest news articles for a given stock ticker",
            inputSchema={
                "type": "object",
                "properties": {
                    "ticker": {
                        "type": "string",
                        "description": "Stock ticker symbol (e.g., AAPL, GOOGL, MSFT)",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum number of news articles to return (default: 5)",
                        "default": 5,
                    },
                },
                "required": ["ticker"],
            },
        ),
        Tool(
            name="get_stock_history",
            description="Get historical stock price data",
            inputSchema={
                "type": "object",
                "properties": {
                    "ticker": {
                        "type": "string",
                        "description": "Stock ticker symbol (e.g., AAPL, GOOGL, MSFT)",
                    },
                    "period": {
                        "type": "string",
                        "description": "Time period (1d, 5d, 1mo, 3mo, 6mo, 1y, 2y, 5y, 10y, ytd, max)",
                        "default": "1mo",
                    },
                },
                "required": ["ticker"],
            },
        ),
        Tool(
            name="analyze_stock",
            description="Comprehensive stock analysis including price, metrics, and news",
            inputSchema={
                "type": "object",
                "properties": {
                    "ticker": {
                        "type": "string",
                        "description": "Stock ticker symbol (e.g., AAPL, GOOGL, MSFT)",
                    },
                },
                "required": ["ticker"],
            },
        ),
        Tool(
            name="compare_stocks",
            description="Compare multiple stocks side by side",
            inputSchema={
                "type": "object",
                "properties": {
                    "tickers": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of stock ticker symbols to compare",
                    },
                },
                "required": ["tickers"],
            },
        ),
        Tool(
            name="get_stock_chart",
            description="Get interactive HTML chart for stock (embeddable in iframe/sandbox)",
            inputSchema={
                "type": "object",
                "properties": {
                    "ticker": {
                        "type": "string",
                        "description": "Stock ticker symbol (e.g., AAPL, RELIANCE.NS)",
                    },
                    "period": {
                        "type": "string",
                        "description": "Time period (10d, 1mo, 3mo, 6mo, 1y)",
                        "default": "1mo",
                    },
                },
                "required": ["ticker"],
            },
        ),
    ]


@app.call_tool()
async def call_tool(name: str, arguments: Any) -> list[TextContent]:
    """Handle tool calls"""
    yf = safe_import_yfinance()

    try:
        if name == "get_stock_price":
            ticker = arguments.get("ticker", "").upper()
            stock = yf.Ticker(ticker)
            info = stock.info

            # Extract key metrics
            current_price = info.get("currentPrice") or info.get("regularMarketPrice", "N/A")
            previous_close = info.get("previousClose", "N/A")
            open_price = info.get("open", "N/A")
            day_high = info.get("dayHigh", "N/A")
            day_low = info.get("dayLow", "N/A")
            volume = info.get("volume", "N/A")
            market_cap = info.get("marketCap", "N/A")

            # Calculate change
            change = "N/A"
            change_percent = "N/A"
            if current_price != "N/A" and previous_close != "N/A":
                change = current_price - previous_close
                change_percent = (change / previous_close) * 100
                change = f"${change:.2f}"
                change_percent = f"{change_percent:.2f}%"

            # Format volume and market cap
            volume_str = f"{volume:,}" if isinstance(volume, (int, float)) else str(volume)
            market_cap_str = f"${market_cap:,}" if isinstance(market_cap, (int, float)) else str(market_cap)

            result = f"""Stock: {ticker}
Company: {info.get('longName', 'N/A')}
Current Price: ${current_price}
Change: {change} ({change_percent})
Previous Close: ${previous_close}
Open: ${open_price}
Day Range: ${day_low} - ${day_high}
Volume: {volume_str}
Market Cap: {market_cap_str}
"""

            return [TextContent(type="text", text=result)]

        elif name == "get_stock_news":
            ticker = arguments.get("ticker", "").upper()
            limit = arguments.get("limit", 5)

            stock = yf.Ticker(ticker)
            news = stock.news

            if not news:
                return [TextContent(type="text", text=f"No news found for {ticker}")]

            result = f"Latest News for {ticker}:\n\n"
            for i, article in enumerate(news[:limit], 1):
                title = article.get("title", "No title")
                publisher = article.get("publisher", "Unknown")
                link = article.get("link", "#")
                pub_date = article.get("providerPublishTime")

                if pub_date:
                    pub_date = datetime.fromtimestamp(pub_date).strftime("%Y-%m-%d %H:%M")
                else:
                    pub_date = "Unknown date"

                result += f"{i}. {title}\n"
                result += f"   Publisher: {publisher}\n"
                result += f"   Date: {pub_date}\n"
                result += f"   Link: {link}\n\n"

            return [TextContent(type="text", text=result)]

        elif name == "get_stock_history":
            ticker = arguments.get("ticker", "").upper()
            period = arguments.get("period", "1mo")

            stock = yf.Ticker(ticker)
            hist = stock.history(period=period)

            if hist.empty:
                return [TextContent(type="text", text=f"No historical data found for {ticker}")]

            result = f"Historical Data for {ticker} (Period: {period}):\n\n"
            result += f"{'Date':<12} {'Open':<10} {'High':<10} {'Low':<10} {'Close':<10} {'Volume':<15}\n"
            result += "-" * 67 + "\n"

            for date, row in hist.iterrows():
                date_str = date.strftime("%Y-%m-%d")
                result += f"{date_str:<12} ${row['Open']:<9.2f} ${row['High']:<9.2f} ${row['Low']:<9.2f} ${row['Close']:<9.2f} {int(row['Volume']):<15,}\n"

            return [TextContent(type="text", text=result)]

        elif name == "analyze_stock":
            ticker = arguments.get("ticker", "").upper()
            stock = yf.Ticker(ticker)
            info = stock.info

            # Get current price data
            current_price = info.get("currentPrice") or info.get("regularMarketPrice", "N/A")
            previous_close = info.get("previousClose", "N/A")

            # Calculate metrics
            change = "N/A"
            change_percent = "N/A"
            if current_price != "N/A" and previous_close != "N/A":
                change = current_price - previous_close
                change_percent = (change / previous_close) * 100

            # Get news
            news = stock.news[:3] if stock.news else []

            # Format change display
            change_str = f"${change:.2f} ({change_percent:.2f}%)" if change != "N/A" else "N/A"

            # Format market cap
            mc = info.get('marketCap', 'N/A')
            market_cap_display = f"${mc:,}" if isinstance(mc, (int, float)) else str(mc)

            result = f"""=== COMPREHENSIVE ANALYSIS: {ticker} ===

COMPANY INFO:
Name: {info.get('longName', 'N/A')}
Sector: {info.get('sector', 'N/A')}
Industry: {info.get('industry', 'N/A')}

PRICE DATA:
Current Price: ${current_price}
Change: {change_str}
52 Week Range: ${info.get('fiftyTwoWeekLow', 'N/A')} - ${info.get('fiftyTwoWeekHigh', 'N/A')}

KEY METRICS:
Market Cap: {market_cap_display}
P/E Ratio: {info.get('trailingPE', 'N/A')}
EPS: ${info.get('trailingEps', 'N/A')}
Dividend Yield: {info.get('dividendYield', 'N/A')}

LATEST NEWS:
"""

            for i, article in enumerate(news, 1):
                result += f"{i}. {article.get('title', 'No title')}\n"
                result += f"   {article.get('publisher', 'Unknown')} - {datetime.fromtimestamp(article.get('providerPublishTime', 0)).strftime('%Y-%m-%d')}\n\n"

            return [TextContent(type="text", text=result)]

        elif name == "compare_stocks":
            tickers = [t.upper() for t in arguments.get("tickers", [])]

            if len(tickers) < 2:
                return [TextContent(type="text", text="Please provide at least 2 tickers to compare")]

            result = f"=== STOCK COMPARISON ===\n\n"
            result += f"{'Metric':<20} " + " ".join([f"{t:<12}" for t in tickers]) + "\n"
            result += "-" * (20 + 13 * len(tickers)) + "\n"

            # Collect data for each ticker
            data = {}
            for ticker in tickers:
                stock = yf.Ticker(ticker)
                info = stock.info
                data[ticker] = {
                    'price': info.get('currentPrice') or info.get('regularMarketPrice', 'N/A'),
                    'market_cap': info.get('marketCap', 'N/A'),
                    'pe_ratio': info.get('trailingPE', 'N/A'),
                    'dividend_yield': info.get('dividendYield', 'N/A'),
                    '52w_high': info.get('fiftyTwoWeekHigh', 'N/A'),
                    '52w_low': info.get('fiftyTwoWeekLow', 'N/A'),
                }

            # Format comparison table
            metrics = [
                ('Current Price', 'price', lambda x: f"${x:.2f}" if isinstance(x, (int, float)) else "N/A"),
                ('Market Cap', 'market_cap', lambda x: f"${x:,.0f}" if isinstance(x, (int, float)) else "N/A"),
                ('P/E Ratio', 'pe_ratio', lambda x: f"{x:.2f}" if isinstance(x, (int, float)) else "N/A"),
                ('Div Yield', 'dividend_yield', lambda x: f"{x*100:.2f}%" if isinstance(x, (int, float)) else "N/A"),
                ('52W High', '52w_high', lambda x: f"${x:.2f}" if isinstance(x, (int, float)) else "N/A"),
                ('52W Low', '52w_low', lambda x: f"${x:.2f}" if isinstance(x, (int, float)) else "N/A"),
            ]

            for metric_name, key, formatter in metrics:
                result += f"{metric_name:<20} "
                for ticker in tickers:
                    value = data[ticker].get(key, 'N/A')
                    formatted = formatter(value)
                    result += f"{formatted:<12} "
                result += "\n"

            return [TextContent(type="text", text=result)]

        elif name == "get_stock_chart":
            ticker = arguments.get("ticker", "").upper()
            period = arguments.get("period", "1mo")

            stock = yf.Ticker(ticker)
            hist = stock.history(period=period)

            if hist.empty:
                return [TextContent(type="text", text=f"No historical data found for {ticker}")]

            # Convert to list of dictionaries for chart
            data = []
            for date, row in hist.iterrows():
                data.append({
                    "date": date.strftime("%Y-%m-%d"),
                    "open": round(float(row['Open']), 2),
                    "high": round(float(row['High']), 2),
                    "low": round(float(row['Low']), 2),
                    "close": round(float(row['Close']), 2),
                    "volume": int(row['Volume'])
                })

            # Generate HTML chart
            html = generate_chart_html(ticker, data)
            return [TextContent(type="text", text=html)]

        else:
            return [TextContent(type="text", text=f"Unknown tool: {name}")]

    except Exception as e:
        logger.error(f"Error executing {name}: {str(e)}")
        return [TextContent(type="text", text=f"Error: {str(e)}")]


async def main():
    """Run the MCP server"""
    logger.info("Starting Stock Analyzer MCP Server")
    async with mcp.server.stdio.stdio_server() as (read_stream, write_stream):
        await app.run(
            read_stream,
            write_stream,
            app.create_initialization_options(),
        )


if __name__ == "__main__":
    asyncio.run(main())
