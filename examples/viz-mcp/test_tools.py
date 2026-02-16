#!/usr/bin/env python3
"""
Quick test script to verify viz-mcp tools
"""

import asyncio
import json
from server import list_tools, call_tool

async def test_tools():
    print("=" * 60)
    print("Testing Visualization MCP Server")
    print("=" * 60)

    # Test 1: List all tools
    print("\n1. Testing list_tools()...")
    tools = await list_tools()
    print(f"✅ Found {len(tools)} tools:")
    for tool in tools:
        print(f"   • {tool.name}: {tool.description[:60]}...")

    # Test 2: Create a simple Mermaid flowchart
    print("\n2. Testing generate_flowchart()...")
    mermaid_result = await call_tool(
        "generate_flowchart",
        {
            "diagram_type": "flowchart",
            "mermaid_code": "graph TD\n    A[Start] --> B[End]",
            "title": "Simple Test Flow"
        }
    )
    print(f"✅ Flowchart generated: {len(mermaid_result[0].text)} chars")

    # Test 3: Create a Chart.js bar chart
    print("\n3. Testing create_chart()...")
    chart_result = await call_tool(
        "create_chart",
        {
            "chart_type": "bar",
            "data": {
                "labels": ["A", "B", "C"],
                "datasets": [{
                    "label": "Test Data",
                    "data": [10, 20, 30]
                }]
            },
            "title": "Test Bar Chart"
        }
    )
    print(f"✅ Chart created: {len(chart_result[0].text)} chars")

    # Test 4: Create an Excalidraw diagram
    print("\n4. Testing create_diagram()...")
    diagram_result = await call_tool(
        "create_diagram",
        {
            "diagram_id": "test-diagram"
        }
    )
    print(f"✅ Diagram created: {len(diagram_result[0].text)} chars")

    # Test 5: List diagrams
    print("\n5. Testing list_diagrams()...")
    list_result = await call_tool("list_diagrams", {})
    print(f"✅ Diagram list retrieved")

    # Test 6: Create a Plotly scatter plot
    print("\n6. Testing create_plot()...")
    plot_result = await call_tool(
        "create_plot",
        {
            "plot_type": "scatter",
            "data": [{
                "x": [1, 2, 3],
                "y": [4, 5, 6],
                "type": "scatter",
                "mode": "markers"
            }],
            "layout": {"title": "Test Plot"},
            "title": "Test Scatter Plot"
        }
    )
    print(f"✅ Plot created: {len(plot_result[0].text)} chars")

    # Test 7: Create an ECharts dashboard
    print("\n7. Testing create_dashboard()...")
    dashboard_result = await call_tool(
        "create_dashboard",
        {
            "dashboard_type": "pie",
            "option": {
                "series": [{
                    "type": "pie",
                    "data": [
                        {"value": 40, "name": "A"},
                        {"value": 30, "name": "B"},
                        {"value": 30, "name": "C"}
                    ]
                }]
            },
            "title": "Test Dashboard"
        }
    )
    print(f"✅ Dashboard created: {len(dashboard_result[0].text)} chars")

    print("\n" + "=" * 60)
    print("✅ All 7 tools tested successfully!")
    print("=" * 60)

if __name__ == "__main__":
    asyncio.run(test_tools())
