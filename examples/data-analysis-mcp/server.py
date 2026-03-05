#!/usr/bin/env python3
"""
Data Analysis MCP Server - Advanced Data Analysis like ChatGPT's feature
"""

import asyncio
import json
import statistics
import math
import uuid
import sys
import argparse
from typing import Any, Dict, List, Tuple, Optional
from datetime import datetime
from mcp.server import Server
from mcp.types import Tool, TextContent, Resource
import mcp.server.stdio

# Initialize MCP server
app = Server("data-analysis")

# Store UI-enabled analysis results
analysis_cache: Dict[str, Dict[str, Any]] = {}


# ============================================================================
# DATASET PARSING
# ============================================================================

def parse_dataset(dataset: Any) -> List[Dict[str, Any]]:
    """
    Parse dataset from multiple formats:
    - JSON array string
    - JSON object wrapping a list
    - Pre-parsed Python list
    - CSV text
    """
    if isinstance(dataset, list):
        return dataset
    
    if isinstance(dataset, str):
        # Try JSON first
        try:
            parsed = json.loads(dataset)
            if isinstance(parsed, list):
                return parsed
            elif isinstance(parsed, dict):
                # Check if it's a wrapper object with a list
                for key, value in parsed.items():
                    if isinstance(value, list):
                        return value
                # Single object - wrap in list
                return [parsed]
            return []
        except json.JSONDecodeError:
            pass
        
        # Try CSV
        lines = dataset.strip().split('\n')
        if len(lines) < 2:
            return []
        
        headers = [h.strip() for h in lines[0].split(',')]
        rows = []
        for line in lines[1:]:
            values = [v.strip() for v in line.split(',')]
            if len(values) == len(headers):
                row = {}
                for i, header in enumerate(headers):
                    row[header] = coerce_value(values[i])
                rows.append(row)
        return rows
    
    return []


def coerce_value(val: Any) -> Any:
    """Silently coerce string values to int or float where possible"""
    if not isinstance(val, str):
        return val
    
    val = val.strip()
    
    # Try int
    try:
        return int(val)
    except ValueError:
        pass
    
    # Try float
    try:
        return float(val)
    except ValueError:
        pass
    
    return val


# ============================================================================
# COLUMN CLASSIFICATION
# ============================================================================

TIME_KEYWORDS = ['date', 'time', 'year', 'month', 'week', 'day', 'quarter', 
                 'period', 'timestamp', 'dt', 'created_at', 'updated_at']

def is_time_column(col_name: str, values: List[Any]) -> bool:
    """Check if column is time-based"""
    col_lower = col_name.lower()
    
    # Check name
    if any(keyword in col_lower for keyword in TIME_KEYWORDS):
        return True
    
    # Check if values parse as dates
    sample = [v for v in values[:10] if v is not None]
    if not sample:
        return False
    
    date_count = 0
    for val in sample:
        if isinstance(val, str):
            # Try common date patterns
            try:
                datetime.strptime(val, '%Y-%m-%d')
                date_count += 1
            except:
                try:
                    datetime.strptime(val, '%Y/%m/%d')
                    date_count += 1
                except:
                    pass
    
    return date_count >= len(sample) * 0.5


def is_numeric_column(values: List[Any]) -> bool:
    """Check if at least 80% of values are numeric"""
    non_none = [v for v in values if v is not None]
    if not non_none:
        return False
    
    numeric_count = sum(1 for v in non_none if isinstance(v, (int, float)))
    return numeric_count >= len(non_none) * 0.8


def classify_columns(data: List[Dict[str, Any]]) -> Dict[str, str]:
    """
    Classify each column as 'time', 'numeric', or 'categorical'
    """
    if not data:
        return {}
    
    columns = {}
    all_cols = set()
    for row in data:
        all_cols.update(row.keys())
    
    for col in all_cols:
        values = [row.get(col) for row in data]
        
        if is_time_column(col, values):
            columns[col] = 'time'
        elif is_numeric_column(values):
            columns[col] = 'numeric'
        else:
            columns[col] = 'categorical'
    
    return columns


# ============================================================================
# PURE PYTHON STATS HELPERS
# ============================================================================

def compute_stats(values: List[float]) -> Dict[str, float]:
    """Compute statistics using only stdlib"""
    clean = [v for v in values if v is not None and isinstance(v, (int, float))]
    if not clean:
        return {
            'min': 0, 'max': 0, 'mean': 0, 'median': 0, 'std_dev': 0
        }
    
    return {
        'min': min(clean),
        'max': max(clean),
        'mean': statistics.mean(clean),
        'median': statistics.median(clean),
        'std_dev': statistics.stdev(clean) if len(clean) > 1 else 0
    }


def pearson_correlation(x: List[float], y: List[float]) -> float:
    """Compute Pearson correlation coefficient"""
    # Filter out None values
    pairs = [(xi, yi) for xi, yi in zip(x, y) 
             if xi is not None and yi is not None 
             and isinstance(xi, (int, float)) 
             and isinstance(yi, (int, float))]
    
    if len(pairs) < 2:
        return 0.0
    
    x_vals = [p[0] for p in pairs]
    y_vals = [p[1] for p in pairs]
    
    n = len(x_vals)
    mean_x = sum(x_vals) / n
    mean_y = sum(y_vals) / n
    
    numerator = sum((x_vals[i] - mean_x) * (y_vals[i] - mean_y) for i in range(n))
    
    sum_sq_x = sum((x - mean_x) ** 2 for x in x_vals)
    sum_sq_y = sum((y - mean_y) ** 2 for y in y_vals)
    
    denominator = math.sqrt(sum_sq_x * sum_sq_y)
    
    if denominator == 0:
        return 0.0
    
    return numerator / denominator


def detect_trend(values: List[float]) -> str:
    """Return 'upward', 'downward', or 'flat'"""
    clean = [v for v in values if v is not None and isinstance(v, (int, float))]
    if len(clean) < 4:
        return 'flat'
    
    mid = len(clean) // 2
    first_half = clean[:mid]
    second_half = clean[mid:]
    
    mean_first = statistics.mean(first_half)
    mean_second = statistics.mean(second_half)
    
    change_pct = abs((mean_second - mean_first) / mean_first) if mean_first != 0 else 0
    
    if change_pct < 0.05:
        return 'flat'
    elif mean_second > mean_first:
        return 'upward'
    else:
        return 'downward'


def detect_outliers(values: List[float], col_name: str) -> List[str]:
    """Detect values > 2 std devs from mean"""
    clean = [v for v in values if v is not None and isinstance(v, (int, float))]
    if len(clean) < 3:
        return []
    
    mean = statistics.mean(clean)
    std_dev = statistics.stdev(clean)
    
    if std_dev == 0:
        return []
    
    outliers = []
    for i, val in enumerate(values):
        if isinstance(val, (int, float)):
            z_score = abs((val - mean) / std_dev)
            if z_score > 2:
                outliers.append(f"Row {i+1}: {col_name} = {val:.2f} (z-score: {z_score:.2f})")
    
    return outliers[:5]  # Limit to 5


def compute_histogram(values: List[float], bins: int = 8) -> Tuple[List[str], List[int]]:
    """Bucket values into N bins"""
    clean = [v for v in values if v is not None and isinstance(v, (int, float))]
    if not clean:
        return [], []
    
    min_val = min(clean)
    max_val = max(clean)
    
    if min_val == max_val:
        return [f"{min_val:.2f}"], [len(clean)]
    
    bin_width = (max_val - min_val) / bins
    counts = [0] * bins
    labels = []
    
    for i in range(bins):
        start = min_val + i * bin_width
        end = min_val + (i + 1) * bin_width
        labels.append(f"{start:.1f}-{end:.1f}")
    
    for val in clean:
        bin_idx = int((val - min_val) / bin_width)
        if bin_idx >= bins:
            bin_idx = bins - 1
        counts[bin_idx] += 1
    
    return labels, counts


# ============================================================================
# SMART INSIGHTS
# ============================================================================

def generate_insights(data: List[Dict[str, Any]], col_types: Dict[str, str]) -> List[str]:
    """Generate smart insights about the dataset"""
    insights = []
    
    if not data:
        return insights
    
    numeric_cols = [col for col, typ in col_types.items() if typ == 'numeric']
    
    # Highest and lowest values
    for col in numeric_cols[:3]:  # Limit to 3
        values = [row.get(col) for row in data]
        clean = [(i, v) for i, v in enumerate(values) if isinstance(v, (int, float))]
        if clean:
            clean.sort(key=lambda x: x[1])
            min_idx, min_val = clean[0]
            max_idx, max_val = clean[-1]
            
            # Try to get a label
            label_col = next((c for c in data[0].keys() if c != col), None)
            if label_col:
                min_label = data[min_idx].get(label_col, f'Row {min_idx+1}')
                max_label = data[max_idx].get(label_col, f'Row {max_idx+1}')
                insights.append(f"<strong>{col}</strong>: Highest is {max_val:.2f} ({max_label}), lowest is {min_val:.2f} ({min_label})")
            else:
                insights.append(f"<strong>{col}</strong>: Range from {min_val:.2f} to {max_val:.2f}")
    
    # Time series percentage change
    time_cols = [col for col, typ in col_types.items() if typ == 'time']
    if time_cols and numeric_cols:
        time_col = time_cols[0]
        num_col = numeric_cols[0]
        values = [row.get(num_col) for row in data]
        clean = [v for v in values if isinstance(v, (int, float))]
        if len(clean) >= 2:
            first_val = clean[0]
            last_val = clean[-1]
            if first_val != 0:
                pct_change = ((last_val - first_val) / first_val) * 100
                direction = "increased" if pct_change > 0 else "decreased"
                insights.append(f"<strong>{num_col}</strong> {direction} by <strong>{abs(pct_change):.1f}%</strong> from first to last period")
    
    # Correlation
    if len(numeric_cols) >= 2:
        max_corr = 0
        corr_pair = None
        for i, col1 in enumerate(numeric_cols):
            for col2 in numeric_cols[i+1:]:
                vals1 = [row.get(col1) for row in data]
                vals2 = [row.get(col2) for row in data]
                corr = pearson_correlation(vals1, vals2)
                if abs(corr) > abs(max_corr):
                    max_corr = corr
                    corr_pair = (col1, col2)
        
        if corr_pair and abs(max_corr) > 0.3:
            direction = "positive" if max_corr > 0 else "negative"
            insights.append(f"Strongest correlation: <strong>{corr_pair[0]}</strong> and <strong>{corr_pair[1]}</strong> ({direction}, r={max_corr:.2f})")
    
    # Trend
    if numeric_cols:
        col = numeric_cols[0]
        values = [row.get(col) for row in data]
        trend = detect_trend(values)
        if trend != 'flat':
            insights.append(f"<strong>{col}</strong> shows an <strong>{trend}</strong> trend over time")
    
    # Outliers
    for col in numeric_cols[:2]:
        values = [row.get(col) for row in data]
        outliers = detect_outliers(values, col)
        if outliers:
            insights.append(f"Outliers detected in <strong>{col}</strong>: {outliers[0]}")
    
    return insights


# ============================================================================
# CHART GENERATION
# ============================================================================

def get_chart_color(index: int) -> str:
    """Get color from palette"""
    colors = ['#6c63ff', '#22c55e', '#f59e0b', '#ef4444', '#38bdf8', '#fb923c', '#a78bfa', '#34d399']
    return colors[index % len(colors)]


def generate_charts(data: List[Dict[str, Any]], col_types: Dict[str, str]) -> List[Dict[str, Any]]:
    """Generate chart configs based on column types"""
    charts = []
    
    time_cols = [col for col, typ in col_types.items() if typ == 'time']
    numeric_cols = [col for col, typ in col_types.items() if typ == 'numeric']
    categorical_cols = [col for col, typ in col_types.items() if typ == 'categorical']
    
    # 1 time col + 1 numeric col → line chart
    if time_cols and numeric_cols:
        time_col = time_cols[0]
        for num_col in numeric_cols[:3]:
            labels = [str(row.get(time_col, '')) for row in data]
            values = [row.get(num_col, 0) for row in data]
            charts.append({
                'type': 'line',
                'title': f'{num_col} over {time_col}',
                'labels': labels,
                'datasets': [{
                    'label': num_col,
                    'data': values,
                    'borderColor': get_chart_color(0),
                    'backgroundColor': get_chart_color(0) + '20',
                    'fill': True
                }]
            })
    
    # 1 categorical col + 1 numeric col → bar chart
    if categorical_cols and numeric_cols:
        cat_col = categorical_cols[0]
        for num_col in numeric_cols[:2]:
            labels = [str(row.get(cat_col, '')) for row in data]
            values = [row.get(num_col, 0) for row in data]
            charts.append({
                'type': 'bar',
                'title': f'{num_col} by {cat_col}',
                'labels': labels,
                'datasets': [{
                    'label': num_col,
                    'data': values,
                    'backgroundColor': [get_chart_color(i) for i in range(len(labels))]
                }]
            })
    
    # Pie chart for percentage columns
    for col in list(col_types.keys()):
        if any(keyword in col.lower() for keyword in ['pct', 'percent', 'rate', 'share', 'ratio']):
            labels = [str(row.get(categorical_cols[0] if categorical_cols else time_cols[0], f'Row {i+1}')) 
                     for i, row in enumerate(data)]
            values = [row.get(col, 0) for row in data]
            charts.append({
                'type': 'pie',
                'title': f'{col} Distribution',
                'labels': labels[:8],  # Limit for readability
                'datasets': [{
                    'data': values[:8],
                    'backgroundColor': [get_chart_color(i) for i in range(min(8, len(labels)))]
                }]
            })
            break
    
    # Scatter plot for 2 numeric cols
    if len(numeric_cols) >= 2:
        x_col = numeric_cols[0]
        y_col = numeric_cols[1]
        data_points = [{'x': row.get(x_col, 0), 'y': row.get(y_col, 0)} for row in data]
        charts.append({
            'type': 'scatter',
            'title': f'{y_col} vs {x_col}',
            'labels': [],
            'datasets': [{
                'label': f'{y_col} vs {x_col}',
                'data': data_points,
                'backgroundColor': get_chart_color(0)
            }]
        })
    
    # Histogram for first numeric column
    if numeric_cols:
        col = numeric_cols[0]
        values = [row.get(col) for row in data]
        labels, counts = compute_histogram(values)
        if labels:
            charts.append({
                'type': 'bar',
                'title': f'{col} Distribution (Histogram)',
                'labels': labels,
                'datasets': [{
                    'label': 'Frequency',
                    'data': counts,
                    'backgroundColor': get_chart_color(2)
                }]
            })
    
    # Radar chart for 3+ numeric columns
    if len(numeric_cols) >= 3:
        # Use first row as example
        labels = numeric_cols[:6]
        values = [data[0].get(col, 0) for col in labels]
        charts.append({
            'type': 'radar',
            'title': 'Multi-dimensional Profile',
            'labels': labels,
            'datasets': [{
                'label': 'Values',
                'data': values,
                'borderColor': get_chart_color(4),
                'backgroundColor': get_chart_color(4) + '40'
            }]
        })
    
    return charts[:6]  # Limit to 6 charts


# ============================================================================
# HTML GENERATION
# ============================================================================

def generate_dashboard_html(data: List[Dict[str, Any]], col_types: Dict[str, str]) -> str:
    """Generate interactive dashboard HTML"""
    
    if not data:
        return generate_empty_state_html()
    
    dataset_title = "Dataset Analysis"
    row_count = len(data)
    col_count = len(col_types)
    
    numeric_cols = [col for col, typ in col_types.items() if typ == 'numeric']
    
    # Compute stats for numeric columns
    stats_cards_html = ""
    for col in numeric_cols:
        values = [row.get(col) for row in data]
        stats = compute_stats(values)
        stats_cards_html += f'''
        <div class="stat-card">
            <div class="stat-label">{col}</div>
            <div class="stat-grid">
                <div class="stat-item">
                    <span class="stat-key">Min</span>
                    <span class="stat-value">{stats['min']:.2f}</span>
                </div>
                <div class="stat-item">
                    <span class="stat-key">Max</span>
                    <span class="stat-value">{stats['max']:.2f}</span>
                </div>
                <div class="stat-item">
                    <span class="stat-key">Mean</span>
                    <span class="stat-value">{stats['mean']:.2f}</span>
                </div>
                <div class="stat-item">
                    <span class="stat-key">Median</span>
                    <span class="stat-value">{stats['median']:.2f}</span>
                </div>
            </div>
        </div>
        '''
    
    # Generate insights
    insights = generate_insights(data, col_types)
    insights_html = "".join(f"<li>{insight}</li>" for insight in insights)
    
    # Generate charts
    charts = generate_charts(data, col_types)
    charts_json = json.dumps(charts)
    
    # Generate data table
    table_headers = "".join(f"<th>{col}</th>" for col in data[0].keys())
    table_rows = ""
    for row in data[:100]:  # Limit to 100 rows
        cells = "".join(f"<td>{row.get(col, '')}</td>" for col in data[0].keys())
        table_rows += f"<tr>{cells}</tr>"
    
    return f'''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{dataset_title}</title>
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <style>
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}
        
        :root {{
            --bg-primary: #0f1117;
            --bg-secondary: #1a1d27;
            --bg-card: #1a1d27;
            --accent: #6c63ff;
            --text-primary: #e8eaf0;
            --text-secondary: #9ca3af;
            --border: #2a2d3a;
        }}
        
        body.light-theme {{
            --bg-primary: #f8fafc;
            --bg-secondary: #ffffff;
            --bg-card: #ffffff;
            --accent: #4f46e5;
            --text-primary: #1e293b;
            --text-secondary: #64748b;
            --border: #e2e8f0;
        }}
        
        body {{
            font-family: 'Inter', 'Segoe UI', -apple-system, sans-serif;
            background: var(--bg-primary);
            color: var(--text-primary);
            padding: 20px;
        }}
        
        .header {{
            position: sticky;
            top: 0;
            background: var(--bg-secondary);
            padding: 20px;
            border-radius: 12px;
            margin-bottom: 20px;
            display: flex;
            justify-content: space-between;
            align-items: center;
            border: 1px solid var(--border);
            z-index: 100;
        }}
        
        .header-info h1 {{
            font-size: 24px;
            margin-bottom: 8px;
        }}
        
        .header-meta {{
            color: var(--text-secondary);
            font-size: 14px;
        }}
        
        .theme-toggle {{
            padding: 8px 16px;
            background: var(--accent);
            color: white;
            border: none;
            border-radius: 8px;
            cursor: pointer;
            font-size: 14px;
            font-weight: 600;
        }}
        
        .stats-container {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
            gap: 16px;
            margin-bottom: 20px;
        }}
        
        .stat-card {{
            background: var(--bg-card);
            border: 1px solid var(--border);
            border-radius: 12px;
            padding: 20px;
        }}
        
        .stat-label {{
            font-size: 14px;
            font-weight: 600;
            color: var(--text-secondary);
            margin-bottom: 12px;
        }}
        
        .stat-grid {{
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 12px;
        }}
        
        .stat-item {{
            display: flex;
            flex-direction: column;
        }}
        
        .stat-key {{
            font-size: 12px;
            color: var(--text-secondary);
        }}
        
        .stat-value {{
            font-size: 20px;
            font-weight: 700;
            color: var(--accent);
        }}
        
        .insights-panel {{
            background: var(--bg-card);
            border: 1px solid var(--border);
            border-radius: 12px;
            padding: 20px;
            margin-bottom: 20px;
        }}
        
        .insights-panel h2 {{
            font-size: 18px;
            margin-bottom: 16px;
            color: var(--accent);
        }}
        
        .insights-panel ul {{
            list-style: none;
            padding: 0;
        }}
        
        .insights-panel li {{
            padding: 10px 0;
            border-bottom: 1px solid var(--border);
            line-height: 1.6;
        }}
        
        .insights-panel li:last-child {{
            border-bottom: none;
        }}
        
        .charts-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(500px, 1fr));
            gap: 20px;
            margin-bottom: 20px;
        }}
        
        @media (max-width: 768px) {{
            .charts-grid {{
                grid-template-columns: 1fr;
            }}
        }}
        
        .chart-card {{
            background: var(--bg-card);
            border: 1px solid var(--border);
            border-radius: 12px;
            padding: 20px;
        }}
        
        .chart-header {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 16px;
        }}
        
        .chart-title {{
            font-size: 16px;
            font-weight: 600;
        }}
        
        .chart-controls {{
            display: flex;
            gap: 8px;
        }}
        
        .chart-btn {{
            padding: 6px 12px;
            background: var(--bg-secondary);
            border: 1px solid var(--border);
            border-radius: 6px;
            color: var(--text-primary);
            cursor: pointer;
            font-size: 12px;
        }}
        
        .chart-btn:hover {{
            background: var(--accent);
            color: white;
        }}
        
        .chart-canvas {{
            position: relative;
            height: 300px;
        }}
        
        .tabs {{
            display: flex;
            gap: 8px;
            margin-bottom: 20px;
            border-bottom: 1px solid var(--border);
        }}
        
        .tab {{
            padding: 12px 24px;
            background: none;
            border: none;
            color: var(--text-secondary);
            cursor: pointer;
            font-size: 14px;
            font-weight: 600;
            border-bottom: 2px solid transparent;
        }}
        
        .tab.active {{
            color: var(--accent);
            border-bottom-color: var(--accent);
        }}
        
        .tab-content {{
            display: none;
        }}
        
        .tab-content.active {{
            display: block;
        }}
        
        .data-table {{
            background: var(--bg-card);
            border: 1px solid var(--border);
            border-radius: 12px;
            overflow: hidden;
        }}
        
        table {{
            width: 100%;
            border-collapse: collapse;
        }}
        
        th {{
            background: var(--bg-secondary);
            padding: 12px;
            text-align: left;
            font-weight: 600;
            font-size: 14px;
            border-bottom: 2px solid var(--border);
        }}
        
        td {{
            padding: 12px;
            border-bottom: 1px solid var(--border);
            font-size: 14px;
        }}
        
        tr:hover {{
            background: var(--bg-secondary);
        }}
    </style>
</head>
<body>
    <div class="header">
        <div class="header-info">
            <h1>{dataset_title}</h1>
            <div class="header-meta">{row_count} rows × {col_count} columns</div>
        </div>
        <button class="theme-toggle" onclick="toggleTheme()">Toggle Theme</button>
    </div>
    
    <div class="stats-container">
        {stats_cards_html}
    </div>
    
    <div class="insights-panel">
        <h2>🔍 Smart Insights</h2>
        <ul>
            {insights_html}
        </ul>
    </div>
    
    <div class="tabs">
        <button class="tab active" onclick="switchTab(event, 'charts')">Charts</button>
        <button class="tab" onclick="switchTab(event, 'data')">Data Table</button>
    </div>
    
    <div id="charts" class="tab-content active">
        <div class="charts-grid" id="chartsGrid"></div>
    </div>
    
    <div id="data" class="tab-content">
        <div class="data-table">
            <table>
                <thead>
                    <tr>{table_headers}</tr>
                </thead>
                <tbody>
                    {table_rows}
                </tbody>
            </table>
        </div>
    </div>
    
    <script>
        Chart.defaults.font.family = "'Inter', 'Segoe UI', sans-serif";
        Chart.defaults.color = getComputedStyle(document.documentElement).getPropertyValue('--text-primary');
        Chart.defaults.borderColor = getComputedStyle(document.documentElement).getPropertyValue('--border');
        
        const charts = {charts_json};
        const chartInstances = [];
        
        function renderCharts() {{
            const grid = document.getElementById('chartsGrid');
            grid.innerHTML = '';
            
            // Destroy existing charts
            chartInstances.forEach(chart => chart.destroy());
            chartInstances.length = 0;
            
            charts.forEach((chartConfig, index) => {{
                const card = document.createElement('div');
                card.className = 'chart-card';
                
                const header = document.createElement('div');
                header.className = 'chart-header';
                
                const title = document.createElement('div');
                title.className = 'chart-title';
                title.textContent = chartConfig.title;
                
                header.appendChild(title);
                card.appendChild(header);
                
                const canvasContainer = document.createElement('div');
                canvasContainer.className = 'chart-canvas';
                
                const canvas = document.createElement('canvas');
                canvas.id = `chart-${{index}}`;
                canvasContainer.appendChild(canvas);
                card.appendChild(canvasContainer);
                
                grid.appendChild(card);
                
                const ctx = canvas.getContext('2d');
                const chart = new Chart(ctx, {{
                    type: chartConfig.type,
                    data: {{
                        labels: chartConfig.labels,
                        datasets: chartConfig.datasets
                    }},
                    options: {{
                        responsive: true,
                        maintainAspectRatio: false,
                        plugins: {{
                            legend: {{
                                display: chartConfig.type !== 'pie',
                                labels: {{
                                    color: getComputedStyle(document.documentElement).getPropertyValue('--text-primary')
                                }}
                            }},
                            tooltip: {{
                                enabled: true
                            }}
                        }},
                        scales: chartConfig.type === 'pie' || chartConfig.type === 'radar' ? undefined : {{
                            x: {{
                                grid: {{
                                    color: getComputedStyle(document.documentElement).getPropertyValue('--border')
                                }},
                                ticks: {{
                                    color: getComputedStyle(document.documentElement).getPropertyValue('--text-secondary')
                                }}
                            }},
                            y: {{
                                grid: {{
                                    color: getComputedStyle(document.documentElement).getPropertyValue('--border')
                                }},
                                ticks: {{
                                    color: getComputedStyle(document.documentElement).getPropertyValue('--text-secondary')
                                }}
                            }}
                        }}
                    }}
                }});
                
                chartInstances.push(chart);
            }});
        }}
        
        function toggleTheme() {{
            document.body.classList.toggle('light-theme');
            renderCharts();
        }}
        
        function switchTab(event, tabName) {{
            const tabs = document.querySelectorAll('.tab');
            const contents = document.querySelectorAll('.tab-content');
            
            tabs.forEach(tab => tab.classList.remove('active'));
            contents.forEach(content => content.classList.remove('active'));
            
            event.target.classList.add('active');
            document.getElementById(tabName).classList.add('active');
        }}
        
        renderCharts();
    </script>
</body>
</html>'''


def generate_data_table_html(data: List[Dict[str, Any]], col_types: Dict[str, str]) -> str:
    """Generate paginated searchable data table with export"""
    
    if not data:
        return generate_empty_state_html()
    
    # Column statistics
    numeric_cols = [col for col, typ in col_types.items() if typ == 'numeric']
    stats_sidebar_html = ""
    
    for col in numeric_cols:
        values = [row.get(col) for row in data]
        stats = compute_stats(values)
        stats_sidebar_html += f'''
        <div class="stat-box">
            <h3>{col}</h3>
            <div class="stat-row"><span>Min:</span> <span>{stats['min']:.2f}</span></div>
            <div class="stat-row"><span>Max:</span> <span>{stats['max']:.2f}</span></div>
            <div class="stat-row"><span>Mean:</span> <span>{stats['mean']:.2f}</span></div>
            <div class="stat-row"><span>Median:</span> <span>{stats['median']:.2f}</span></div>
            <div class="stat-row"><span>Std Dev:</span> <span>{stats['std_dev']:.2f}</span></div>
        </div>
        '''
    
    # Generate CSV data URI
    csv_lines = [','.join(data[0].keys())]
    for row in data:
        csv_lines.append(','.join(str(row.get(col, '')) for col in data[0].keys()))
    csv_content = '\\n'.join(csv_lines)
    
    # Data table
    table_headers = "".join(f"<th>{col}</th>" for col in data[0].keys())
    table_rows = ""
    for i, row in enumerate(data):
        cells = "".join(f"<td>{row.get(col, '')}</td>" for col in data[0].keys())
        table_rows += f"<tr data-index='{i}'>{cells}</tr>"
    
    return f'''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Dataset Explorer</title>
    <style>
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}
        
        body {{
            font-family: 'Inter', 'Segoe UI', sans-serif;
            background: #0f1117;
            color: #e8eaf0;
            display: flex;
            height: 100vh;
        }}
        
        .sidebar {{
            width: 280px;
            background: #1a1d27;
            border-right: 1px solid #2a2d3a;
            padding: 20px;
            overflow-y: auto;
        }}
        
        .sidebar h2 {{
            font-size: 18px;
            margin-bottom: 16px;
            color: #6c63ff;
        }}
        
        .stat-box {{
            background: #0f1117;
            border: 1px solid #2a2d3a;
            border-radius: 8px;
            padding: 12px;
            margin-bottom: 12px;
        }}
        
        .stat-box h3 {{
            font-size: 14px;
            margin-bottom: 8px;
            color: #6c63ff;
        }}
        
        .stat-row {{
            display: flex;
            justify-content: space-between;
            font-size: 12px;
            padding: 4px 0;
            color: #9ca3af;
        }}
        
        .main-content {{
            flex: 1;
            display: flex;
            flex-direction: column;
            overflow: hidden;
        }}
        
        .toolbar {{
            background: #1a1d27;
            border-bottom: 1px solid #2a2d3a;
            padding: 16px 20px;
            display: flex;
            gap: 12px;
            align-items: center;
        }}
        
        .search-box {{
            flex: 1;
            padding: 10px 16px;
            background: #0f1117;
            border: 1px solid #2a2d3a;
            border-radius: 8px;
            color: #e8eaf0;
            font-size: 14px;
        }}
        
        .export-btn {{
            padding: 10px 20px;
            background: #6c63ff;
            color: white;
            border: none;
            border-radius: 8px;
            cursor: pointer;
            font-weight: 600;
            font-size: 14px;
        }}
        
        .export-btn:hover {{
            background: #5b52e5;
        }}
        
        .table-container {{
            flex: 1;
            overflow: auto;
            padding: 20px;
        }}
        
        table {{
            width: 100%;
            border-collapse: collapse;
            background: #1a1d27;
            border-radius: 12px;
            overflow: hidden;
        }}
        
        th {{
            background: #252836;
            padding: 14px;
            text-align: left;
            font-weight: 600;
            font-size: 13px;
            position: sticky;
            top: 0;
            z-index: 10;
            border-bottom: 2px solid #2a2d3a;
        }}
        
        td {{
            padding: 12px 14px;
            border-bottom: 1px solid #2a2d3a;
            font-size: 13px;
        }}
        
        tr:hover {{
            background: #252836;
        }}
        
        .pagination {{
            display: flex;
            justify-content: center;
            align-items: center;
            gap: 12px;
            padding: 16px;
            background: #1a1d27;
            border-top: 1px solid #2a2d3a;
        }}
        
        .page-btn {{
            padding: 8px 16px;
            background: #252836;
            border: 1px solid #2a2d3a;
            border-radius: 6px;
            color: #e8eaf0;
            cursor: pointer;
            font-size: 13px;
        }}
        
        .page-btn:hover {{
            background: #6c63ff;
        }}
        
        .page-info {{
            color: #9ca3af;
            font-size: 13px;
        }}
    </style>
</head>
<body>
    <div class="sidebar">
        <h2>Column Statistics</h2>
        {stats_sidebar_html}
    </div>
    
    <div class="main-content">
        <div class="toolbar">
            <input type="text" class="search-box" id="searchBox" placeholder="Search dataset..." 
                   onkeyup="searchTable()">
            <button class="export-btn" onclick="exportCSV()">Export CSV</button>
        </div>
        
        <div class="table-container">
            <table id="dataTable">
                <thead>
                    <tr>{table_headers}</tr>
                </thead>
                <tbody id="tableBody">
                    {table_rows}
                </tbody>
            </table>
        </div>
        
        <div class="pagination">
            <button class="page-btn" onclick="prevPage()">Previous</button>
            <span class="page-info" id="pageInfo">Page 1</span>
            <button class="page-btn" onclick="nextPage()">Next</button>
        </div>
    </div>
    
    <script>
        let currentPage = 1;
        const rowsPerPage = 50;
        const allRows = Array.from(document.querySelectorAll('#tableBody tr'));
        let filteredRows = allRows;
        
        function searchTable() {{
            const query = document.getElementById('searchBox').value.toLowerCase();
            filteredRows = allRows.filter(row => 
                row.textContent.toLowerCase().includes(query)
            );
            currentPage = 1;
            renderPage();
        }}
        
        function renderPage() {{
            const start = (currentPage - 1) * rowsPerPage;
            const end = start + rowsPerPage;
            
            allRows.forEach(row => row.style.display = 'none');
            filteredRows.slice(start, end).forEach(row => row.style.display = '');
            
            const totalPages = Math.ceil(filteredRows.length / rowsPerPage);
            document.getElementById('pageInfo').textContent = 
                `Page ${{currentPage}} of ${{totalPages}} (${{filteredRows.length}} rows)`;
        }}
        
        function nextPage() {{
            const totalPages = Math.ceil(filteredRows.length / rowsPerPage);
            if (currentPage < totalPages) {{
                currentPage++;
                renderPage();
            }}
        }}
        
        function prevPage() {{
            if (currentPage > 1) {{
                currentPage--;
                renderPage();
            }}
        }}
        
        function exportCSV() {{
            const csv = `{csv_content}`;
            const blob = new Blob([csv], {{ type: 'text/csv' }});
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = 'dataset.csv';
            a.click();
            URL.revokeObjectURL(url);
        }}
        
        renderPage();
    </script>
</body>
</html>'''


def generate_insights_report_html(data: List[Dict[str, Any]], col_types: Dict[str, str]) -> str:
    """Generate styled insights report"""
    
    if not data:
        return generate_empty_state_html()
    
    # Dataset summary
    row_count = len(data)
    col_count = len(col_types)
    numeric_cols = [col for col, typ in col_types.items() if typ == 'numeric']
    categorical_cols = [col for col, typ in col_types.items() if typ == 'categorical']
    time_cols = [col for col, typ in col_types.items() if typ == 'time']
    
    # Top findings
    insights = generate_insights(data, col_types)
    insights_html = "".join(f"<div class='finding'>{insight}</div>" for insight in insights)
    
    # Correlation matrix
    corr_matrix_html = ""
    if len(numeric_cols) >= 2:
        corr_matrix_html = "<h2>📊 Correlation Matrix</h2><table class='corr-matrix'><tr><th></th>"
        for col in numeric_cols[:5]:
            corr_matrix_html += f"<th>{col}</th>"
        corr_matrix_html += "</tr>"
        
        for col1 in numeric_cols[:5]:
            corr_matrix_html += f"<tr><th>{col1}</th>"
            vals1 = [row.get(col1) for row in data]
            for col2 in numeric_cols[:5]:
                vals2 = [row.get(col2) for row in data]
                corr = pearson_correlation(vals1, vals2)
                
                # Color code
                if abs(corr) > 0.7:
                    color_class = 'corr-high'
                elif abs(corr) > 0.4:
                    color_class = 'corr-medium'
                else:
                    color_class = 'corr-low'
                
                corr_matrix_html += f"<td class='{color_class}'>{corr:.2f}</td>"
            corr_matrix_html += "</tr>"
        corr_matrix_html += "</table>"
    
    # Suggested visualizations
    suggestions = []
    if time_cols and numeric_cols:
        suggestions.append("📈 Time series line chart to track trends")
    if categorical_cols and numeric_cols:
        suggestions.append("📊 Bar chart to compare categories")
    if len(numeric_cols) >= 2:
        suggestions.append("🔵 Scatter plot to explore relationships")
    if len(numeric_cols) >= 3:
        suggestions.append("🕸️ Radar chart for multi-dimensional comparison")
    
    suggestions_html = "".join(f"<li>{s}</li>" for s in suggestions)
    
    return f'''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Dataset Insights Report</title>
    <style>
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}
        
        body {{
            font-family: 'Inter', 'Segoe UI', sans-serif;
            background: #0f1117;
            color: #e8eaf0;
            padding: 40px 20px;
        }}
        
        .container {{
            max-width: 900px;
            margin: 0 auto;
        }}
        
        h1 {{
            font-size: 32px;
            margin-bottom: 24px;
            background: linear-gradient(135deg, #6c63ff 0%, #22c55e 100%);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            background-clip: text;
        }}
        
        .summary-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 16px;
            margin-bottom: 32px;
        }}
        
        .summary-card {{
            background: #1a1d27;
            border: 1px solid #2a2d3a;
            border-radius: 12px;
            padding: 20px;
            text-align: center;
        }}
        
        .summary-value {{
            font-size: 36px;
            font-weight: 700;
            color: #6c63ff;
            margin-bottom: 8px;
        }}
        
        .summary-label {{
            font-size: 14px;
            color: #9ca3af;
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }}
        
        .section {{
            background: #1a1d27;
            border: 1px solid #2a2d3a;
            border-radius: 12px;
            padding: 24px;
            margin-bottom: 20px;
        }}
        
        h2 {{
            font-size: 20px;
            margin-bottom: 16px;
            color: #6c63ff;
        }}
        
        .finding {{
            padding: 12px 16px;
            background: #0f1117;
            border-left: 4px solid #6c63ff;
            border-radius: 6px;
            margin-bottom: 10px;
            line-height: 1.6;
        }}
        
        .corr-matrix {{
            width: 100%;
            border-collapse: collapse;
            margin-top: 16px;
        }}
        
        .corr-matrix th {{
            background: #252836;
            padding: 12px;
            font-weight: 600;
            font-size: 12px;
            border: 1px solid #2a2d3a;
        }}
        
        .corr-matrix td {{
            padding: 12px;
            text-align: center;
            font-weight: 600;
            border: 1px solid #2a2d3a;
        }}
        
        .corr-high {{
            background: #22c55e;
            color: white;
        }}
        
        .corr-medium {{
            background: #f59e0b;
            color: white;
        }}
        
        .corr-low {{
            background: #252836;
            color: #9ca3af;
        }}
        
        ul {{
            list-style: none;
            padding: 0;
        }}
        
        li {{
            padding: 10px 16px;
            background: #0f1117;
            border-radius: 6px;
            margin-bottom: 8px;
            border-left: 3px solid #6c63ff;
        }}
    </style>
</head>
<body>
    <div class="container">
        <h1>📊 Dataset Insights Report</h1>
        
        <div class="summary-grid">
            <div class="summary-card">
                <div class="summary-value">{row_count}</div>
                <div class="summary-label">Total Rows</div>
            </div>
            <div class="summary-card">
                <div class="summary-value">{col_count}</div>
                <div class="summary-label">Total Columns</div>
            </div>
            <div class="summary-card">
                <div class="summary-value">{len(numeric_cols)}</div>
                <div class="summary-label">Numeric Columns</div>
            </div>
            <div class="summary-card">
                <div class="summary-value">{len(categorical_cols)}</div>
                <div class="summary-label">Categorical</div>
            </div>
        </div>
        
        <div class="section">
            <h2>🔍 Top Statistical Findings</h2>
            {insights_html}
        </div>
        
        <div class="section">
            {corr_matrix_html}
        </div>
        
        <div class="section">
            <h2>💡 Suggested Visualizations</h2>
            <ul>
                {suggestions_html}
            </ul>
        </div>
    </div>
</body>
</html>'''


def generate_error_html(message: str) -> str:
    """Generate error page"""
    return f'''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Error</title>
    <style>
        body {{
            font-family: 'Inter', 'Segoe UI', sans-serif;
            background: #0f1117;
            color: #e8eaf0;
            display: flex;
            align-items: center;
            justify-content: center;
            min-height: 100vh;
            padding: 20px;
        }}
        .error-card {{
            background: #1a1d27;
            border: 2px solid #ef4444;
            border-radius: 12px;
            padding: 32px;
            max-width: 600px;
            text-align: center;
        }}
        h1 {{
            color: #ef4444;
            font-size: 24px;
            margin-bottom: 16px;
        }}
        p {{
            color: #9ca3af;
            line-height: 1.6;
            margin-bottom: 20px;
        }}
        .hint {{
            background: #0f1117;
            border-left: 4px solid #f59e0b;
            padding: 16px;
            text-align: left;
            border-radius: 6px;
        }}
        .hint strong {{
            color: #f59e0b;
        }}
    </style>
</head>
<body>
    <div class="error-card">
        <h1>⚠️ Error</h1>
        <p>{message}</p>
        <div class="hint">
            <strong>Example format:</strong><br>
            [{{"name": "Item1", "value": 100}}, {{"name": "Item2", "value": 200}}]
        </div>
    </div>
</body>
</html>'''


def generate_empty_state_html() -> str:
    """Generate empty state page"""
    return f'''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>No Data</title>
    <style>
        body {{
            font-family: 'Inter', 'Segoe UI', sans-serif;
            background: #0f1117;
            color: #e8eaf0;
            display: flex;
            align-items: center;
            justify-content: center;
            min-height: 100vh;
            padding: 20px;
        }}
        .empty-card {{
            background: #1a1d27;
            border: 1px solid #2a2d3a;
            border-radius: 12px;
            padding: 48px;
            max-width: 500px;
            text-align: center;
        }}
        h1 {{
            font-size: 48px;
            margin-bottom: 16px;
        }}
        p {{
            color: #9ca3af;
            font-size: 18px;
        }}
    </style>
</head>
<body>
    <div class="empty-card">
        <h1>📭</h1>
        <p>No data to display</p>
    </div>
</body>
</html>'''


# ============================================================================
# MCP RESOURCE HANDLERS (for UI)
# ============================================================================

@app.list_resources()
async def list_resources() -> list[Resource]:
    """List available UI resources"""
    return [
        Resource(
            uri="ui://data-analysis/dashboard",
            name="Dashboard UI",
            mimeType="text/html;profile=mcp-app",
            description="Interactive dashboard with charts, statistics, and insights"
        ),
        Resource(
            uri="ui://data-analysis/explorer",
            name="Data Explorer UI",
            mimeType="text/html;profile=mcp-app",
            description="Paginated searchable data table with statistics"
        ),
        Resource(
            uri="ui://data-analysis/insights",
            name="Insights Report UI",
            mimeType="text/html;profile=mcp-app",
            description="Statistical insights report with correlations"
        )
    ]


@app.read_resource()
async def read_resource(uri: str) -> str:
    """Serve UI content for analysis results"""
    
    # Extract analysis ID from cache (use latest if not specified)
    analysis_id = "latest"
    
    if analysis_id not in analysis_cache:
        return generate_empty_state_html()
    
    cached_data = analysis_cache[analysis_id]
    data = cached_data["data"]
    col_types = cached_data["col_types"]
    
    if uri == "ui://data-analysis/dashboard":
        return generate_dashboard_html(data, col_types)
    elif uri == "ui://data-analysis/explorer":
        return generate_data_table_html(data, col_types)
    elif uri == "ui://data-analysis/insights":
        return generate_insights_report_html(data, col_types)
    else:
        return generate_error_html(f"Unknown resource: {uri}")


# ============================================================================
# MCP TOOL HANDLERS
# ============================================================================

@app.list_tools()
async def list_tools() -> list[Tool]:
    """List available MCP tools"""
    return [
        Tool(
            name="visualize_dataset",
            description="Analyze dataset and return interactive dashboard. Set return_html=false to get JSON metadata with UI resource link for MCP Apps pattern, or use the default HTML response for backwards compatibility.",
            inputSchema={
                "type": "object",
                "properties": {
                    "dataset": {
                        "type": ["string", "array"],
                        "description": "Dataset as JSON array string, CSV text, or Python list. Example: [{'month':'Jan','revenue':120000},{'month':'Feb','revenue':145000}]"
                    },
                    "return_html": {
                        "type": "boolean",
                        "description": "If true, returns interactive HTML directly. If false, returns JSON metadata with UI resource link (default: true for backwards compatibility)",
                        "default": True
                    }
                },
                "required": ["dataset"]
            },
            _meta={
                "ui": {
                    "resourceUri": "ui://data-analysis/dashboard"
                }
            }
        ),
        Tool(
            name="explore_dataset",
            description="Explore dataset in an interactive table. Set return_html=false to get JSON metadata with UI resource link for MCP Apps pattern, or use the default HTML response for backwards compatibility.",
            inputSchema={
                "type": "object",
                "properties": {
                    "dataset": {
                        "type": ["string", "array"],
                        "description": "Dataset as JSON array string, CSV text, or Python list"
                    },
                    "return_html": {
                        "type": "boolean",
                        "description": "If true, returns interactive HTML directly. If false, returns JSON metadata with UI resource link (default: true for backwards compatibility)",
                        "default": True
                    }
                },
                "required": ["dataset"]
            },
            _meta={
                "ui": {
                    "resourceUri": "ui://data-analysis/explorer"
                }
            }
        ),
        Tool(
            name="get_insights",
            description="Get statistical insights report. Set return_html=false to get JSON metadata with UI resource link for MCP Apps pattern, or use the default HTML response for backwards compatibility.",
            inputSchema={
                "type": "object",
                "properties": {
                    "dataset": {
                        "type": ["string", "array"],
                        "description": "Dataset as JSON array string, CSV text, or Python list"
                    },
                    "return_html": {
                        "type": "boolean",
                        "description": "If true, returns interactive HTML directly. If false, returns JSON metadata with UI resource link (default: true for backwards compatibility)",
                        "default": True
                    }
                },
                "required": ["dataset"]
            },
            _meta={
                "ui": {
                    "resourceUri": "ui://data-analysis/insights"
                }
            }
        )
    ]


@app.call_tool()
async def call_tool(name: str, arguments: Any) -> list[TextContent]:
    """Handle tool execution - returns structured data or HTML based on return_html parameter"""
    
    try:
        dataset_input = arguments.get("dataset")
        return_html = arguments.get("return_html", True)  # Default True for backwards compatibility
        
        # Parse dataset
        data = parse_dataset(dataset_input)
        
        if not data:
            return [TextContent(
                type="text",
                text="Failed to parse dataset. Please provide valid JSON array or CSV text."
            )]
        
        # Classify columns
        col_types = classify_columns(data)
        
        # Cache analysis for UI resource
        analysis_id = "latest"
        analysis_cache[analysis_id] = {
            "data": data,
            "col_types": col_types,
            "timestamp": datetime.now().isoformat()
        }
        
        # If return_html is True, return HTML directly (legacy/backwards compatible mode)
        if return_html:
            if name == "visualize_dataset":
                html = generate_dashboard_html(data, col_types)
            elif name == "explore_dataset":
                html = generate_data_table_html(data, col_types)
            elif name == "get_insights":
                html = generate_insights_report_html(data, col_types)
            else:
                html = generate_error_html(f"Unknown tool: {name}")
            
            return [TextContent(
                type="text",
                text=html
            )]
        
        # Default: Return JSON metadata (MCP Apps pattern)
        # Generate summary statistics
        row_count = len(data)
        col_count = len(col_types)
        numeric_cols = [col for col, typ in col_types.items() if typ == 'numeric']
        categorical_cols = [col for col, typ in col_types.items() if typ == 'categorical']
        time_cols = [col for col, typ in col_types.items() if typ == 'time']
        
        # Return structured data (not HTML)
        result = {
            "status": "success",
            "tool": name,
            "summary": {
                "rows": row_count,
                "columns": col_count,
                "numeric_columns": len(numeric_cols),
                "categorical_columns": len(categorical_cols),
                "time_columns": len(time_cols)
            },
            "column_types": col_types,
            "ui_resource": f"ui://data-analysis/{name.replace('_dataset', '').replace('get_', '')}"
        }
        
        if numeric_cols:
            # Add quick stats for first numeric column
            col = numeric_cols[0]
            values = [row.get(col) for row in data if row.get(col) is not None]
            stats = compute_stats(values)
            result["sample_stats"] = {col: stats}
        
        # Get insights
        insights = generate_insights(data, col_types)
        if insights:
            result["key_insights"] = insights[:3]  # Top 3 insights
        
        return [TextContent(
            type="text",
            text=json.dumps(result, indent=2)
        )]
        
    except Exception as e:
        return [TextContent(
            type="text",
            text=json.dumps({
                "status": "error",
                "error": str(e),
                "tool": name
            }, indent=2)
        )]


# ============================================================================
# ENTRY POINT
# ============================================================================

async def main_stdio():
    """Run the MCP server in stdio mode"""
    async with mcp.server.stdio.stdio_server() as (read_stream, write_stream):
        await app.run(
            read_stream,
            write_stream,
            app.create_initialization_options()
        )


async def main_http(port: int):
    """Run the MCP server in HTTP mode"""
    from mcp.server.sse import SseServerTransport
    from starlette.applications import Starlette
    from starlette.routing import Route
    from starlette.responses import Response
    import uvicorn
    
    sse = SseServerTransport("/messages")
    
    async def handle_sse(request):
        async with sse.connect_sse(
            request.scope,
            request.receive,
            request._send,
        ) as streams:
            await app.run(
                streams[0],
                streams[1],
                app.create_initialization_options(),
            )
        return Response()
    
    async def handle_messages(request):
        await sse.handle_post_message(request.scope, request.receive, request._send)
        return Response()
    
    starlette_app = Starlette(
        routes=[
            Route("/sse", endpoint=handle_sse),
            Route("/messages", endpoint=handle_messages, methods=["POST"]),
        ]
    )
    
    print(f"🚀 Data Analysis MCP Server running on http://localhost:{port}")
    print(f"   SSE endpoint: http://localhost:{port}/sse")
    print(f"   Messages endpoint: http://localhost:{port}/messages")
    
    config = uvicorn.Config(starlette_app, host="0.0.0.0", port=port, log_level="info")
    server = uvicorn.Server(config)
    await server.serve()


async def main():
    """Main entry point - parse args and run appropriate mode"""
    parser = argparse.ArgumentParser(description="Data Analysis MCP Server")
    parser.add_argument("--http", action="store_true", help="Run in HTTP mode")
    parser.add_argument("--port", type=int, default=8080, help="Port for HTTP mode (default: 8080)")
    
    args = parser.parse_args()
    
    if args.http:
        await main_http(args.port)
    else:
        await main_stdio()


if __name__ == "__main__":
    asyncio.run(main())
