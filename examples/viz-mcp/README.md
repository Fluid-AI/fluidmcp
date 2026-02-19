# Visualization MCP Server

Interactive visualization and diagram editing MCP server with support for multiple visualization libraries.

## Features

### 🎨 Excalidraw Integration
- **Interactive diagram editor** with hand-drawn style
- Create flowcharts, wireframes, system architecture diagrams
- Real-time editing with full drawing toolkit
- Export to PNG, SVG, and JSON formats
- Persistent storage for saved diagrams

### 📊 Mermaid.js Diagrams
- Code-generated flowcharts and diagrams
- Support for: flowcharts, sequence diagrams, class diagrams, state diagrams, ER diagrams, Gantt charts, pie charts, user journey maps
- Clean, professional styling
- Export to SVG and PNG

### 📈 Chart.js Visualizations
- Simple, elegant charts for common use cases
- Chart types: bar, line, pie, doughnut, radar, polar area, bubble
- Responsive and animated
- Export to PNG and JSON data

### 🔬 Plotly Advanced Plots
- Scientific and advanced visualizations
- Support for: 3D plots, heatmaps, contour plots, surface plots, box plots, violin plots
- Highly interactive with zoom, pan, and hover
- Export to PNG, SVG, and HTML

### 📊 ECharts Dashboards
- Professional business intelligence dashboards
- Support for: line, bar, pie, gauge, funnel, treemap, sunburst, graph, sankey
- Complex multi-chart compositions
- Geographic map support
- Export to PNG and SVG

## Tools

### 1. create_diagram
Create an interactive Excalidraw diagram.

**Parameters:**
- `diagram_id` (string, required): Unique identifier for the diagram
- `initial_elements` (array, optional): Pre-populate canvas with elements

**Example:**
```json
{
  "diagram_id": "auth-flow",
  "initial_elements": []
}
```

**Returns:** Self-contained HTML with interactive Excalidraw canvas

### 2. load_diagram
Load a previously saved Excalidraw diagram.

**Parameters:**
- `diagram_id` (string, required): ID of diagram to load

**Example:**
```json
{
  "diagram_id": "auth-flow"
}
```

### 3. list_diagrams
List all saved diagrams with metadata.

**Returns:** List of saved diagrams with creation date, type, and element count

### 4. generate_flowchart
Generate a Mermaid.js diagram.

**Parameters:**
- `diagram_type` (string, required): One of: flowchart, sequence, class, state, er, gantt, pie, journey
- `mermaid_code` (string, required): Mermaid syntax code
- `title` (string, optional): Diagram title

**Example:**
```json
{
  "diagram_type": "flowchart",
  "mermaid_code": "graph TD\n    A[Start] --> B{Decision}\n    B -->|Yes| C[Action 1]\n    B -->|No| D[Action 2]\n    C --> E[End]\n    D --> E",
  "title": "Sample Process Flow"
}
```

**Mermaid Syntax Examples:**

**Flowchart:**
```
graph TD
    A[Christmas] -->|Get money| B(Go shopping)
    B --> C{Let me think}
    C -->|One| D[Laptop]
    C -->|Two| E[iPhone]
```

**Sequence Diagram:**
```
sequenceDiagram
    participant User
    participant App
    participant API
    User->>App: Login Request
    App->>API: Authenticate
    API-->>App: Token
    App-->>User: Success
```

**Class Diagram:**
```
classDiagram
    class Animal {
        +String name
        +int age
        +makeSound()
    }
    class Dog {
        +String breed
        +bark()
    }
    Animal <|-- Dog
```

### 5. create_chart
Create a Chart.js visualization.

**Parameters:**
- `chart_type` (string, required): One of: bar, line, pie, doughnut, radar, polarArea, bubble
- `data` (object, required): Chart.js data object with labels and datasets
- `options` (object, optional): Chart.js customization options
- `title` (string, required): Chart title

**Example (Bar Chart):**
```json
{
  "chart_type": "bar",
  "data": {
    "labels": ["Q1", "Q2", "Q3", "Q4"],
    "datasets": [{
      "label": "Revenue",
      "data": [12000, 19000, 15000, 22000],
      "backgroundColor": "rgba(75, 192, 192, 0.6)",
      "borderColor": "rgba(75, 192, 192, 1)",
      "borderWidth": 1
    }]
  },
  "options": {
    "scales": {
      "y": {
        "beginAtZero": true
      }
    }
  },
  "title": "Quarterly Revenue"
}
```

**Example (Pie Chart):**
```json
{
  "chart_type": "pie",
  "data": {
    "labels": ["Chrome", "Firefox", "Safari", "Edge"],
    "datasets": [{
      "data": [60, 20, 15, 5],
      "backgroundColor": [
        "rgba(255, 99, 132, 0.8)",
        "rgba(54, 162, 235, 0.8)",
        "rgba(255, 206, 86, 0.8)",
        "rgba(75, 192, 192, 0.8)"
      ]
    }]
  },
  "title": "Browser Market Share"
}
```

### 6. create_plot
Create a Plotly visualization.

**Parameters:**
- `plot_type` (string, required): One of: scatter, line, bar, heatmap, surface, 3d_scatter, contour, box, violin
- `data` (array, required): Array of Plotly trace objects
- `layout` (object, optional): Plotly layout configuration
- `title` (string, required): Plot title

**Example (3D Scatter Plot):**
```json
{
  "plot_type": "3d_scatter",
  "data": [{
    "type": "scatter3d",
    "mode": "markers",
    "x": [1, 2, 3, 4, 5],
    "y": [1, 4, 9, 16, 25],
    "z": [1, 8, 27, 64, 125],
    "marker": {
      "size": 12,
      "color": "rgb(255, 127, 14)"
    }
  }],
  "layout": {
    "scene": {
      "xaxis": {"title": "X Axis"},
      "yaxis": {"title": "Y Axis"},
      "zaxis": {"title": "Z Axis"}
    }
  },
  "title": "3D Data Visualization"
}
```

**Example (Heatmap):**
```json
{
  "plot_type": "heatmap",
  "data": [{
    "type": "heatmap",
    "z": [[1, 20, 30], [20, 1, 60], [30, 60, 1]],
    "colorscale": "Viridis"
  }],
  "layout": {
    "xaxis": {"title": "X Axis"},
    "yaxis": {"title": "Y Axis"}
  },
  "title": "Correlation Heatmap"
}
```

### 7. create_dashboard
Create an ECharts dashboard.

**Parameters:**
- `dashboard_type` (string, required): One of: line, bar, pie, gauge, funnel, treemap, sunburst, graph, sankey
- `option` (object, required): ECharts option configuration
- `title` (string, required): Dashboard title

**Example (Gauge Dashboard):**
```json
{
  "dashboard_type": "gauge",
  "option": {
    "series": [{
      "type": "gauge",
      "startAngle": 180,
      "endAngle": 0,
      "min": 0,
      "max": 100,
      "splitNumber": 8,
      "axisLine": {
        "lineStyle": {
          "width": 6,
          "color": [
            [0.25, "#FF6E76"],
            [0.5, "#FDDD60"],
            [0.75, "#58D9F9"],
            [1, "#7CFFB2"]
          ]
        }
      },
      "pointer": {
        "icon": "path://M12.8,0.7l12,40.1H0.7L12.8,0.7z",
        "length": "12%",
        "width": 20
      },
      "detail": {
        "fontSize": 30,
        "offsetCenter": [0, "70%"],
        "valueAnimation": true,
        "formatter": "{value}%"
      },
      "data": [{"value": 75, "name": "Completion"}]
    }]
  },
  "title": "Project Completion Dashboard"
}
```

**Example (Sankey Diagram):**
```json
{
  "dashboard_type": "sankey",
  "option": {
    "series": {
      "type": "sankey",
      "layout": "none",
      "data": [
        {"name": "Source A"},
        {"name": "Source B"},
        {"name": "Process"},
        {"name": "Output"}
      ],
      "links": [
        {"source": "Source A", "target": "Process", "value": 5},
        {"source": "Source B", "target": "Process", "value": 3},
        {"source": "Process", "target": "Output", "value": 8}
      ]
    }
  },
  "title": "Data Flow Analysis"
}
```

## Installation

### Option 1: Run directly with FluidMCP

```bash
fluidmcp run examples/viz-mcp-config.json --file --start-server
```

### Option 2: Add to your FluidMCP configuration

Add to your config.json:

```json
{
  "mcpServers": {
    "viz-mcp": {
      "command": "python3",
      "args": [
        "/path/to/viz-mcp/server.py"
      ],
      "env": {}
    }
  }
}
```

## Usage

1. Start the MCP server using FluidMCP
2. Access via HTTP at `http://localhost:8099/viz-mcp/mcp`
3. Call tools using MCP protocol
4. Receive self-contained HTML responses
5. Save HTML files and open in browser
6. Interact with visualizations and export as needed

## Example Workflow

### Creating a Flowchart with Excalidraw

```bash
# 1. Call create_diagram tool
POST http://localhost:8099/viz-mcp/mcp
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "tools/call",
  "params": {
    "name": "create_diagram",
    "arguments": {
      "diagram_id": "my-flowchart"
    }
  }
}

# 2. Save returned HTML to file
# 3. Open in browser
# 4. Draw your diagram
# 5. Use export buttons to save as PNG/SVG
```

### Creating a Chart

```bash
# Call create_chart tool
POST http://localhost:8099/viz-mcp/mcp
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "tools/call",
  "params": {
    "name": "create_chart",
    "arguments": {
      "chart_type": "line",
      "data": {
        "labels": ["Jan", "Feb", "Mar", "Apr"],
        "datasets": [{
          "label": "Sales",
          "data": [65, 59, 80, 81],
          "borderColor": "rgb(75, 192, 192)",
          "tension": 0.1
        }]
      },
      "title": "Monthly Sales"
    }
  }
}
```

## Storage

All saved diagrams are stored in: `~/.viz-mcp/diagrams/`

Each diagram has:
- `.meta.json` - Metadata (ID, creation date, type, element count)
- The HTML is generated on-demand when loading

## Architecture

### File Structure
```
viz-mcp/
├── server.py           # Main MCP server with all tools
├── metadata.json       # Package metadata for FluidMCP
└── README.md          # This file
```

### Key Features
- **Self-contained HTML outputs** - No external dependencies for users
- **CDN-based libraries** - No build step required
- **File locking** - Thread-safe storage operations
- **MCP Prompts Resource** - Agent instructions for best practices
- **Export capabilities** - Multiple formats (PNG, SVG, JSON, HTML)

## Libraries Used

All libraries are loaded via CDN (no installation required):

- **Excalidraw**: v0.17.0 - Interactive whiteboard
- **Mermaid.js**: v10.6.1 - Diagram generation
- **Chart.js**: v4.4.0 - Simple charts
- **Plotly**: v2.27.0 - Advanced plotting
- **ECharts**: v5.4.3 - Professional dashboards

## Tips

### Choosing the Right Tool

- **Simple flowchart/diagram you want to draw?** → Use `create_diagram` (Excalidraw)
- **Code-generated flowchart/diagram?** → Use `generate_flowchart` (Mermaid)
- **Simple bar/line/pie chart?** → Use `create_chart` (Chart.js)
- **3D plot or scientific visualization?** → Use `create_plot` (Plotly)
- **Professional dashboard or complex viz?** → Use `create_dashboard` (ECharts)

### Best Practices

1. **Start simple** - Use basic chart types first
2. **Test with sample data** - Verify structure before using real data
3. **Use descriptive titles** - Make visualizations self-explanatory
4. **Export early** - Save your work frequently
5. **Leverage interactivity** - All visualizations support zoom, pan, hover

## Troubleshooting

**Problem:** HTML file doesn't display properly
**Solution:** Ensure you saved the complete HTML content, including opening `<!DOCTYPE html>` tag

**Problem:** Excalidraw not loading
**Solution:** Check browser console for errors. CDN scripts may be blocked by firewall/proxy

**Problem:** Diagram not saving
**Solution:** Check `~/.viz-mcp/diagrams/` directory exists and has write permissions

## License

MIT License - Free to use and modify
