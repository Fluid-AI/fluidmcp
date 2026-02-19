#!/usr/bin/env python3
"""
Visualization MCP Server
Provides interactive visualizations and diagram editing capabilities
"""

import os
import json
import asyncio
import fcntl
from datetime import datetime
from pathlib import Path
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import (
    Tool,
    TextContent,
    Prompt,
    PromptMessage,
    GetPromptResult,
    INVALID_PARAMS,
    INTERNAL_ERROR
)

# Initialize MCP server
app = Server("viz-mcp")

# Storage configuration
STORAGE_DIR = Path.home() / ".viz-mcp" / "diagrams"
STORAGE_DIR.mkdir(parents=True, exist_ok=True)

# File locking utilities
def safe_write_json(file_path: Path, data: dict):
    """Safely write JSON with file locking"""
    file_path.parent.mkdir(parents=True, exist_ok=True)

    with open(file_path, 'w') as f:
        fcntl.flock(f.fileno(), fcntl.LOCK_EX)
        try:
            json.dump(data, f, indent=2)
            f.flush()
            os.fsync(f.fileno())
        finally:
            fcntl.flock(f.fileno(), fcntl.LOCK_UN)

def safe_read_json(file_path: Path) -> dict:
    """Safely read JSON with file locking"""
    if not file_path.exists():
        return {}

    with open(file_path, 'r') as f:
        fcntl.flock(f.fileno(), fcntl.LOCK_SH)
        try:
            return json.load(f)
        finally:
            fcntl.flock(f.fileno(), fcntl.LOCK_UN)

# HTML Template Generators
def generate_excalidraw_html(diagram_id: str, initial_data: dict = None, elements_list: list = None, connections_list: list = None) -> str:
    """Generate self-contained SVG diagram designer HTML (no React, pure JavaScript)"""
    title = diagram_id.replace('-', ' ').replace('_', ' ').title()

    # Calculate canvas size based on element count
    num_elements = len(elements_list) if elements_list else 5

    # Fixed canvas height tiers based on element count
    if num_elements <= 5:
        canvas_height = 650
    elif num_elements <= 10:
        canvas_height = 900
    elif num_elements <= 15:
        canvas_height = 1200
    elif num_elements <= 20:
        canvas_height = 1500
    else:
        canvas_height = 2000

    # Calculate canvas width based on max X position
    canvas_width = 1400  # Default width
    if elements_list and len(elements_list) > 0:
        max_x = 0
        for elem in elements_list:
            elem_right = elem.get('x', 100) + elem.get('width', 180)
            max_x = max(max_x, elem_right)
        canvas_width = max(1400, max_x + 300)  # Add padding

    # Normalize Y positions to spread elements across available canvas height
    if elements_list and len(elements_list) > 0:
        # Find original min and max Y positions
        min_y = min(elem.get('y', 100) for elem in elements_list)
        max_y = max(elem.get('y', 100) + elem.get('height', 80) for elem in elements_list)
        original_height = max_y - min_y

        # Available height (with padding)
        available_height = canvas_height - 160  # Top and bottom padding

        # Scale factor to spread elements
        if original_height > 0:
            scale_factor = available_height / original_height
        else:
            scale_factor = 1.0

        # Convert elements list to JavaScript format with normalized Y positions
        elements_js = "[\n"
        for i, elem in enumerate(elements_list):
            elem_id = f"element{i+1}"
            text = elem.get('text', 'Element')
            x = elem.get('x', 100 + (i % 3) * 300)
            original_y = elem.get('y', 100 + (i // 3) * 200)

            # Normalize Y position to spread across canvas
            normalized_y = 80 + ((original_y - min_y) * scale_factor)
            y = int(normalized_y)

            width = elem.get('width', 180)
            height = elem.get('height', 80)
            shape = elem.get('shape', 'rounded-rect')
            fillColor = elem.get('fillColor', '#a5d8ff')
            strokeColor = elem.get('strokeColor', '#1971c2')
            textColor = elem.get('textColor', '#000000')

            elements_js += f'        {{ id: "{elem_id}", x: {x}, y: {y}, width: {width}, height: {height}, shape: "{shape}", fillColor: "{fillColor}", strokeColor: "{strokeColor}", textColor: "{textColor}", text: "{text}" }}'
            if i < len(elements_list) - 1:
                elements_js += ","
            elements_js += "\n"
        elements_js += "      ]"
    else:
        # Default microservices architecture
        elements_js = """[
        { id: "element1", x: 450, y: 80, width: 200, height: 80, shape: "rounded-rect", fillColor: "#a5d8ff", strokeColor: "#1971c2", textColor: "#000000", text: "API Gateway" },
        { id: "element2", x: 150, y: 250, width: 180, height: 80, shape: "rounded-rect", fillColor: "#b2f2bb", strokeColor: "#2f9e44", textColor: "#000000", text: "User Service" },
        { id: "element3", x: 460, y: 250, width: 180, height: 80, shape: "rounded-rect", fillColor: "#ffec99", strokeColor: "#f59f00", textColor: "#000000", text: "Order Service" },
        { id: "element4", x: 770, y: 250, width: 180, height: 80, shape: "rounded-rect", fillColor: "#ffc9c9", strokeColor: "#e03131", textColor: "#000000", text: "Payment Service" },
        { id: "element5", x: 500, y: 450, width: 150, height: 100, shape: "ellipse", fillColor: "#d0bfff", strokeColor: "#5f3dc4", textColor: "#000000", text: "Database" }
      ]"""

    # Convert connections list to JavaScript format
    if connections_list and len(connections_list) > 0:
        connections_js = "[\n"
        for i, conn in enumerate(connections_list):
            from_id = conn.get('fromId', 'element1')
            from_point = conn.get('fromPoint', 'bottom')
            to_id = conn.get('toId', 'element2')
            to_point = conn.get('toPoint', 'top')

            connections_js += f'        createInitialConnection("{from_id}", "{from_point}", "{to_id}", "{to_point}")'
            if i < len(connections_list) - 1:
                connections_js += ","
            connections_js += "\n"
        connections_js += "      ]"
    else:
        # Default connections
        connections_js = """[
        createInitialConnection("element1", "bottom", "element2", "top"),
        createInitialConnection("element1", "bottom", "element3", "top"),
        createInitialConnection("element1", "bottom", "element4", "top"),
        createInitialConnection("element2", "bottom", "element5", "left"),
        createInitialConnection("element3", "bottom", "element5", "top"),
        createInitialConnection("element4", "bottom", "element5", "right")
      ]"""

    return f"""<!doctype html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>{title} - Advanced Diagram Designer</title>
    <style>
      * {{
        margin: 0;
        padding: 0;
        box-sizing: border-box;
      }}

      body {{
        font-family:
          -apple-system, BlinkMacSystemFont, "Segoe UI", "Roboto", sans-serif;
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        display: flex;
        justify-content: center;
        align-items: center;
        min-height: 100vh;
        padding: 20px;
      }}

      .container {{
        background: white;
        border-radius: 20px;
        box-shadow: 0 20px 60px rgba(0, 0, 0, 0.3);
        padding: 25px;
        max-width: {canvas_width + 100}px;
        width: 100%;
      }}

      h1 {{
        text-align: center;
        color: #333;
        margin-bottom: 20px;
        font-size: 26px;
      }}

      .toolbar {{
        background: #f8f9fa;
        border-radius: 10px;
        padding: 15px;
        margin-bottom: 15px;
        display: flex;
        flex-wrap: wrap;
        gap: 10px;
        align-items: center;
        border: 2px solid #e9ecef;
      }}

      .toolbar-section {{
        display: flex;
        gap: 8px;
        align-items: center;
        padding: 5px 10px;
        border-right: 2px solid #dee2e6;
      }}

      .toolbar-section:last-child {{
        border-right: none;
      }}

      .toolbar-label {{
        font-size: 12px;
        font-weight: 600;
        color: #495057;
        margin-right: 5px;
      }}

      .tool-btn {{
        padding: 8px 16px;
        border: 2px solid #dee2e6;
        background: white;
        border-radius: 6px;
        cursor: pointer;
        font-size: 13px;
        font-weight: 500;
        transition: all 0.2s;
        display: flex;
        align-items: center;
        gap: 5px;
      }}

      .tool-btn:hover {{
        background: #e9ecef;
        border-color: #adb5bd;
        transform: translateY(-1px);
      }}

      .tool-btn.active {{
        background: #4c6ef5;
        color: white;
        border-color: #4c6ef5;
      }}

      .color-picker {{
        width: 40px;
        height: 35px;
        border: 2px solid #dee2e6;
        border-radius: 6px;
        cursor: pointer;
      }}

      input[type="text"],
      input[type="number"],
      select {{
        padding: 6px 10px;
        border: 2px solid #dee2e6;
        border-radius: 6px;
        font-size: 13px;
        outline: none;
      }}

      input[type="text"]:focus,
      input[type="number"]:focus,
      select:focus {{
        border-color: #4c6ef5;
      }}

      .diagram-container {{
        position: relative;
        width: 100%;
        height: {canvas_height}px;
        background: white;
        border-radius: 10px;
        overflow: hidden;
        border: 3px solid #e9ecef;
        cursor: default;
        display: flex;
        align-items: center;
        justify-content: center;
      }}

      .diagram-container.crosshair {{
        cursor: crosshair;
      }}

      .diagram-container.panning {{
        cursor: grab;
      }}

      .diagram-container.panning:active {{
        cursor: grabbing;
      }}

      svg {{
        transform-origin: center center;
        flex-shrink: 0;
        position: relative;
      }}

      .zoom-controls {{
        position: absolute;
        top: 10px;
        right: 10px;
        display: flex;
        gap: 5px;
        z-index: 1000;
        background: rgba(255,255,255,0.95);
        padding: 5px;
        border-radius: 8px;
        box-shadow: 0 2px 8px rgba(0,0,0,0.15);
      }}

      .zoom-info-badge {{
        position: absolute;
        bottom: 10px;
        right: 10px;
        background: rgba(76, 110, 245, 0.9);
        color: white;
        padding: 8px 12px;
        border-radius: 6px;
        font-size: 12px;
        font-weight: 600;
        z-index: 1000;
        pointer-events: none;
      }}

      .shape-element {{
        cursor: grab;
        transition: filter 0.2s, transform 0.1s;
      }}

      .shape-element:hover {{
        filter: brightness(1.08) drop-shadow(0 2px 8px rgba(76, 110, 245, 0.3));
        transform: translateY(-1px);
      }}

      .shape-element:active {{
        cursor: grabbing;
      }}

      .shape-element.selected {{
        filter: drop-shadow(0 0 10px rgba(76, 110, 245, 0.8));
      }}

      .resize-handle {{
        fill: #4c6ef5;
        stroke: white;
        stroke-width: 2;
        cursor: nwse-resize;
      }}

      .resize-handle:hover {{
        fill: #364fc7;
      }}

      .edit-text-btn {{
        fill: #4c6ef5;
        stroke: white;
        stroke-width: 2;
        cursor: pointer;
        transition: all 0.2s;
      }}

      .edit-text-btn:hover {{
        fill: #364fc7;
        r: 14;
      }}

      .connection-line {{
        stroke-width: 2;
        fill: none;
        cursor: pointer;
      }}

      .connection-line:hover {{
        stroke-width: 4;
      }}

      .connection-line.selected {{
        stroke-width: 4;
        filter: drop-shadow(0 0 5px rgba(76, 110, 245, 0.8));
      }}

      .connection-point {{
        fill: #4c6ef5;
        stroke: white;
        stroke-width: 2;
        cursor: crosshair;
        transition: all 0.2s;
        opacity: 0.6;
      }}

      .shape-element:hover .connection-point {{
        opacity: 1;
        animation: pulse 1.5s ease-in-out infinite;
      }}

      .connection-point:hover {{
        fill: #364fc7;
        r: 7;
        opacity: 1;
        animation: none;
      }}

      .connection-anchor {{
        cursor: grab;
        pointer-events: all;
        filter: drop-shadow(0 2px 4px rgba(0, 0, 0, 0.3));
      }}

      .connection-anchor:hover {{
        filter: drop-shadow(0 3px 8px rgba(0, 0, 0, 0.5));
        cursor: grab;
      }}

      .connection-anchor:active {{
        cursor: grabbing;
      }}

      .controls {{
        margin-top: 15px;
        text-align: center;
        color: #666;
        font-size: 13px;
        line-height: 1.6;
      }}

      .shape-text {{
        user-select: none;
        font-weight: 600;
      }}

      .shape-text.editable {{
        cursor: text;
      }}

      .temp-shape {{
        stroke-dasharray: 5, 5;
        opacity: 0.6;
      }}

      .temp-connection-line {{
        stroke: #4c6ef5;
        stroke-width: 2;
        stroke-dasharray: 5, 5;
        opacity: 0.7;
        pointer-events: none;
      }}

      @keyframes pulse {{
        0%,
        100% {{
          opacity: 1;
        }}
        50% {{
          opacity: 0.5;
        }}
      }}

      .drawing {{
        animation: pulse 1s infinite;
      }}

      .shape-element:hover .shape-connection-point,
      .shape-element.connection-mode .shape-connection-point {{
        opacity: 1;
      }}

      .shape-connection-point {{
        opacity: 0;
        fill: #4c6ef5;
        stroke: white;
        stroke-width: 2;
        cursor: crosshair;
        transition: opacity 0.2s;
      }}

      .shape-connection-point:hover {{
        fill: #ff6b6b;
        r: 7;
      }}

      foreignObject {{
        pointer-events: none;
      }}

      foreignObject.editing {{
        pointer-events: all;
      }}

      .inline-text-editor {{
        width: 100%;
        height: 100%;
        background: transparent;
        border: none;
        outline: none;
        text-align: center;
        font-size: 16px;
        font-weight: 600;
        font-family:
          -apple-system, BlinkMacSystemFont, "Segoe UI", "Roboto", sans-serif;
        resize: none;
        overflow: hidden;
        display: flex;
        align-items: center;
        justify-content: center;
      }}

      .inline-text-editor:focus {{
        background: rgba(255, 255, 255, 0.9);
        border-radius: 4px;
      }}

      .edit-icon-text {{
        pointer-events: none;
        user-select: none;
      }}
    </style>
  </head>
  <body>
    <div class="container">
      <h1>🎨 {title} Designer</h1>

      <div class="toolbar">
        <div class="toolbar-section">
          <span class="toolbar-label">Shapes:</span>
          <button
            class="tool-btn active"
            data-mode="rectangle"
            title="Draw rectangle by dragging"
          >
            <span>▭</span> Rectangle
          </button>
          <button
            class="tool-btn"
            data-mode="rounded-rect"
            title="Draw rounded rectangle"
          >
            <span>▢</span> Rounded
          </button>
          <button class="tool-btn" data-mode="circle" title="Draw circle">
            <span>●</span> Circle
          </button>
          <button class="tool-btn" data-mode="ellipse" title="Draw ellipse">
            <span>⬭</span> Ellipse
          </button>
          <button class="tool-btn" data-mode="diamond" title="Draw diamond">
            <span>◆</span> Diamond
          </button>
        </div>

        <div class="toolbar-section">
          <span class="toolbar-label">Lines:</span>
          <button
            class="tool-btn"
            data-mode="connection"
            title="Connect elements - click on connection points"
          >
            <span>🔗</span> Arrow
          </button>
          <select id="lineStyle">
            <option value="solid">Solid</option>
            <option value="dashed">Dashed</option>
            <option value="dotted">Dotted</option>
          </select>
        </div>

        <div class="toolbar-section">
          <span class="toolbar-label">Colors:</span>
          <input
            type="color"
            id="fillColor"
            class="color-picker"
            value="#a5d8ff"
            title="Fill color"
          />
          <input
            type="color"
            id="strokeColor"
            class="color-picker"
            value="#1971c2"
            title="Stroke color"
          />
          <input
            type="color"
            id="textColor"
            class="color-picker"
            value="#000000"
            title="Text color"
          />
        </div>

        <div class="toolbar-section">
          <button
            class="tool-btn"
            id="editTextBtn"
            title="Edit text of selected element"
            style="display: none"
          >
            <span>✏️</span> Edit Text
          </button>
          <button
            class="tool-btn"
            id="deleteBtn"
            title="Delete selected element"
          >
            <span>🗑️</span> Delete
          </button>
          <button class="tool-btn" id="clearBtn" title="Clear all">
            <span>🧹</span> Clear
          </button>
          <button class="tool-btn" id="exportBtn" title="Export as JSON">
            <span>💾</span> Export
          </button>
        </div>
      </div>

      <div class="diagram-container" id="diagramContainer">
        <div class="zoom-controls">
          <button class="tool-btn" onclick="resetDiagramView()" title="Reset View">↺</button>
        </div>
        <div class="zoom-info-badge" id="zoomInfo">100%</div>
        <svg id="diagram" width="{canvas_width}" height="{canvas_height}">
          <defs>
            <marker
              id="arrowhead"
              markerWidth="10"
              markerHeight="10"
              refX="9"
              refY="3"
              orient="auto"
            >
              <polygon points="0 0, 10 3, 0 6" fill="#666" />
            </marker>
          </defs>
          <g id="tempConnectionGroup"></g>
          <g id="connectionsGroup"></g>
          <g id="shapesGroup"></g>
          <g id="anchorsGroup"></g>
        </svg>
      </div>

      <div class="controls">
        <strong>✨ Intuitive Controls:</strong><br />
        <strong>🎯 Auto-Drag:</strong> Just hover over any shape and drag to move it (no need to click Select!) | <strong>🔗 Drag-Drop Connect:</strong> Click and DRAG from a blue connection point, then DROP on another blue point to connect | <strong>🔄 Reconnect:</strong> CLICK on any connection line to select it, then drag the ARROWHEAD itself (the arrow tip) to reconnect to a different shape | <strong>✏️ Edit Text:</strong> Double-click any shape or click the "Edit Text" button | <strong>📐 Resize:</strong> Drag corner handles when shape is selected | <strong>🎨 New Shapes:</strong> Select a shape tool, then click and drag to draw<br/>
        <strong>🔍 Zoom:</strong> Hold <strong>Ctrl + Mouse Wheel</strong> to zoom in/out | <strong>📍 Pan:</strong> Hold <strong>Space + Drag</strong> to pan around canvas
      </div>
    </div>

    <script>
      let elements = [];
      let connections = [];
      let currentMode = "rectangle";  // Default to rectangle mode
      let selectedElement = null;
      let draggedElement = null;
      let isDrawing = false;
      let mouseDownForDrawing = false;  // Track if mouse is down for drawing
      let drawStart = {{ x: 0, y: 0 }};
      let tempShape = null;
      let connectionStart = null;
      let connectionStartPoint = null;
      let tempConnectionLine = null;
      let resizingHandle = null;
      let draggedConnectionPoint = null;
      let editingElement = null;
      let nextId = 1;

      const svg = document.getElementById("diagram");
      const diagramContainer = document.getElementById("diagramContainer");
      const zoomInfo = document.getElementById("zoomInfo");

      // Zoom and Pan variables
      let diagramScale = 1;
      let diagramTranslateX = 0;
      let diagramTranslateY = 0;
      let isPanning = false;
      let panStartX = 0;
      let panStartY = 0;
      let spaceKeyPressed = false;

      function updateDiagramTransform() {{
        svg.style.transform = `translate(${{diagramTranslateX}}px, ${{diagramTranslateY}}px) scale(${{diagramScale}})`;
        zoomInfo.textContent = Math.round(diagramScale * 100) + '%';
      }}

      function resetDiagramView() {{
        diagramScale = 1;
        diagramTranslateX = 0;
        diagramTranslateY = 0;
        updateDiagramTransform();
      }}

      // Zoom with Ctrl + Mouse Wheel
      diagramContainer.addEventListener('wheel', (e) => {{
        if (e.ctrlKey) {{
          e.preventDefault();

          const containerRect = diagramContainer.getBoundingClientRect();
          const mouseX = e.clientX - containerRect.left;
          const mouseY = e.clientY - containerRect.top;

          const svgRect = svg.getBoundingClientRect();
          const svgCenterX = svgRect.left - containerRect.left + svgRect.width / 2;
          const svgCenterY = svgRect.top - containerRect.top + svgRect.height / 2;

          const mouseRelativeX = mouseX - svgCenterX;
          const mouseRelativeY = mouseY - svgCenterY;

          const delta = e.deltaY > 0 ? 0.9 : 1.1;
          const oldScale = diagramScale;
          const newScale = Math.min(Math.max(diagramScale * delta, 0.1), 10);

          const scaleDiff = newScale - oldScale;
          diagramTranslateX -= mouseRelativeX * (scaleDiff / oldScale);
          diagramTranslateY -= mouseRelativeY * (scaleDiff / oldScale);
          diagramScale = newScale;

          updateDiagramTransform();
        }}
      }}, {{ passive: false }});

      // Pan with Space + Drag
      document.addEventListener('keydown', (e) => {{
        if (e.code === 'Space' && !isPanning) {{
          spaceKeyPressed = true;
          diagramContainer.classList.add('panning');
        }}
      }});

      document.addEventListener('keyup', (e) => {{
        if (e.code === 'Space') {{
          spaceKeyPressed = false;
          isPanning = false;
          diagramContainer.classList.remove('panning');
        }}
      }});

      diagramContainer.addEventListener('mousedown', (e) => {{
        if (spaceKeyPressed) {{
          isPanning = true;
          panStartX = e.clientX - diagramTranslateX;
          panStartY = e.clientY - diagramTranslateY;
          e.preventDefault();
          return;
        }}
      }});

      document.addEventListener('mousemove', (e) => {{
        if (isPanning) {{
          diagramTranslateX = e.clientX - panStartX;
          diagramTranslateY = e.clientY - panStartY;
          updateDiagramTransform();
          e.preventDefault();
          return;
        }}
      }});

      document.addEventListener('mouseup', () => {{
        if (isPanning) {{
          isPanning = false;
        }}
      }});

      document.querySelectorAll("[data-mode]").forEach((btn) => {{
        btn.addEventListener("click", () => {{
          document.querySelectorAll("[data-mode]").forEach((b) => b.classList.remove("active"));
          btn.classList.add("active");
          currentMode = btn.getAttribute("data-mode");

          const container = document.getElementById("diagramContainer");
          if (currentMode === "connection") {{
            container.classList.remove("crosshair");
          }} else {{
            container.classList.add("crosshair");
          }}

          connectionStart = null;
          connectionStartPoint = null;
          tempConnectionLine = null;
          clearSelection();
          render();
        }});
      }});

      document.getElementById("editTextBtn").addEventListener("click", () => {{
        if (selectedElement && selectedElement.type !== "connection") {{
          startEditingText(selectedElement);
        }}
      }});

      document.getElementById("deleteBtn").addEventListener("click", () => {{
        if (selectedElement) {{
          if (selectedElement.type === "connection") {{
            connections = connections.filter((c) => c.id !== selectedElement.id);
          }} else {{
            elements = elements.filter((e) => e.id !== selectedElement.id);
            connections = connections.filter((c) => c.fromId !== selectedElement.id && c.toId !== selectedElement.id);
          }}
          selectedElement = null;
          document.getElementById("editTextBtn").style.display = "none";
          render();
        }}
      }});

      document.getElementById("clearBtn").addEventListener("click", () => {{
        if (confirm("Clear all elements?")) {{
          elements = [];
          connections = [];
          selectedElement = null;
          document.getElementById("editTextBtn").style.display = "none";
          render();
        }}
      }});

      document.getElementById("exportBtn").addEventListener("click", () => {{
        const data = JSON.stringify({{ elements, connections }}, null, 2);
        const blob = new Blob([data], {{ type: "application/json" }});
        const url = URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url;
        a.download = "{diagram_id}.json";
        a.click();
      }});

      svg.addEventListener("mousedown", handleMouseDown);
      svg.addEventListener("mousemove", handleMouseMove);
      svg.addEventListener("mouseup", handleMouseUp);
      svg.addEventListener("dblclick", handleDoubleClick);

      function getSvgCoords(e) {{
        const svgRect = svg.getBoundingClientRect();

        // Get mouse position relative to the transformed SVG (in screen space)
        const relativeScreenX = e.clientX - svgRect.left;
        const relativeScreenY = e.clientY - svgRect.top;

        // Convert from scaled coordinates back to original SVG coordinates
        const svgX = relativeScreenX / diagramScale;
        const svgY = relativeScreenY / diagramScale;

        return {{ x: svgX, y: svgY }};
      }}

      function handleMouseDown(e) {{
        const coords = getSvgCoords(e);
        const target = e.target;

        if (target.classList.contains("edit-text-btn") || target.classList.contains("edit-icon-text")) {{
          const elementId = target.dataset.elementId;
          const element = elements.find((el) => el.id === elementId);
          if (element) startEditingText(element);
          return;
        }}

        if (target.classList.contains("resize-handle")) {{
          resizingHandle = {{ element: selectedElement, corner: target.dataset.corner }};
          return;
        }}

        if (target.classList.contains("connection-anchor")) {{
          const conn = connections.find((c) => c.id === target.dataset.connectionId);
          const point = target.dataset.point;

          // Store original connection data for restoration if needed
          draggedConnectionPoint = {{
            connection: conn,
            point: point,
            dragHandle: target,  // Store reference to drag handle
            originalData: {{
              fromId: conn.fromId,
              fromPoint: conn.fromPoint,
              toId: conn.toId,
              toPoint: conn.toPoint,
              startX: conn.startX,
              startY: conn.startY,
              endX: conn.endX,
              endY: conn.endY
            }}
          }};

          // Disable pointer-events on drag handle so it doesn't block drop detection
          target.style.pointerEvents = "none";
          console.log("🎯 Started dragging connection anchor");

          e.stopPropagation();
          return;
        }}

        // DRAG-DROP CONNECT: Drag from connection point and drop on another
        if (target.classList.contains("shape-connection-point")) {{
          const elementId = target.dataset.elementId;
          const pointPosition = target.dataset.position;
          const element = elements.find((e) => e.id === elementId);

          if (element) {{
            // Start dragging connection line
            connectionStart = element;
            connectionStartPoint = pointPosition;
            e.stopPropagation();
          }}
          return;
        }}

        if (editingElement) return;

        // Don't start dragging element if we're starting a connection
        if (connectionStart && connectionStartPoint) {{
          return;
        }}

        // AUTO-DRAG: Click on element allows dragging regardless of current mode
        const clickedElement = elements.find((el) => isPointInElement(coords, el));
        if (clickedElement) {{
          selectedElement = clickedElement;
          draggedElement = clickedElement;
          draggedElement.dragOffset = {{ x: coords.x - clickedElement.x, y: coords.y - clickedElement.y }};
          document.getElementById("editTextBtn").style.display = "flex";
          render();
          return;
        }}

        // Allow selecting connections
        const clickedConnection = connections.find((c) => isPointNearLine(coords, c));
        if (clickedConnection) {{
          selectedElement = clickedConnection;
          selectedElement.type = "connection";
          document.getElementById("editTextBtn").style.display = "none";
          render();
          return;
        }}

        // Draw new shapes if in a shape mode (not connection mode) and clicked on empty space
        // Don't start drawing immediately - wait for mouse to actually move (drag)
        if (currentMode !== "connection") {{
          mouseDownForDrawing = true;
          drawStart = coords;
          return;
        }}

        clearSelection();
      }}

      function handleDoubleClick(e) {{
        const coords = getSvgCoords(e);
        const clickedElement = elements.find((el) => isPointInElement(coords, el));
        if (clickedElement && !editingElement) startEditingText(clickedElement);
      }}

      function startEditingText(element) {{
        editingElement = element;
        render();
        setTimeout(() => {{
          const textarea = document.getElementById("text-editor-" + element.id);
          if (textarea) {{ textarea.focus(); textarea.select(); }}
        }}, 10);
      }}

      function stopEditingText() {{
        editingElement = null;
        render();
      }}

      function handleMouseMove(e) {{
        const coords = getSvgCoords(e);
        if (editingElement) return;

        // AUTO-CONNECT: Show temp connection line when dragging from connection point (regardless of mode)
        if (connectionStart && connectionStartPoint) {{
          const startCoords = getConnectionPointCoords(connectionStart, connectionStartPoint);
          tempConnectionLine = {{ x1: startCoords.x, y1: startCoords.y, x2: coords.x, y2: coords.y }};
          renderTempConnection();
          return;
        }}

        if (resizingHandle) {{
          const element = resizingHandle.element;
          const corner = resizingHandle.corner;
          if (corner === "se") {{
            element.width = Math.max(50, coords.x - element.x);
            element.height = Math.max(30, coords.y - element.y);
          }} else if (corner === "sw") {{
            const newWidth = Math.max(50, element.x + element.width - coords.x);
            element.x = element.x + element.width - newWidth;
            element.width = newWidth;
            element.height = Math.max(30, coords.y - element.y);
          }} else if (corner === "ne") {{
            element.width = Math.max(50, coords.x - element.x);
            const newHeight = Math.max(30, element.y + element.height - coords.y);
            element.y = element.y + element.height - newHeight;
            element.height = newHeight;
          }} else if (corner === "nw") {{
            const newWidth = Math.max(50, element.x + element.width - coords.x);
            const newHeight = Math.max(30, element.y + element.height - coords.y);
            element.x = element.x + element.width - newWidth;
            element.y = element.y + element.height - newHeight;
            element.width = newWidth;
            element.height = newHeight;
          }}
          render();
          return;
        }}

        if (draggedConnectionPoint) {{
          const conn = draggedConnectionPoint.connection;
          if (draggedConnectionPoint.point === "start") {{
            conn.startX = coords.x;
            conn.startY = coords.y;
            conn.fromId = null;
          }} else {{
            conn.endX = coords.x;
            conn.endY = coords.y;
            conn.toId = null;
          }}
          render();
          return;
        }}

        // Start drawing only if mouse moved while button is down
        if (mouseDownForDrawing && !isDrawing) {{
          // Mouse moved after mousedown - now actually start drawing
          isDrawing = true;
        }}

        if (isDrawing) {{
          const width = coords.x - drawStart.x;
          const height = coords.y - drawStart.y;
          if (tempShape) {{
            tempShape.width = Math.abs(width);
            tempShape.height = Math.abs(height);
            tempShape.x = width < 0 ? coords.x : drawStart.x;
            tempShape.y = height < 0 ? coords.y : drawStart.y;
          }} else {{
            tempShape = {{
              id: "temp",
              x: drawStart.x,
              y: drawStart.y,
              width: Math.abs(width),
              height: Math.abs(height),
              shape: currentMode,
              fillColor: document.getElementById("fillColor").value,
              strokeColor: document.getElementById("strokeColor").value,
              textColor: document.getElementById("textColor").value,
              text: "New Element",
              isTemp: true
            }};
          }}
          render();
          return;
        }}

        // AUTO-DRAG: Allow dragging element regardless of current mode
        if (draggedElement) {{
          draggedElement.x = coords.x - draggedElement.dragOffset.x;
          draggedElement.y = coords.y - draggedElement.dragOffset.y;
          render();
          return;
        }}
      }}

      function handleMouseUp(e) {{
        if (resizingHandle) {{ resizingHandle = null; return; }}

        // DRAG-DROP CONNECT: Complete connection when dropping on connection point
        const target = e.target;
        if (connectionStart && connectionStartPoint && target.classList.contains("shape-connection-point")) {{
          const elementId = target.dataset.elementId;
          const pointPosition = target.dataset.position;
          const element = elements.find((e) => e.id === elementId);

          if (element && connectionStart.id !== element.id) {{
            // Create connection on drop
            createConnection(connectionStart.id, connectionStartPoint, element.id, pointPosition);
          }}

          // Clear connection state
          connectionStart = null;
          connectionStartPoint = null;
          tempConnectionLine = null;
          renderTempConnection();
          render();
          return;
        }}

        // Clear connection if dropped elsewhere
        if (connectionStart) {{
          connectionStart = null;
          connectionStartPoint = null;
          tempConnectionLine = null;
          renderTempConnection();
        }}

        if (draggedConnectionPoint) {{
          const coords = getSvgCoords(e);
          const conn = draggedConnectionPoint.connection;
          let reconnected = false;

          // Use elementFromPoint to find what's UNDER the mouse cursor (not the drag handle itself)
          const elementUnderCursor = document.elementFromPoint(e.clientX, e.clientY);
          console.log("🎯 DROP on:", elementUnderCursor?.classList, elementUnderCursor?.dataset);

          // Check if dropped on a valid connection point
          if (elementUnderCursor && elementUnderCursor.classList.contains("shape-connection-point")) {{
            const elementId = elementUnderCursor.dataset.elementId;
            const pointPosition = elementUnderCursor.dataset.position;
            const element = elements.find((el) => el.id === elementId);
            console.log("✅ Found connection point:", elementId, pointPosition);
            if (element) {{
              const pointCoords = getConnectionPointCoords(element, pointPosition);
              if (draggedConnectionPoint.point === "start") {{
                conn.fromId = elementId;
                conn.fromPoint = pointPosition;
                conn.startX = pointCoords.x;
                conn.startY = pointCoords.y;
              }} else {{
                conn.toId = elementId;
                conn.toPoint = pointPosition;
                conn.endX = pointCoords.x;
                conn.endY = pointCoords.y;
              }}
              reconnected = true;
              console.log("🎉 RECONNECTED!");
            }}
          }} else {{
            console.log("❌ Not dropped on connection point");
          }}

          // If not reconnected to a valid point, restore original connection
          if (!reconnected) {{
            console.log("🔄 RESTORING original connection");
            const orig = draggedConnectionPoint.originalData;
            conn.fromId = orig.fromId;
            conn.fromPoint = orig.fromPoint;
            conn.toId = orig.toId;
            conn.toPoint = orig.toPoint;
            conn.startX = orig.startX;
            conn.startY = orig.startY;
            conn.endX = orig.endX;
            conn.endY = orig.endY;
          }}

          // Re-enable pointer-events on drag handle (will be recreated in render)
          if (draggedConnectionPoint.dragHandle) {{
            draggedConnectionPoint.dragHandle.style.pointerEvents = "all";
          }}

          draggedConnectionPoint = null;
          render();
          return;
        }}

        if (isDrawing && tempShape) {{
          if (tempShape.width > 20 && tempShape.height > 20) {{
            tempShape.id = "element" + nextId++;
            tempShape.isTemp = false;
            elements.push(tempShape);
            selectedElement = tempShape;
            document.getElementById("editTextBtn").style.display = "flex";
          }}
          tempShape = null;
          isDrawing = false;
          mouseDownForDrawing = false;  // Reset flag
          render();
          return;
        }}

        // Clear flags on mouseup
        mouseDownForDrawing = false;
        draggedElement = null;
      }}

      function getConnectionPointCoords(element, position) {{
        const centerX = element.x + element.width / 2;
        const centerY = element.y + element.height / 2;
        switch (position) {{
          case "top": return {{ x: centerX, y: element.y }};
          case "right": return {{ x: element.x + element.width, y: centerY }};
          case "bottom": return {{ x: centerX, y: element.y + element.height }};
          case "left": return {{ x: element.x, y: centerY }};
          default: return {{ x: centerX, y: centerY }};
        }}
      }}

      function createConnection(fromId, fromPoint, toId, toPoint) {{
        const fromElement = elements.find((e) => e.id === fromId);
        const toElement = elements.find((e) => e.id === toId);
        const fromCoords = getConnectionPointCoords(fromElement, fromPoint);
        const toCoords = getConnectionPointCoords(toElement, toPoint);
        connections.push({{
          id: "conn" + nextId++,
          fromId, fromPoint, toId, toPoint,
          startX: fromCoords.x, startY: fromCoords.y,
          endX: toCoords.x, endY: toCoords.y,
          color: document.getElementById("strokeColor").value,
          style: document.getElementById("lineStyle").value
        }});
      }}

      function isPointInElement(point, element) {{
        if (element.shape === "circle") {{
          const centerX = element.x + element.width / 2;
          const centerY = element.y + element.height / 2;
          const radius = Math.min(element.width, element.height) / 2;
          const dx = point.x - centerX;
          const dy = point.y - centerY;
          return dx * dx + dy * dy <= radius * radius;
        }} else if (element.shape === "ellipse") {{
          const centerX = element.x + element.width / 2;
          const centerY = element.y + element.height / 2;
          const rx = element.width / 2;
          const ry = element.height / 2;
          const dx = (point.x - centerX) / rx;
          const dy = (point.y - centerY) / ry;
          return dx * dx + dy * dy <= 1;
        }} else if (element.shape === "diamond") {{
          const centerX = element.x + element.width / 2;
          const centerY = element.y + element.height / 2;
          const dx = Math.abs(point.x - centerX) / (element.width / 2);
          const dy = Math.abs(point.y - centerY) / (element.height / 2);
          return dx + dy <= 1;
        }} else {{
          return point.x >= element.x && point.x <= element.x + element.width && point.y >= element.y && point.y <= element.y + element.height;
        }}
      }}

      function isPointNearLine(point, connection) {{
        const x1 = connection.startX, y1 = connection.startY;
        const x2 = connection.endX, y2 = connection.endY;
        const A = point.x - x1, B = point.y - y1;
        const C = x2 - x1, D = y2 - y1;
        const dot = A * C + B * D;
        const lenSq = C * C + D * D;
        const param = lenSq !== 0 ? dot / lenSq : -1;
        let xx, yy;
        if (param < 0) {{ xx = x1; yy = y1; }}
        else if (param > 1) {{ xx = x2; yy = y2; }}
        else {{ xx = x1 + param * C; yy = y1 + param * D; }}
        const dx = point.x - xx, dy = point.y - yy;
        return Math.sqrt(dx * dx + dy * dy) < 10;
      }}

      function clearSelection() {{
        selectedElement = null;
        document.getElementById("editTextBtn").style.display = "none";
        render();
      }}

      function renderTempConnection() {{
        const tempGroup = document.getElementById("tempConnectionGroup");
        tempGroup.innerHTML = "";
        if (tempConnectionLine) {{
          const line = document.createElementNS("http://www.w3.org/2000/svg", "line");
          line.setAttribute("x1", tempConnectionLine.x1);
          line.setAttribute("y1", tempConnectionLine.y1);
          line.setAttribute("x2", tempConnectionLine.x2);
          line.setAttribute("y2", tempConnectionLine.y2);
          line.classList.add("temp-connection-line");
          line.setAttribute("marker-end", "url(#arrowhead)");
          tempGroup.appendChild(line);
        }}
      }}

      function render() {{
        const shapesGroup = document.getElementById("shapesGroup");
        const connectionsGroup = document.getElementById("connectionsGroup");
        const anchorsGroup = document.getElementById("anchorsGroup");
        shapesGroup.innerHTML = "";
        connectionsGroup.innerHTML = "";
        anchorsGroup.innerHTML = "";  // Clear anchors too

        connections.forEach((conn) => {{
          if (conn.fromId && conn.fromPoint) {{
            const fromElement = elements.find((e) => e.id === conn.fromId);
            if (fromElement) {{
              const coords = getConnectionPointCoords(fromElement, conn.fromPoint);
              conn.startX = coords.x;
              conn.startY = coords.y;
            }}
          }}
          if (conn.toId && conn.toPoint) {{
            const toElement = elements.find((e) => e.id === conn.toId);
            if (toElement) {{
              const coords = getConnectionPointCoords(toElement, conn.toPoint);
              conn.endX = coords.x;
              conn.endY = coords.y;
            }}
          }}

          // Create wider invisible hit area for easier clicking
          const hitArea = document.createElementNS("http://www.w3.org/2000/svg", "line");
          hitArea.setAttribute("x1", conn.startX);
          hitArea.setAttribute("y1", conn.startY);
          hitArea.setAttribute("x2", conn.endX);
          hitArea.setAttribute("y2", conn.endY);
          hitArea.setAttribute("stroke", "transparent");
          hitArea.setAttribute("stroke-width", "20");
          hitArea.style.cursor = "pointer";
          hitArea.dataset.connectionId = conn.id;
          hitArea.classList.add("connection-hit-area");

          // CLICK to select connection (not hover!)
          hitArea.addEventListener("click", (e) => {{
            console.log("✅ CLICK SELECT:", conn.id, "from", conn.fromId, "to", conn.toId);
            selectedElement = conn;
            selectedElement.type = "connection";
            document.getElementById("editTextBtn").style.display = "none";
            e.stopPropagation();
            render();
          }});

          connectionsGroup.appendChild(hitArea);

          // Create visible connection line
          const line = document.createElementNS("http://www.w3.org/2000/svg", "line");
          line.setAttribute("x1", conn.startX);
          line.setAttribute("y1", conn.startY);
          line.setAttribute("x2", conn.endX);
          line.setAttribute("y2", conn.endY);
          line.setAttribute("stroke", conn.color);
          line.setAttribute("marker-end", "url(#arrowhead)");
          line.classList.add("connection-line");
          line.style.pointerEvents = "none";  // Let hit area handle events
          if (conn.style === "dashed") line.setAttribute("stroke-dasharray", "5,5");
          else if (conn.style === "dotted") line.setAttribute("stroke-dasharray", "2,3");
          if (selectedElement && selectedElement.id === conn.id) line.classList.add("selected");

          connectionsGroup.appendChild(line);

          // Store anchor data for later rendering (after shapes, so anchors appear on top)
          if (selectedElement && selectedElement.id === conn.id) {{
            conn._showAnchors = true;
          }} else {{
            conn._showAnchors = false;
          }}
        }});

        const allElements = tempShape ? [...elements, tempShape] : elements;
        allElements.forEach((element) => {{
          const group = document.createElementNS("http://www.w3.org/2000/svg", "g");
          group.classList.add("shape-element");
          // Show connection points when: in connection mode, creating new connection, OR reconnecting existing connection
          if (currentMode === "connection" || connectionStart || draggedConnectionPoint) {{
            group.classList.add("connection-mode");
          }}
          if (selectedElement && selectedElement.id === element.id) group.classList.add("selected");
          if (element.isTemp) group.classList.add("temp-shape");

          let shape;
          if (element.shape === "rectangle") {{
            shape = document.createElementNS("http://www.w3.org/2000/svg", "rect");
            shape.setAttribute("x", element.x);
            shape.setAttribute("y", element.y);
            shape.setAttribute("width", element.width);
            shape.setAttribute("height", element.height);
          }} else if (element.shape === "rounded-rect") {{
            shape = document.createElementNS("http://www.w3.org/2000/svg", "rect");
            shape.setAttribute("x", element.x);
            shape.setAttribute("y", element.y);
            shape.setAttribute("width", element.width);
            shape.setAttribute("height", element.height);
            shape.setAttribute("rx", 15);
            shape.setAttribute("ry", 15);
          }} else if (element.shape === "circle") {{
            shape = document.createElementNS("http://www.w3.org/2000/svg", "circle");
            const radius = Math.min(element.width, element.height) / 2;
            shape.setAttribute("cx", element.x + element.width / 2);
            shape.setAttribute("cy", element.y + element.height / 2);
            shape.setAttribute("r", radius);
          }} else if (element.shape === "ellipse") {{
            shape = document.createElementNS("http://www.w3.org/2000/svg", "ellipse");
            shape.setAttribute("cx", element.x + element.width / 2);
            shape.setAttribute("cy", element.y + element.height / 2);
            shape.setAttribute("rx", element.width / 2);
            shape.setAttribute("ry", element.height / 2);
          }} else if (element.shape === "diamond") {{
            shape = document.createElementNS("http://www.w3.org/2000/svg", "polygon");
            const cx = element.x + element.width / 2;
            const cy = element.y + element.height / 2;
            const points = `${{cx}},${{element.y}} ${{element.x + element.width}},${{cy}} ${{cx}},${{element.y + element.height}} ${{element.x}},${{cy}}`;
            shape.setAttribute("points", points.trim());
          }}

          shape.setAttribute("fill", element.fillColor);
          shape.setAttribute("stroke", element.strokeColor);
          shape.setAttribute("stroke-width", 3);
          group.appendChild(shape);

          if (!element.isTemp) {{
            const positions = ["top", "right", "bottom", "left"];
            positions.forEach((pos) => {{
              const coords = getConnectionPointCoords(element, pos);
              const point = document.createElementNS("http://www.w3.org/2000/svg", "circle");
              point.setAttribute("cx", coords.x);
              point.setAttribute("cy", coords.y);
              point.setAttribute("r", 5);
              point.classList.add("shape-connection-point");
              point.dataset.elementId = element.id;
              point.dataset.position = pos;
              group.appendChild(point);
            }});
          }}

          if (editingElement && editingElement.id === element.id) {{
            const fo = document.createElementNS("http://www.w3.org/2000/svg", "foreignObject");
            fo.setAttribute("x", element.x);
            fo.setAttribute("y", element.y);
            fo.setAttribute("width", element.width);
            fo.setAttribute("height", element.height);
            fo.classList.add("editing");

            const textarea = document.createElement("textarea");
            textarea.className = "inline-text-editor";
            textarea.id = "text-editor-" + element.id;
            textarea.value = element.text;
            textarea.style.color = element.textColor;

            textarea.addEventListener("blur", () => {{
              element.text = textarea.value || "New Element";
              stopEditingText();
            }});

            textarea.addEventListener("keydown", (e) => {{
              if (e.key === "Enter" && !e.shiftKey) {{
                e.preventDefault();
                element.text = textarea.value || "New Element";
                stopEditingText();
              }}
              if (e.key === "Escape") stopEditingText();
            }});

            fo.appendChild(textarea);
            group.appendChild(fo);
          }} else {{
            const text = document.createElementNS("http://www.w3.org/2000/svg", "text");
            text.setAttribute("x", element.x + element.width / 2);
            text.setAttribute("y", element.y + element.height / 2 + 6);
            text.setAttribute("text-anchor", "middle");
            text.setAttribute("fill", element.textColor);
            text.setAttribute("font-size", "16");
            text.classList.add("shape-text");
            text.textContent = element.text;
            group.appendChild(text);
          }}

          if (selectedElement && selectedElement.id === element.id && !element.isTemp) {{
            const corners = [
              {{ x: element.x + element.width, y: element.y + element.height, corner: "se" }},
              {{ x: element.x, y: element.y + element.height, corner: "sw" }},
              {{ x: element.x + element.width, y: element.y, corner: "ne" }},
              {{ x: element.x, y: element.y, corner: "nw" }}
            ];

            corners.forEach((c) => {{
              const handle = document.createElementNS("http://www.w3.org/2000/svg", "circle");
              handle.setAttribute("cx", c.x);
              handle.setAttribute("cy", c.y);
              handle.setAttribute("r", 6);
              handle.classList.add("resize-handle");
              handle.dataset.corner = c.corner;
              group.appendChild(handle);
            }});

            const editBtn = document.createElementNS("http://www.w3.org/2000/svg", "circle");
            editBtn.setAttribute("cx", element.x + element.width / 2);
            editBtn.setAttribute("cy", element.y - 20);
            editBtn.setAttribute("r", 12);
            editBtn.classList.add("edit-text-btn");
            editBtn.dataset.elementId = element.id;
            group.appendChild(editBtn);

            const editIcon = document.createElementNS("http://www.w3.org/2000/svg", "text");
            editIcon.setAttribute("x", element.x + element.width / 2);
            editIcon.setAttribute("y", element.y - 13);
            editIcon.setAttribute("text-anchor", "middle");
            editIcon.setAttribute("fill", "white");
            editIcon.setAttribute("font-size", "14");
            editIcon.classList.add("edit-icon-text");
            editIcon.dataset.elementId = element.id;
            editIcon.textContent = "✏️";
            group.appendChild(editIcon);
          }}

          shapesGroup.appendChild(group);
        }});

        // Render anchors AFTER shapes so they appear on top and are always clickable
        // BUT if currently dragging, hide them so they don't block connection points
        connections.forEach((conn) => {{
          if (conn._showAnchors && !draggedConnectionPoint) {{
            // BLUE start anchor
            const startAnchor = document.createElementNS("http://www.w3.org/2000/svg", "circle");
            startAnchor.setAttribute("cx", conn.startX);
            startAnchor.setAttribute("cy", conn.startY);
            startAnchor.setAttribute("r", 12);
            startAnchor.classList.add("connection-anchor");
            startAnchor.dataset.connectionId = conn.id;
            startAnchor.dataset.point = "start";
            startAnchor.setAttribute("fill", "#4c6ef5");
            startAnchor.setAttribute("stroke", "white");
            startAnchor.setAttribute("stroke-width", "3");
            startAnchor.style.pointerEvents = "all";
            startAnchor.style.cursor = "grab";
            anchorsGroup.appendChild(startAnchor);

            // Create INVISIBLE drag area over the actual arrowhead
            const dx = conn.endX - conn.startX;
            const dy = conn.endY - conn.startY;
            const length = Math.sqrt(dx * dx + dy * dy);

            // Position drag handle right at the arrowhead location
            const offset = 8;  // Position at the actual arrowhead
            const arrowHeadX = conn.endX - (dx / length) * offset;
            const arrowHeadY = conn.endY - (dy / length) * offset;

            // Create COMPLETELY INVISIBLE circle over the arrowhead for easy dragging
            // This makes it feel like you're dragging the actual arrowhead
            const endDragHandle = document.createElementNS("http://www.w3.org/2000/svg", "circle");
            endDragHandle.setAttribute("cx", arrowHeadX);
            endDragHandle.setAttribute("cy", arrowHeadY);
            endDragHandle.setAttribute("r", 25);  // Large invisible hit area over arrowhead
            endDragHandle.classList.add("connection-anchor");
            endDragHandle.dataset.connectionId = conn.id;
            endDragHandle.dataset.point = "end";
            endDragHandle.setAttribute("fill", "transparent");  // COMPLETELY INVISIBLE
            endDragHandle.setAttribute("stroke", "none");  // No stroke - totally invisible
            endDragHandle.style.pointerEvents = "all";
            endDragHandle.style.cursor = "grab";

            anchorsGroup.appendChild(endDragHandle);
          }}
        }});
      }}

      // Initialize with provided elements or default microservices architecture
      elements = {elements_js};

      // Update nextId based on elements count
      nextId = elements.length + 1;

      function createInitialConnection(fromId, fromPoint, toId, toPoint) {{
        const fromElement = elements.find((e) => e.id === fromId);
        const toElement = elements.find((e) => e.id === toId);
        const fromCoords = getConnectionPointCoords(fromElement, fromPoint);
        const toCoords = getConnectionPointCoords(toElement, toPoint);
        return {{
          id: "conn" + nextId++, fromId, fromPoint, toId, toPoint,
          startX: fromCoords.x, startY: fromCoords.y,
          endX: toCoords.x, endY: toCoords.y,
          color: "#1971c2", style: "solid"
        }};
      }}

      connections = {connections_js};

      render();
    </script>
  </body>
</html>"""

def parse_sequence_steps(description: str) -> tuple:
    """Parse sequence diagram description into participants and steps"""
    import re
    import sys

    # Debug logging
    print(f"DEBUG: parse_sequence_steps called", file=sys.stderr)
    print(f"DEBUG: Description length: {len(description)}", file=sys.stderr)
    print(f"DEBUG: First 200 chars: {description[:200]}", file=sys.stderr)

    lines = [line.strip() for line in description.split('\n') if line.strip()]
    print(f"DEBUG: Total lines: {len(lines)}", file=sys.stderr)

    # More flexible line filtering - accept lines with OR without bullets
    # Remove bullet points if present, but accept all lines that look like steps
    processed_lines = []
    for line in lines:
        # Strip bullet points
        clean_line = line.lstrip('- •*#>').strip()

        # Skip empty lines
        if not clean_line:
            continue

        # Skip lines that are clearly not steps (too short, all lowercase, etc.)
        if len(clean_line) < 10:
            continue

        # Accept line if it has at least one capital letter (likely a service name)
        if any(c.isupper() for c in clean_line):
            processed_lines.append(clean_line)

    lines = processed_lines
    print(f"DEBUG: Processed lines: {len(lines)}", file=sys.stderr)
    for i, line in enumerate(lines[:5]):
        print(f"DEBUG: Line {i+1}: {line}", file=sys.stderr)

    participants = []
    steps = []

    # Keywords that indicate direction
    request_keywords = ['sends', 'forwards', 'queries', 'requests', 'submits', 'validates', 'checks', 'logs', 'stores', 'generates', 'calls', 'invokes']
    response_keywords = ['returns', 'responds', 'sends back', 'displays', 'replies']

    for line in lines:
        if not line:
            continue

        # Use regex to find capitalized phrases (2+ consecutive capital words or single capital word followed by Service/Database/Cache/Gateway)
        # Pattern: Word starting with capital, optionally followed by more words with capitals or specific keywords
        participant_pattern = r'\b([A-Z][a-zA-Z]*(?:\s+(?:[A-Z][a-zA-Z]*|Service|Database|Cache|Gateway|Storage|Queue|API|Engine|Manager|Handler|Controller))*)\b'

        matches = re.findall(participant_pattern, line)

        # Filter out single words that are likely verbs/actions, not participants
        potential_participants = []
        action_words = ['Submit', 'Send', 'Forward', 'Query', 'Return', 'Validate', 'Check', 'Store', 'Generate', 'Display', 'Process', 'Create', 'Update', 'Delete', 'Log', 'Request', 'Response']

        for match in matches:
            # Skip single action words
            if match in action_words:
                continue
            # Skip very short matches unless they end with Service/Database/etc
            if len(match) < 3 and not any(keyword in match for keyword in ['Service', 'Database', 'Cache', 'Gateway']):
                continue
            potential_participants.append(match)

        # Determine if this is a response
        is_response = any(keyword in line.lower() for keyword in response_keywords)

        # Handle implicit responses: "Database returns data" means return to whoever sent the last request
        if len(potential_participants) == 1 and is_response and steps:
            # Find the most recent step where someone sent TO this participant
            from_participant = potential_participants[0]
            to_participant = None

            # Look backwards through steps to find who last sent to this participant
            for prev_step in reversed(steps):
                if prev_step['to'] == from_participant:
                    to_participant = prev_step['from']
                    break

            if to_participant:
                # This is a response from from_participant back to to_participant
                potential_participants = [from_participant, to_participant]

        # Need at least 2 participants (from and to)
        if len(potential_participants) >= 2:
            from_participant = potential_participants[0]
            # Find "to", "from", "with", "in" to identify the second participant
            to_participant = potential_participants[1]

            # Try to find which one comes after "to"/"with"/"in"
            for i, participant in enumerate(potential_participants[1:], 1):
                # Check if this participant appears after "to", "with", "in", "from"
                for keyword in [' to ', ' with ', ' in ', ' from ']:
                    if keyword + participant in line:
                        to_participant = participant
                        break

            # Extract message text
            message = line

            # Remove the from_participant from the start
            if line.startswith(from_participant):
                message = line[len(from_participant):].strip()

            # Remove "to [participant]" or "from [participant]" from the end
            for keyword in ['to', 'from', 'with', 'in']:
                pattern = f' {keyword} {re.escape(to_participant)}$'
                message = re.sub(pattern, '', message)
                pattern = f' {keyword} {re.escape(to_participant)} '
                if pattern in message:
                    message = message.split(pattern)[0].strip()

            # Clean up the message
            message = message.strip()
            if not message:
                message = "message"

            # is_response was already determined earlier

            # Add participants if not already present
            if from_participant not in participants:
                participants.append(from_participant)
            if to_participant not in participants:
                participants.append(to_participant)

            steps.append({
                'from': from_participant,
                'to': to_participant,
                'message': message,
                'is_response': is_response
            })

    return participants, steps

def generate_sequence_diagram_svg(title: str, description: str) -> str:
    """Generate beautiful custom SVG sequence diagram matching the professional template"""
    import sys

    try:
        participants, steps = parse_sequence_steps(description)

        print(f"DEBUG: Participants found: {len(participants)}", file=sys.stderr)
        print(f"DEBUG: Steps found: {len(steps)}", file=sys.stderr)

        if not participants or not steps:
            # Fallback: return a detailed error message
            error_msg = f"No valid sequence steps found. Participants: {len(participants)}, Steps: {len(steps)}"
            print(f"ERROR: {error_msg}", file=sys.stderr)
            print(f"ERROR: Description was: {description[:500]}", file=sys.stderr)
            return f'<svg width="1000" height="300"><text x="500" y="150" text-anchor="middle" fill="#ef4444" font-size="18" font-weight="bold">Error: {error_msg}</text><text x="500" y="180" text-anchor="middle" fill="#64748b" font-size="14">Use bullet points like: - Service A sends request to Service B</text></svg>'
    except Exception as e:
        print(f"ERROR in generate_sequence_diagram_svg: {str(e)}", file=sys.stderr)
        import traceback
        traceback.print_exc(file=sys.stderr)
        return f'<svg width="1000" height="200"><text x="500" y="100" text-anchor="middle" fill="#ef4444" font-size="16">Error generating diagram: {str(e)}</text></svg>'

    # Rich color gradients for different services
    color_schemes = [
        {'name': 'grad0', 'start': '#3b82f6', 'end': '#2563eb', 'stroke': '#2563eb'},   # Blue
        {'name': 'grad1', 'start': '#8b5cf6', 'end': '#7c3aed', 'stroke': '#7c3aed'},   # Purple
        {'name': 'grad2', 'start': '#10b981', 'end': '#059669', 'stroke': '#059669'},   # Green
        {'name': 'grad3', 'start': '#f59e0b', 'end': '#d97706', 'stroke': '#d97706'},   # Orange
        {'name': 'grad4', 'start': '#ef4444', 'end': '#dc2626', 'stroke': '#dc2626'},   # Red
        {'name': 'grad5', 'start': '#ec4899', 'end': '#db2777', 'stroke': '#db2777'},   # Pink
        {'name': 'grad6', 'start': '#06b6d4', 'end': '#0891b2', 'stroke': '#0891b2'},   # Cyan
        {'name': 'grad7', 'start': '#64748b', 'end': '#475569', 'stroke': '#475569'},   # Slate
        {'name': 'grad8', 'start': '#14b8a6', 'end': '#0d9488', 'stroke': '#0d9488'},   # Teal
        {'name': 'grad9', 'start': '#a855f7', 'end': '#9333ea', 'stroke': '#9333ea'},   # Violet
        {'name': 'grad10', 'start': '#f97316', 'end': '#ea580c', 'stroke': '#ea580c'}, # Orange-red
        {'name': 'grad11', 'start': '#84cc16', 'end': '#65a30d', 'stroke': '#65a30d'}, # Lime
    ]

    # Assign colors to participants
    participant_colors = {}
    for idx, participant in enumerate(participants):
        participant_colors[participant] = color_schemes[idx % len(color_schemes)]

    # Calculate dimensions dynamically
    num_participants = len(participants)
    box_width = 120
    box_spacing = 150
    start_x = 70

    # Calculate canvas width to fit all participants with proper spacing
    canvas_width = max(1500, start_x + num_participants * box_spacing + 100)

    # Calculate height based on number of steps (30px per step)
    step_height = 30
    canvas_height = 200 + len(steps) * step_height + 200

    # X positions for participants (center of their boxes)
    participant_x_positions = {}
    for idx, participant in enumerate(participants):
        participant_x_positions[participant] = start_x + idx * box_spacing

    # Generate SVG with defs
    svg = f'''<svg width="{canvas_width}" height="{canvas_height}" viewBox="0 0 {canvas_width} {canvas_height}" xmlns="http://www.w3.org/2000/svg">
        <defs>'''

    # Add gradient definitions
    for color in color_schemes:
        svg += f'''
          <linearGradient id="{color['name']}" x1="0%" y1="0%" x2="0%" y2="100%">
            <stop offset="0%" style="stop-color: {color['start']}; stop-opacity: 1" />
            <stop offset="100%" style="stop-color: {color['end']}; stop-opacity: 1" />
          </linearGradient>'''

    # Add arrow markers
    svg += '''
          <marker id="arrowRequest" markerWidth="10" markerHeight="10" refX="9" refY="3" orient="auto" markerUnits="strokeWidth">
            <polygon points="0 0, 10 3, 0 6" fill="#1e293b" />
          </marker>
          <marker id="arrowResponse" markerWidth="10" markerHeight="10" refX="9" refY="3" orient="auto" markerUnits="strokeWidth">
            <polygon points="0 0, 10 3, 0 6" fill="#64748b" />
          </marker>
        </defs>'''

    # Draw participant boxes at top
    for participant in participants:
        center_x = participant_x_positions[participant]
        x = center_x - box_width // 2
        color = participant_colors[participant]

        # Split long names intelligently
        name_parts = participant.split()
        if len(name_parts) >= 2:
            # Split into two lines
            line1 = name_parts[0]
            line2 = ' '.join(name_parts[1:])
            svg += f'''
        <g class="actor-box">
          <rect x="{x}" y="20" width="{box_width}" height="60" rx="8" fill="url(#{color['name']})" stroke="{color['stroke']}" stroke-width="2" />
          <text x="{center_x}" y="45" text-anchor="middle" fill="white" font-size="13" font-weight="700">{line1}</text>
          <text x="{center_x}" y="62" text-anchor="middle" fill="white" font-size="13" font-weight="700">{line2}</text>
        </g>'''
        else:
            svg += f'''
        <g class="actor-box">
          <rect x="{x}" y="20" width="{box_width}" height="60" rx="8" fill="url(#{color['name']})" stroke="{color['stroke']}" stroke-width="2" />
          <text x="{center_x}" y="55" text-anchor="middle" fill="white" font-size="14" font-weight="700">{participant}</text>
        </g>'''

    # Draw lifelines (vertical dashed lines)
    lifeline_end = canvas_height - 80
    for participant in participants:
        x = participant_x_positions[participant]
        svg += f'''
        <line x1="{x}" y1="80" x2="{x}" y2="{lifeline_end}" stroke="#cbd5e1" stroke-width="2" stroke-dasharray="5,5" />'''

    # Draw messages with numbered labels
    y_position = 130
    for idx, step in enumerate(steps):
        from_x = participant_x_positions[step['from']]
        to_x = participant_x_positions[step['to']]

        # Determine arrow style (request vs response)
        if step['is_response']:
            stroke_color = '#64748b'
            stroke_dasharray = '5,5'
            marker = 'arrowResponse'
        else:
            stroke_color = '#1e293b'
            stroke_dasharray = 'none'
            marker = 'arrowRequest'

        # Calculate midpoint for text label
        mid_x = (from_x + to_x) / 2
        text_y = y_position - 5

        # Limit message length to prevent overflow
        message = step['message']
        max_length = 50
        if len(message) > max_length:
            message = message[:max_length - 3] + '...'

        svg += f'''
        <g class="message-line">
          <line x1="{from_x}" y1="{y_position}" x2="{to_x}" y2="{y_position}"
                stroke="{stroke_color}" stroke-width="2" stroke-dasharray="{stroke_dasharray}"
                marker-end="url(#{marker})" />
          <text x="{mid_x}" y="{text_y}" text-anchor="middle" fill="{stroke_color}"
                font-size="11" font-weight="500" class="message-text">{idx + 1}. {message}</text>
        </g>'''

        y_position += step_height

    # Draw participant boxes at bottom
    y_bottom = canvas_height - 140
    for participant in participants:
        center_x = participant_x_positions[participant]
        x = center_x - box_width // 2
        color = participant_colors[participant]

        # Split long names intelligently
        name_parts = participant.split()
        if len(name_parts) >= 2:
            line1 = name_parts[0]
            line2 = ' '.join(name_parts[1:])
            svg += f'''
        <g class="actor-box">
          <rect x="{x}" y="{y_bottom}" width="{box_width}" height="60" rx="8" fill="url(#{color['name']})" stroke="{color['stroke']}" stroke-width="2" />
          <text x="{center_x}" y="{y_bottom + 27}" text-anchor="middle" fill="white" font-size="13" font-weight="700">{line1}</text>
          <text x="{center_x}" y="{y_bottom + 44}" text-anchor="middle" fill="white" font-size="13" font-weight="700">{line2}</text>
        </g>'''
        else:
            svg += f'''
        <g class="actor-box">
          <rect x="{x}" y="{y_bottom}" width="{box_width}" height="60" rx="8" fill="url(#{color['name']})" stroke="{color['stroke']}" stroke-width="2" />
          <text x="{center_x}" y="{y_bottom + 37}" text-anchor="middle" fill="white" font-size="14" font-weight="700">{participant}</text>
        </g>'''

    svg += '''
      </svg>'''

    return svg

def generate_sequence_diagram_html(title: str, description: str) -> str:
    """Generate beautiful sequence diagram HTML with custom SVG matching professional template"""
    import sys

    try:
        print(f"DEBUG: generate_sequence_diagram_html called with title='{title}'", file=sys.stderr)
        print(f"DEBUG: Description has {len(description)} chars, {description.count(chr(10))} lines", file=sys.stderr)

        svg_content = generate_sequence_diagram_svg(title, description)

        print(f"DEBUG: SVG content generated, length={len(svg_content)}", file=sys.stderr)
    except Exception as e:
        print(f"ERROR in generate_sequence_diagram_html: {str(e)}", file=sys.stderr)
        import traceback
        traceback.print_exc(file=sys.stderr)
        svg_content = f'<svg width="1000" height="200"><text x="500" y="100" text-anchor="middle" fill="#ef4444" font-size="16">Error: {str(e)}</text></svg>'

    return f"""<!doctype html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>{title}</title>
    <style>
      body {{
        margin: 0;
        padding: 20px;
        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "Roboto", "Helvetica Neue", sans-serif;
        background: linear-gradient(135deg, #0f172a 0%, #1e293b 100%);
        min-height: 100vh;
      }}
      .container {{
        max-width: 1600px;
        margin: 0 auto;
        background: white;
        border-radius: 16px;
        padding: 40px;
        box-shadow: 0 20px 60px rgba(0, 0, 0, 0.5);
        overflow-x: auto;
      }}
      h1 {{
        color: #1e293b;
        margin-top: 0;
        font-size: 32px;
        font-weight: 700;
        text-align: center;
        margin-bottom: 10px;
        letter-spacing: -0.5px;
      }}
      .subtitle {{
        color: #64748b;
        text-align: center;
        margin-bottom: 40px;
        font-size: 16px;
        font-weight: 400;
      }}
      svg {{
        display: block;
        margin: 0 auto;
        max-width: 100%;
        height: auto;
      }}
      .actor-box {{
        transition: all 0.3s ease;
      }}
      .actor-box:hover {{
        filter: brightness(1.1);
        transform: translateY(-2px);
      }}
      .message-line {{
        transition: all 0.3s ease;
      }}
      .message-line:hover line {{
        stroke-width: 3;
        cursor: pointer;
      }}
      .message-text {{
        pointer-events: none;
      }}
      .legend {{
        display: flex;
        justify-content: center;
        gap: 30px;
        margin-top: 40px;
        padding: 20px;
        background: #f8fafc;
        border-radius: 12px;
        flex-wrap: wrap;
        border: 1px solid #e2e8f0;
      }}
      .legend-item {{
        display: flex;
        align-items: center;
        gap: 10px;
        font-size: 14px;
        color: #475569;
      }}
      .legend-item strong {{
        color: #1e293b;
      }}
      .phase-label {{
        background: #f1f5f9;
        padding: 12px 24px;
        border-radius: 8px;
        font-weight: 700;
        color: #334155;
        text-align: center;
        margin: 20px 0 10px 0;
      }}
      .controls {{
        display: flex;
        justify-content: center;
        gap: 15px;
        margin-bottom: 30px;
        flex-wrap: wrap;
      }}
      .btn {{
        background: #3b82f6;
        color: white;
        border: none;
        padding: 10px 20px;
        border-radius: 8px;
        cursor: pointer;
        font-size: 14px;
        font-weight: 600;
        transition: all 0.3s ease;
        box-shadow: 0 2px 4px rgba(0,0,0,0.1);
      }}
      .btn:hover {{
        background: #2563eb;
        transform: translateY(-2px);
        box-shadow: 0 4px 8px rgba(0,0,0,0.2);
      }}
      .zoom-info {{
        position: fixed;
        bottom: 20px;
        right: 20px;
        background: rgba(30, 41, 59, 0.9);
        color: white;
        padding: 12px 20px;
        border-radius: 8px;
        font-size: 14px;
        font-weight: 600;
        z-index: 1000;
        box-shadow: 0 4px 12px rgba(0,0,0,0.3);
        pointer-events: none;
      }}
      .help-text {{
        text-align: center;
        color: #64748b;
        font-size: 13px;
        margin-bottom: 20px;
        font-style: italic;
      }}
      .svg-container {{
        overflow: hidden;
        cursor: grab;
        position: relative;
        border: 2px solid #e2e8f0;
        border-radius: 8px;
        background: #fafafa;
        width: 100%;
        height: 75vh;
        min-height: 500px;
        display: flex;
        align-items: center;
        justify-content: center;
      }}
      .svg-container:active {{
        cursor: grabbing;
      }}
      .svg-container svg {{
        transform-origin: center center;
        flex-shrink: 0;
        position: relative;
      }}
    </style>
  </head>
  <body>
    <div class="container">
      <h1>{title}</h1>
      <p class="subtitle">
        Complete sequence flow with all service interactions
      </p>

      <p class="help-text">
        💡 <strong>Ctrl + Mouse Wheel</strong> to zoom in/out at cursor position | <strong>Click & Drag</strong> to pan
      </p>

      <div class="controls">
        <button class="btn" onclick="resetView()">↺ Reset View</button>
        <button class="btn" onclick="exportPNG()">📷 Export PNG</button>
        <button class="btn" onclick="exportSVG()">🎨 Export SVG</button>
      </div>

      <div class="svg-container" id="svgContainer">
        {svg_content}
      </div>

      <div class="zoom-info" id="zoomLevel">100%</div>

      <!-- Legend -->
      <div class="legend">
        <div class="legend-item">
          <svg width="60" height="20">
            <line x1="5" y1="10" x2="55" y2="10" stroke="#1e293b" stroke-width="2" />
            <polygon points="50 6, 55 10, 50 14" fill="#1e293b" />
          </svg>
          <span><strong>Request</strong> (synchronous call)</span>
        </div>
        <div class="legend-item">
          <svg width="60" height="20">
            <line x1="5" y1="10" x2="55" y2="10" stroke="#64748b" stroke-width="2" stroke-dasharray="5,5" />
            <polygon points="50 6, 55 10, 50 14" fill="#64748b" />
          </svg>
          <span><strong>Response</strong> (return value)</span>
        </div>
        <div class="legend-item">
          <svg width="60" height="30">
            <rect x="5" y="5" width="50" height="20" rx="5" fill="#3b82f6" opacity="0.3" />
          </svg>
          <span><strong>Activation</strong> (processing)</span>
        </div>
        <div class="legend-item">
          <svg width="60" height="20">
            <line x1="5" y1="10" x2="55" y2="10" stroke="#cbd5e1" stroke-width="2" stroke-dasharray="5,5" />
          </svg>
          <span><strong>Lifeline</strong></span>
        </div>
      </div>
    </div>

    <script>
      const svgContainer = document.getElementById('svgContainer');
      const svg = svgContainer.querySelector('svg');
      const zoomLevelDisplay = document.getElementById('zoomLevel');

      let scale = 1;
      let translateX = 0;
      let translateY = 0;
      let isDragging = false;
      let startX = 0;
      let startY = 0;
      let initialWidth, initialHeight;

      // Initialize and center on load
      window.addEventListener('load', () => {{
        // Get SVG's natural dimensions
        initialWidth = parseFloat(svg.getAttribute('width')) || svg.viewBox.baseVal.width || 800;
        initialHeight = parseFloat(svg.getAttribute('height')) || svg.viewBox.baseVal.height || 600;

        const containerRect = svgContainer.getBoundingClientRect();

        // Calculate scale to fit
        const scaleToFitX = (containerRect.width - 40) / initialWidth;
        const scaleToFitY = (containerRect.height - 40) / initialHeight;
        const initialScale = Math.min(scaleToFitX, scaleToFitY, 1) * 0.9;

        scale = initialScale;

        // Start with no translation (flexbox centers it)
        translateX = 0;
        translateY = 0;

        updateTransform();
      }});

      function constrainBounds() {{
        // No constraints - allow free panning in all directions
        // User can pan completely out of view if needed
      }}

      function updateTransform() {{
        svg.style.transform = `translate(${{translateX}}px, ${{translateY}}px) scale(${{scale}})`;
        svg.style.transformOrigin = 'center center';
        zoomLevelDisplay.textContent = Math.round(scale * 100) + '%';
      }}

      // Mouse wheel zoom with Ctrl key
      svgContainer.addEventListener('wheel', (e) => {{
        if (e.ctrlKey) {{
          e.preventDefault();

          // Get mouse position relative to container
          const containerRect = svgContainer.getBoundingClientRect();
          const mouseX = e.clientX - containerRect.left;
          const mouseY = e.clientY - containerRect.top;

          // Get SVG's current position and center
          const svgRect = svg.getBoundingClientRect();
          const svgCenterX = svgRect.left - containerRect.left + svgRect.width / 2;
          const svgCenterY = svgRect.top - containerRect.top + svgRect.height / 2;

          // Calculate mouse position relative to SVG center
          const mouseRelativeX = mouseX - svgCenterX;
          const mouseRelativeY = mouseY - svgCenterY;

          // Zoom in or out
          const delta = e.deltaY > 0 ? 0.9 : 1.1;
          const oldScale = scale;
          const newScale = Math.min(Math.max(scale * delta, 0.1), 10);

          // Calculate how much to adjust translation to keep mouse point fixed
          const scaleDiff = newScale - oldScale;
          translateX -= mouseRelativeX * (scaleDiff / oldScale);
          translateY -= mouseRelativeY * (scaleDiff / oldScale);
          scale = newScale;

          updateTransform();
        }}
      }}, {{ passive: false }});

      // Drag to pan
      svgContainer.addEventListener('mousedown', (e) => {{
        isDragging = true;
        startX = e.clientX - translateX;
        startY = e.clientY - translateY;
        svgContainer.style.cursor = 'grabbing';
      }});

      document.addEventListener('mousemove', (e) => {{
        if (isDragging) {{
          translateX = e.clientX - startX;
          translateY = e.clientY - startY;
          updateTransform();
        }}
      }});

      document.addEventListener('mouseup', () => {{
        isDragging = false;
        svgContainer.style.cursor = 'grab';
      }});

      // Prevent text selection while dragging
      svgContainer.addEventListener('selectstart', (e) => {{
        if (isDragging) e.preventDefault();
      }});

      function resetView() {{
        const containerRect = svgContainer.getBoundingClientRect();

        // Recalculate scale to fit
        const scaleToFitX = (containerRect.width - 40) / initialWidth;
        const scaleToFitY = (containerRect.height - 40) / initialHeight;
        scale = Math.min(scaleToFitX, scaleToFitY, 1) * 0.9;

        // Reset to center position (flexbox handles centering)
        translateX = 0;
        translateY = 0;

        updateTransform();
      }}

      function exportSVG() {{
        const svgData = svg.outerHTML;
        const blob = new Blob([svgData], {{ type: 'image/svg+xml' }});
        const url = URL.createObjectURL(blob);
        const link = document.createElement('a');
        link.href = url;
        link.download = '{title.replace(" ", "_")}_sequence_diagram.svg';
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
        URL.revokeObjectURL(url);
      }}

      function exportPNG() {{
        const svgData = new XMLSerializer().serializeToString(svg);
        const canvas = document.createElement('canvas');
        const ctx = canvas.getContext('2d');
        const img = new Image();

        const svgBlob = new Blob([svgData], {{ type: 'image/svg+xml;charset=utf-8' }});
        const url = URL.createObjectURL(svgBlob);

        img.onload = function() {{
          canvas.width = img.width * 2;
          canvas.height = img.height * 2;
          ctx.scale(2, 2);
          ctx.fillStyle = 'white';
          ctx.fillRect(0, 0, canvas.width, canvas.height);
          ctx.drawImage(img, 0, 0);

          canvas.toBlob(function(blob) {{
            const link = document.createElement('a');
            link.href = URL.createObjectURL(blob);
            link.download = '{title.replace(" ", "_")}_sequence_diagram.png';
            document.body.appendChild(link);
            link.click();
            document.body.removeChild(link);
            URL.revokeObjectURL(url);
          }});
        }};

        img.src = url;
      }}
    </script>
  </body>
</html>"""


def parse_flowchart_steps(description: str) -> list:
    """Parse flowchart description into nodes with types"""
    import re

    lines = [line.strip().lstrip('- •*').strip() for line in description.split('\n') if line.strip()]

    nodes = []
    step_counter = 1

    for idx, line in enumerate(lines):
        if not line or len(line) < 3:
            continue

        # Determine node type based on keywords and patterns
        node_type = 'process'  # default
        text = line
        tooltip = ''
        is_decision = False

        # Check if it's a decision (ends with ? or contains yes/no)
        if '?' in line or '(yes/no)' in line.lower():
            node_type = 'decision'
            is_decision = True
            text = line.replace('?', '?').replace('(yes/no)', '').replace('(Yes/No)', '').strip()
            tooltip = 'Decision point'
        # Check if it's the first line (start)
        elif idx == 0:
            node_type = 'start-end'
            tooltip = 'Start of process'
        # Check if it's the last line or contains "complete", "end", "closed"
        elif idx == len(lines) - 1 or any(word in line.lower() for word in ['complete', 'end', 'closed', 'finish']):
            node_type = 'start-end'
            tooltip = 'End of process'
        # Check for escalation keywords
        elif any(word in line.lower() for word in ['escalate', 'elevate', 'reassign']):
            node_type = 'escalation'
            tooltip = 'Escalation step'
        # Check for action keywords
        elif any(word in line.lower() for word in ['route', 'assign', 'resolve', 'provide', 'close', 'deploy', 'test', 'verify']):
            node_type = 'action'
            tooltip = 'Action step'
        # Otherwise it's a process
        else:
            node_type = 'process'
            tooltip = 'Process step'

        # Check if next line(s) are yes/no branches
        branches = None
        if is_decision and idx + 1 < len(lines):
            # Look for "if yes:" or "if no:" patterns in next lines
            yes_branch = []
            no_branch = []

            j = idx + 1
            current_branch = None
            while j < len(lines):
                next_line = lines[j].lower()
                if 'if yes:' in next_line or next_line.startswith('yes:'):
                    current_branch = 'yes'
                    j += 1
                    continue
                elif 'if no:' in next_line or next_line.startswith('no:'):
                    current_branch = 'no'
                    j += 1
                    continue
                elif '?' in lines[j]:  # Another decision, stop
                    break

                if current_branch == 'yes':
                    yes_branch.append(lines[j])
                elif current_branch == 'no':
                    no_branch.append(lines[j])
                else:
                    break

                j += 1

            if yes_branch or no_branch:
                branches = {'yes': yes_branch, 'no': no_branch}

        nodes.append({
            'step': step_counter,
            'type': node_type,
            'text': text,
            'tooltip': tooltip,
            'is_decision': is_decision,
            'branches': branches
        })

        step_counter += 1

    return nodes


def generate_flowchart_html(title: str, description: str) -> str:
    """Generate beautiful custom flowchart HTML with branching support"""
    lines = [line.strip().lstrip('- •*').strip() for line in description.split('\n') if line.strip() and len(line.strip()) > 2]

    html_nodes = []
    i = 0
    step_counter = 1

    while i < len(lines):
        line = lines[i]

        # Determine node type
        node_type = 'process'
        tooltip = 'Process step'
        is_decision = '?' in line or '(yes/no)' in line.lower()

        if is_decision:
            node_type = 'decision'
            tooltip = 'Decision point'
            line = line.replace('?', '?').replace('(yes/no)', '').replace('(Yes/No)', '').strip()
        elif i == 0:
            node_type = 'start-end'
            tooltip = 'Start of process'
        elif i == len(lines) - 1 or any(word in line.lower() for word in ['complete', 'end', 'closed', 'finish']):
            node_type = 'start-end'
            tooltip = 'End of process'
        elif any(word in line.lower() for word in ['escalate', 'elevate', 'reassign']):
            node_type = 'escalation'
            tooltip = 'Escalation step'
        elif any(word in line.lower() for word in ['route', 'assign', 'resolve', 'provide', 'close', 'deploy', 'test', 'verify']):
            node_type = 'action'
            tooltip = 'Action step'

        # Add node
        html_nodes.append(f'''
        <div class="node">
          <div class="box {node_type}" data-step="{step_counter}">
            {line}
            <div class="tooltip">{tooltip}</div>
          </div>
        </div>''')

        step_counter += 1
        i += 1

        # Check for branches after decision
        if is_decision and i < len(lines):
            yes_steps = []
            no_steps = []
            branch_mode = None

            # Collect branch steps
            while i < len(lines):
                next_line = lines[i]
                lower_line = next_line.lower()

                if 'if yes:' in lower_line or lower_line.startswith('yes:'):
                    branch_mode = 'yes'
                    # Extract content after "if yes:" or "yes:" on the same line (case-insensitive)
                    if 'if yes:' in lower_line:
                        idx = lower_line.find('if yes:')
                        content = next_line[idx + 8:].strip()  # 8 = len('if yes:')
                        if content:
                            yes_steps.append(content)
                    elif lower_line.startswith('yes:'):
                        content = next_line[4:].strip()  # 4 = len('yes:')
                        if content:
                            yes_steps.append(content)
                    i += 1
                    continue
                elif 'if no:' in lower_line or lower_line.startswith('no:'):
                    branch_mode = 'no'
                    # Extract content after "if no:" or "no:" on the same line (case-insensitive)
                    if 'if no:' in lower_line:
                        idx = lower_line.find('if no:')
                        content = next_line[idx + 7:].strip()  # 7 = len('if no:')
                        if content:
                            no_steps.append(content)
                    elif lower_line.startswith('no:'):
                        content = next_line[3:].strip()  # 3 = len('no:')
                        if content:
                            no_steps.append(content)
                    i += 1
                    continue
                elif '?' in next_line:  # Another decision
                    break
                elif not branch_mode:  # No branch keywords found
                    break

                # Add to appropriate branch
                if branch_mode == 'yes':
                    yes_steps.append(next_line)
                elif branch_mode == 'no':
                    no_steps.append(next_line)

                i += 1

            # Render branches if found
            if yes_steps or no_steps:
                html_nodes.append('<div class="split">')

                # Yes branch
                html_nodes.append('<div class="branch">')
                html_nodes.append('<div class="label">YES</div>')
                if yes_steps:  # Only render connector and nodes if branch has content
                    html_nodes.append('<div class="connector"></div>')
                    for idx, yes_step in enumerate(yes_steps):
                        y_type = 'action' if any(w in yes_step.lower() for w in ['close', 'provide', 'resolve']) else 'process'
                        y_tooltip = 'Action step' if y_type == 'action' else 'Process step'
                        html_nodes.append(f'''
                    <div class="node">
                      <div class="box {y_type}" data-step="{step_counter}">
                        {yes_step}
                        <div class="tooltip">{y_tooltip}</div>
                      </div>
                    </div>''')
                        step_counter += 1
                        # Add connector after every node EXCEPT the last one
                        if idx < len(yes_steps) - 1:
                            html_nodes.append('<div class="connector"></div>')
                html_nodes.append('</div>')

                # No branch
                html_nodes.append('<div class="branch">')
                html_nodes.append('<div class="label">NO</div>')
                if no_steps:  # Only render connector and nodes if branch has content
                    html_nodes.append('<div class="connector"></div>')
                    for idx, no_step in enumerate(no_steps):
                        n_type = 'escalation' if any(w in no_step.lower() for w in ['escalate', 'elevate']) else 'process'
                        n_tooltip = 'Escalation step' if n_type == 'escalation' else 'Process step'
                        html_nodes.append(f'''
                    <div class="node">
                      <div class="box {n_type}" data-step="{step_counter}">
                        {no_step}
                        <div class="tooltip">{n_tooltip}</div>
                      </div>
                    </div>''')
                        step_counter += 1
                        # Add connector after every node EXCEPT the last one
                        if idx < len(no_steps) - 1:
                            html_nodes.append('<div class="connector"></div>')
                html_nodes.append('</div>')

                html_nodes.append('</div>')
                # Add regular connector after split to continue flow (no horizontal line)
                if i < len(lines):
                    html_nodes.append('<div class="connector"></div>')
            else:
                html_nodes.append('<div class="connector"></div>')
        else:
            if i < len(lines):
                html_nodes.append('<div class="connector"></div>')

    html_content = '\n'.join(html_nodes)

    return f'''<!doctype html>
<html lang="en">
<head>
  <meta charset="UTF-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1.0"/>
  <title>{title}</title>
  <style>
    * {{ margin: 0; padding: 0; box-sizing: border-box; }}

    body {{
      font-family: "Segoe UI", Tahoma, Geneva, Verdana, sans-serif;
      background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
      min-height: 100vh;
      padding: 20px;
      display: flex;
      flex-direction: column;
      align-items: center;
    }}

    .header {{
      text-align: center;
      color: white;
      margin-bottom: 30px;
      animation: fadeIn 0.8s ease-in;
    }}

    .header h1 {{
      font-size: 2.5em;
      margin-bottom: 10px;
      text-shadow: 2px 2px 4px rgba(0,0,0,0.3);
    }}

    .header p {{ font-size: 1.1em; opacity: 0.95; }}

    .controls {{
      margin-bottom: 20px;
      display: flex;
      gap: 15px;
      flex-wrap: wrap;
      justify-content: center;
    }}

    .btn {{
      background: white;
      color: #667eea;
      border: none;
      padding: 12px 24px;
      border-radius: 25px;
      cursor: pointer;
      font-size: 1em;
      font-weight: 600;
      transition: all 0.3s ease;
      box-shadow: 0 4px 6px rgba(0,0,0,0.1);
    }}

    .btn:hover {{
      transform: translateY(-2px);
      box-shadow: 0 6px 12px rgba(0,0,0,0.2);
      background: #f0f0f0;
    }}

    .flowchart-container {{
      background: white;
      border-radius: 15px;
      padding: 40px;
      box-shadow: 0 20px 60px rgba(0,0,0,0.3);
      max-width: 1400px;
      width: 100%;
      animation: slideUp 0.8s ease-out;
    }}

    .flowchart-viewport {{
      overflow: hidden;
      cursor: grab;
      border-radius: 10px;
      background: white;
      width: 100%;
      height: 75vh;
      min-height: 500px;
      position: relative;
    }}

    .flowchart-viewport:active {{
      cursor: grabbing;
    }}

    .flowchart-viewport.scroll-mode {{
      overflow-y: auto;
      overflow-x: auto;
      cursor: default;
    }}

    .flowchart-inner {{
      width: 100%;
      height: 100%;
      display: flex;
      align-items: center;
      justify-content: center;
      position: relative;
    }}

    .flowchart {{
      transform-origin: center center;
      flex-shrink: 0;
      position: relative;
      display: flex;
      flex-direction: column;
      align-items: center;
      width: 900px;
    }}

    .node {{ margin: 15px 0; position: relative; animation: fadeIn 0.5s ease-in; }}

    .box {{
      padding: 20px 30px;
      border-radius: 10px;
      box-shadow: 0 4px 8px rgba(0,0,0,0.1);
      font-size: 1em;
      font-weight: 500;
      text-align: center;
      min-width: 280px;
      max-width: 400px;
      transition: transform 0.3s ease, box-shadow 0.3s ease, outline 0.15s ease;
      cursor: pointer;
      position: relative;
    }}

    .box:hover {{
      transform: scale(1.05);
      box-shadow: 0 6px 16px rgba(0,0,0,0.2);
    }}

    .start-end {{
      background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
      color: white;
      border-radius: 50px;
      font-weight: 600;
    }}

    .process {{
      background: linear-gradient(135deg, #f093fb 0%, #f5576c 100%);
      color: white;
    }}

    .decision {{
      background: linear-gradient(135deg, #4facfe 0%, #00f2fe 100%);
      color: white;
      clip-path: polygon(50% 0%, 100% 50%, 50% 100%, 0% 50%);
      padding: 30px 40px;
      min-width: 320px;
    }}

    .action {{
      background: linear-gradient(135deg, #43e97b 0%, #38f9d7 100%);
      color: white;
    }}

    .escalation {{
      background: linear-gradient(135deg, #fa709a 0%, #fee140 100%);
      color: white;
    }}

    .connector {{
      width: 3px;
      height: 40px;
      background: linear-gradient(180deg, #667eea 0%, #764ba2 100%);
      margin: 0 auto;
      position: relative;
    }}

    .connector::after {{
      content: "";
      position: absolute;
      bottom: -8px;
      left: 50%;
      transform: translateX(-50%);
      width: 0;
      height: 0;
      border-left: 8px solid transparent;
      border-right: 8px solid transparent;
      border-top: 12px solid #764ba2;
    }}

    .tooltip {{
      position: absolute;
      background: rgba(0,0,0,0.9);
      color: white;
      padding: 8px 12px;
      border-radius: 6px;
      font-size: 0.85em;
      white-space: nowrap;
      opacity: 0;
      pointer-events: none;
      transition: opacity 0.3s ease;
      bottom: 100%;
      left: 50%;
      transform: translateX(-50%);
      margin-bottom: 10px;
      z-index: 1000;
    }}

    .box:hover .tooltip {{ opacity: 1; }}

    .split {{
      display: flex;
      flex-direction: row;
      flex-wrap: nowrap;
      justify-content: center;
      align-items: flex-start;
      gap: 60px;
      margin: 20px 0;
      width: 900px;
    }}

    .branch {{
      display: flex;
      flex-direction: column;
      align-items: center;
      flex: 0 0 360px;
      width: 360px;
    }}

    .label {{
      background: white;
      color: #667eea;
      padding: 8px 16px;
      border-radius: 20px;
      font-weight: 600;
      font-size: 0.9em;
      margin: 10px 0;
      box-shadow: 0 2px 4px rgba(0,0,0,0.1);
      border: 2px solid #667eea;
    }}

    .merge-connector {{
      width: 100%;
      height: 3px;
      background: linear-gradient(90deg, #667eea 0%, #764ba2 100%);
      position: relative;
      margin: 20px 0;
    }}

    .legend {{
      display: flex;
      gap: 20px;
      margin-top: 30px;
      flex-wrap: wrap;
      justify-content: center;
      padding-top: 20px;
      border-top: 2px solid #e0e0e0;
    }}

    .legend-item {{
      display: flex;
      align-items: center;
      gap: 10px;
      font-size: 0.9em;
      color: #555;
    }}

    .legend-box {{
      width: 30px;
      height: 30px;
      border-radius: 6px;
      box-shadow: 0 2px 4px rgba(0,0,0,0.1);
    }}

    @keyframes fadeIn {{ from {{ opacity: 0; }} to {{ opacity: 1; }} }}

    @keyframes slideUp {{
      from {{ opacity: 0; transform: translateY(30px); }}
      to {{ opacity: 1; transform: translateY(0); }}
    }}

    .highlight {{
      outline: 4px solid #FFD700 !important;
      outline-offset: 3px;
      box-shadow: 0 0 20px rgba(255, 215, 0, 0.8), 0 0 40px rgba(255, 165, 0, 0.5) !important;
      animation: highlightPulse 0.8s ease-in-out !important;
    }}

    @keyframes highlightPulse {{
      0%   {{ transform: scale(1); }}
      30%  {{ transform: scale(1.12); }}
      60%  {{ transform: scale(1.06); }}
      100% {{ transform: scale(1.08); }}
    }}

    .highlight-active {{
      outline: 4px solid #FFD700 !important;
      outline-offset: 3px;
      box-shadow: 0 0 20px rgba(255, 215, 0, 0.7), 0 0 40px rgba(255, 165, 0, 0.4) !important;
      transform: scale(1.06) !important;
    }}

    .zoom-info {{
      position: fixed;
      bottom: 20px;
      right: 20px;
      background: rgba(102, 126, 234, 0.95);
      color: white;
      padding: 12px 20px;
      border-radius: 8px;
      font-size: 14px;
      font-weight: 600;
      z-index: 1000;
      box-shadow: 0 4px 12px rgba(0,0,0,0.3);
      pointer-events: none;
    }}

    .scroll-hint {{
      position: fixed;
      bottom: 20px;
      left: 20px;
      background: rgba(102, 126, 234, 0.95);
      color: white;
      padding: 12px 20px;
      border-radius: 8px;
      font-size: 13px;
      font-weight: 600;
      z-index: 1000;
      box-shadow: 0 4px 12px rgba(0,0,0,0.3);
      pointer-events: none;
      transition: opacity 0.4s ease;
    }}

    .help-text {{
      text-align: center;
      color: white;
      font-size: 14px;
      margin-bottom: 20px;
      opacity: 0.9;
    }}

    @media (max-width: 768px) {{
      .header h1 {{ font-size: 1.8em; }}
      .flowchart-container {{ padding: 20px; }}
      .split {{ flex-direction: column; gap: 20px; }}
      .box {{ min-width: 220px; font-size: 0.9em; padding: 15px 20px; }}
    }}
  </style>
</head>
<body>
  <div class="header">
    <h1>📊 {title}</h1>
    <p>Interactive Process Flowchart</p>
  </div>

  <p class="help-text">
    💡 <strong>Ctrl + Mouse Wheel</strong> to zoom &nbsp;|&nbsp; <strong>Mouse Wheel</strong> to scroll &nbsp;|&nbsp; <strong>Click & Drag</strong> to pan
  </p>

  <div class="controls">
    <button class="btn" onclick="resetAnimation()">🔄 Reset Animation</button>
    <button class="btn" onclick="highlightPath()">⚡ Highlight Flow</button>
    <button class="btn" onclick="resetView()">↺ Reset View</button>
    <button class="btn" onclick="exportPNG()">📷 Export PNG</button>
  </div>

  <div class="flowchart-container">
    <div class="flowchart-viewport" id="flowchartViewport">
      <div class="flowchart-inner" id="flowchartInner">
        <div class="flowchart" id="flowchart">
          {html_content}
        </div>
      </div>
    </div>

    <div class="legend">
      <div class="legend-item">
        <div class="legend-box" style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);"></div>
        <span>Start/End</span>
      </div>
      <div class="legend-item">
        <div class="legend-box" style="background: linear-gradient(135deg, #f093fb 0%, #f5576c 100%);"></div>
        <span>Process</span>
      </div>
      <div class="legend-item">
        <div class="legend-box" style="background: linear-gradient(135deg, #4facfe 0%, #00f2fe 100%);"></div>
        <span>Decision</span>
      </div>
      <div class="legend-item">
        <div class="legend-box" style="background: linear-gradient(135deg, #43e97b 0%, #38f9d7 100%);"></div>
        <span>Action</span>
      </div>
      <div class="legend-item">
        <div class="legend-box" style="background: linear-gradient(135deg, #fa709a 0%, #fee140 100%);"></div>
        <span>Escalation</span>
      </div>
    </div>
  </div>

  <div class="zoom-info" id="zoomLevel">100%</div>
  <div class="scroll-hint" id="scrollHint" style="opacity:0;">🖱️ Scroll to navigate</div>

  <script>
    const viewport   = document.getElementById('flowchartViewport');
    const inner      = document.getElementById('flowchartInner');
    const flowchart  = document.getElementById('flowchart');
    const zoomDisplay= document.getElementById('zoomLevel');
    const scrollHint = document.getElementById('scrollHint');

    let scale      = 1;
    let translateX = 0;
    let translateY = 0;
    let isDragging = false;
    let startX = 0, startY = 0;
    let initialWidth, initialHeight;

    let scrollHintTimer;
    function showScrollHint() {{
      scrollHint.style.opacity = '1';
      clearTimeout(scrollHintTimer);
      scrollHintTimer = setTimeout(() => {{ scrollHint.style.opacity = '0'; }}, 2000);
    }}

    function updateTransform() {{
      flowchart.style.transform = `translate(${{translateX}}px, ${{translateY}}px) scale(${{scale}})`;
      flowchart.style.transformOrigin = 'center center';
      zoomDisplay.textContent = Math.round(scale * 100) + '%';
    }}

    window.addEventListener('load', () => {{
      flowchart.style.transform = 'none';
      const vp = viewport.getBoundingClientRect();

      initialWidth  = 900;
      initialHeight = flowchart.getBoundingClientRect().height;

      const sx = (vp.width  - 40) / initialWidth;
      const sy = (vp.height - 40) / initialHeight;
      scale = Math.min(sx, sy, 1) * 0.9;
      translateX = 0;
      translateY = 0;
      updateTransform();

      setTimeout(() => {{
        const first = document.querySelector('[data-step="1"]');
        if (first) {{
          first.classList.add('highlight-active');
          setTimeout(() => first.classList.remove('highlight-active'), 2000);
        }}
      }}, 500);
    }});

    viewport.addEventListener('wheel', (e) => {{
      if (e.ctrlKey) {{
        e.preventDefault();

        const vpRect = viewport.getBoundingClientRect();
        const fcRect = flowchart.getBoundingClientRect();

        const mouseX = e.clientX - vpRect.left;
        const mouseY = e.clientY - vpRect.top;

        const centerX = fcRect.left - vpRect.left + fcRect.width  / 2;
        const centerY = fcRect.top  - vpRect.top  + fcRect.height / 2;

        const relX = mouseX - centerX;
        const relY = mouseY - centerY;

        const delta    = e.deltaY > 0 ? 0.9 : 1.1;
        const oldScale = scale;
        const newScale = Math.min(Math.max(scale * delta, 0.1), 10);

        const scaleDiff = newScale - oldScale;
        translateX -= relX * (scaleDiff / oldScale);
        translateY -= relY * (scaleDiff / oldScale);
        scale = newScale;
        updateTransform();

      }} else {{
        e.preventDefault();
        const step = 60;

        if (e.shiftKey) {{
          translateX -= (e.deltaY > 0 ? step : -step);
        }} else {{
          translateY -= (e.deltaY > 0 ? step : -step);
        }}
        updateTransform();
        showScrollHint();
      }}
    }}, {{ passive: false }});

    viewport.addEventListener('mousedown', (e) => {{
      if (e.target.closest('.box')) return;
      isDragging = true;
      startX = e.clientX - translateX;
      startY = e.clientY - translateY;
      viewport.style.cursor = 'grabbing';
    }});

    document.addEventListener('mousemove', (e) => {{
      if (!isDragging) return;
      translateX = e.clientX - startX;
      translateY = e.clientY - startY;
      updateTransform();
    }});

    document.addEventListener('mouseup', () => {{
      isDragging = false;
      viewport.style.cursor = 'grab';
    }});

    viewport.addEventListener('selectstart', (e) => {{
      if (isDragging) e.preventDefault();
    }});

    function resetView() {{
      const vpRect = viewport.getBoundingClientRect();
      const sx = (vpRect.width  - 40) / initialWidth;
      const sy = (vpRect.height - 40) / initialHeight;
      scale = Math.min(sx, sy, 1) * 0.9;
      translateX = 0;
      translateY = 0;
      updateTransform();
    }}

    function resetAnimation() {{
      document.querySelectorAll('.box').forEach(box => {{
        box.classList.remove('highlight', 'highlight-active');
      }});
    }}

    let highlightRunning = false;
    let highlightTimeouts = [];

    function highlightPath() {{
      highlightTimeouts.forEach(t => clearTimeout(t));
      highlightTimeouts = [];
      resetAnimation();
      highlightRunning = true;

      const boxes = Array.from(document.querySelectorAll('[data-step]'))
        .sort((a, b) => {{
          const stepA = parseInt(a.dataset.step);
          const stepB = parseInt(b.dataset.step);
          return stepA - stepB;
        }});

      const DELAY_BETWEEN = 500;
      const HOLD_DURATION = 400;

      boxes.forEach((box, idx) => {{
        const t1 = setTimeout(() => {{
          if (idx > 0) {{
            boxes[idx - 1].classList.remove('highlight-active');
          }}

          box.classList.add('highlight');
          box.classList.add('highlight-active');

          scrollToBox(box);

        }}, idx * DELAY_BETWEEN);

        highlightTimeouts.push(t1);
      }});

      const totalTime = boxes.length * DELAY_BETWEEN + HOLD_DURATION;
      const tEnd = setTimeout(() => {{
        if (boxes.length > 0) {{
          boxes[boxes.length - 1].classList.remove('highlight-active');
        }}
        highlightRunning = false;
      }}, totalTime);
      highlightTimeouts.push(tEnd);
    }}

    function scrollToBox(box) {{
      const vpRect  = viewport.getBoundingClientRect();
      const boxRect = box.getBoundingClientRect();

      const boxCenterX = boxRect.left - vpRect.left + boxRect.width  / 2;
      const boxCenterY = boxRect.top  - vpRect.top  + boxRect.height / 2;

      const diffX = boxCenterX - vpRect.width  / 2;
      const diffY = boxCenterY - vpRect.height / 2;

      translateX -= diffX;
      translateY -= diffY;
      updateTransform();
    }}

    document.querySelectorAll('.box').forEach(box => {{
      box.addEventListener('click', function () {{
        this.classList.toggle('highlight-active');
      }});
    }});

    function exportPNG() {{
      function captureAndDownload() {{
        html2canvas(viewport, {{
          scale: 2,
          backgroundColor: '#ffffff',
          logging: false,
          useCORS: true
        }}).then(canvas => {{
          canvas.toBlob(function (blob) {{
            const link = document.createElement('a');
            link.href = URL.createObjectURL(blob);
            link.download = '{title.replace(" ", "_")}_flowchart.png';
            document.body.appendChild(link);
            link.click();
            document.body.removeChild(link);
            URL.revokeObjectURL(link.href);
          }});
        }});
      }}

      if (typeof html2canvas === 'undefined') {{
        const script = document.createElement('script');
        script.src = 'https://cdnjs.cloudflare.com/ajax/libs/html2canvas/1.4.1/html2canvas.min.js';
        script.onload = captureAndDownload;
        document.head.appendChild(script);
      }} else {{
        captureAndDownload();
      }}
    }}
  </script>

  <script src="https://cdnjs.cloudflare.com/ajax/libs/html2canvas/1.4.1/html2canvas.min.js"></script>
</body>
</html>'''

def fix_mermaid_syntax(mermaid_code: str) -> str:
    """
    Automatically fix common Mermaid syntax errors by adding quotes where needed.
    Handles text in square brackets [text] and curly braces {text}.
    """
    import re

    # Fix square brackets: A[Text here] -> A["Text here"]
    # Pattern: node_id followed by [ followed by text without quotes, ending with ]
    # Only fix if text doesn't already start with quote
    def fix_square_brackets(match):
        node_id = match.group(1)
        text = match.group(2)
        # If already quoted, return as is
        if text.startswith('"') and text.endswith('"'):
            return match.group(0)
        # Add quotes
        return f'{node_id}["{text}"]'

    # Pattern: word boundary, node ID (letters/numbers), [, content, ]
    mermaid_code = re.sub(
        r'(\b[A-Za-z0-9]+)\[([^\]]+)\]',
        fix_square_brackets,
        mermaid_code
    )

    # Fix curly braces: A{Text here?} -> A{"Text here?"}
    # Pattern: node_id followed by { followed by text without quotes, ending with }
    def fix_curly_braces(match):
        node_id = match.group(1)
        text = match.group(2)
        # If already quoted, return as is
        if text.startswith('"') and text.endswith('"'):
            return match.group(0)
        # Add quotes
        return f'{node_id}{{"{text}"}}'

    # Pattern: word boundary, node ID (letters/numbers), {, content, }
    mermaid_code = re.sub(
        r'(\b[A-Za-z0-9]+)\{([^\}]+)\}',
        fix_curly_braces,
        mermaid_code
    )

    return mermaid_code

def generate_mermaid_html(diagram_code: str, diagram_type: str) -> str:
    """Generate self-contained Mermaid.js HTML with zoom controls"""
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Mermaid Diagram - {diagram_type}</title>
    <script src="https://cdn.jsdelivr.net/npm/mermaid@10.6.1/dist/mermaid.min.js"></script>
    <style>
        body {{
            margin: 0;
            padding: 40px;
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: #f5f5f5;
            display: flex;
            flex-direction: column;
            align-items: center;
            min-height: 100vh;
        }}
        .container {{
            background: white;
            padding: 30px;
            border-radius: 12px;
            box-shadow: 0 4px 12px rgba(0,0,0,0.1);
            max-width: 1200px;
            width: 100%;
        }}
        .controls {{
            margin-bottom: 20px;
            display: flex;
            gap: 10px;
            flex-wrap: wrap;
            align-items: center;
        }}
        button {{
            padding: 10px 20px;
            border: none;
            border-radius: 6px;
            background: #6965db;
            color: white;
            cursor: pointer;
            font-size: 14px;
            font-weight: 500;
        }}
        button:hover {{
            background: #5753c5;
        }}
        .zoom-controls {{
            display: flex;
            gap: 5px;
            align-items: center;
            margin-left: auto;
        }}
        .zoom-level {{
            padding: 8px 12px;
            background: #f0f0f0;
            border-radius: 4px;
            font-size: 13px;
            font-weight: 600;
            color: #333;
            min-width: 60px;
            text-align: center;
        }}
        #diagram-wrapper {{
            overflow: auto;
            height: 80vh;
            width: 100%;
            border: 1px solid #e0e0e0;
            border-radius: 8px;
            background: #fafafa;
            position: relative;
            cursor: grab;
        }}
        #diagram-wrapper.dragging {{
            cursor: grabbing;
            user-select: none;
        }}
        #diagram-container {{
            display: inline-block;
            min-width: 100%;
            min-height: 100%;
        }}
        #diagram {{
            transform-origin: top left;
            transition: transform 0.2s ease;
            display: inline-block;
            padding: 60px;
        }}
        #diagram svg {{
            display: block;
        }}
        .code-panel {{
            background: #f8f9fa;
            padding: 20px;
            border-radius: 8px;
            margin-top: 20px;
            display: none;
        }}
        .code-panel.show {{
            display: block;
        }}
        pre {{
            margin: 0;
            overflow-x: auto;
        }}
        code {{
            font-family: 'Monaco', 'Menlo', monospace;
            font-size: 13px;
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="controls">
            <button onclick="exportSVG()">📷 Export SVG</button>
            <button onclick="exportPNG()">🖼️ Export PNG</button>
            <button onclick="toggleCode()">📝 Show/Hide Code</button>
            <div class="zoom-controls">
                <button onclick="zoomOut()">➖ Zoom Out</button>
                <div class="zoom-level" id="zoom-level">100%</div>
                <button onclick="zoomIn()">➕ Zoom In</button>
                <button onclick="resetZoom()">🔄 Reset</button>
            </div>
        </div>
        <div id="diagram-wrapper">
            <div id="diagram-container">
                <div id="diagram">
                    <pre class="mermaid">
{diagram_code}
                    </pre>
                </div>
            </div>
        </div>
        <div id="code-panel" class="code-panel">
            <strong>Mermaid Code:</strong>
            <pre><code>{diagram_code}</code></pre>
        </div>
    </div>

    <script>
        mermaid.initialize({{
            startOnLoad: true,
            theme: 'default',
            securityLevel: 'loose'
        }});

        let currentZoom = 1.0;
        const zoomStep = 0.1;
        const minZoom = 0.3;
        const maxZoom = 10.0;

        // Pan/drag variables
        let isDragging = false;
        let startX, startY, scrollLeft, scrollTop;

        function updateZoom(centerX, centerY) {{
            const diagram = document.getElementById('diagram');
            const container = document.getElementById('diagram-container');
            const wrapper = document.getElementById('diagram-wrapper');
            const svg = diagram.querySelector('svg');

            // If centerX and centerY provided, adjust scroll to keep that point centered
            if (centerX !== undefined && centerY !== undefined) {{
                const oldZoom = parseFloat(diagram.style.transform.replace(/[^0-9.]/g, '')) || 1;
                const zoomRatio = currentZoom / oldZoom;

                // Calculate the point relative to the diagram
                const rect = wrapper.getBoundingClientRect();
                const pointX = centerX - rect.left + wrapper.scrollLeft;
                const pointY = centerY - rect.top + wrapper.scrollTop;

                // Apply zoom transformation
                diagram.style.transform = `scale(${{currentZoom}})`;

                // Calculate new dimensions
                if (svg) {{
                    const svgWidth = svg.getBoundingClientRect().width / currentZoom;
                    const svgHeight = svg.getBoundingClientRect().height / currentZoom;
                    const padding = 60;

                    container.style.width = ((svgWidth + padding * 2) * currentZoom) + 'px';
                    container.style.height = ((svgHeight + padding * 2) * currentZoom) + 'px';
                }}

                // Adjust scroll to keep the point under cursor
                requestAnimationFrame(() => {{
                    wrapper.scrollLeft = pointX * zoomRatio - (centerX - rect.left);
                    wrapper.scrollTop = pointY * zoomRatio - (centerY - rect.top);
                }});
            }} else {{
                // Regular zoom update
                diagram.style.transform = `scale(${{currentZoom}})`;

                if (svg) {{
                    const svgWidth = svg.getBoundingClientRect().width / currentZoom;
                    const svgHeight = svg.getBoundingClientRect().height / currentZoom;
                    const padding = 60;

                    container.style.width = ((svgWidth + padding * 2) * currentZoom) + 'px';
                    container.style.height = ((svgHeight + padding * 2) * currentZoom) + 'px';
                }}
            }}

            document.getElementById('zoom-level').textContent = Math.round(currentZoom * 100) + '%';
        }}

        // Initialize zoom after mermaid renders
        setTimeout(() => {{
            updateZoom();
        }}, 500);

        function zoomIn() {{
            if (currentZoom < maxZoom) {{
                currentZoom = Math.min(maxZoom, currentZoom + zoomStep);
                updateZoom();
            }}
        }}

        function zoomOut() {{
            if (currentZoom > minZoom) {{
                currentZoom = Math.max(minZoom, currentZoom - zoomStep);
                updateZoom();
            }}
        }}

        function resetZoom() {{
            currentZoom = 1.0;
            updateZoom();
        }}

        // Ctrl + Scroll wheel zoom towards cursor, or regular scroll wheel to pan
        const diagramWrapper = document.getElementById('diagram-wrapper');
        diagramWrapper.addEventListener('wheel', (e) => {{
            if (e.ctrlKey || e.metaKey) {{
                // Ctrl/Cmd + Wheel: Zoom
                e.preventDefault();
                e.stopPropagation();

                const oldZoom = currentZoom;

                if (e.deltaY < 0) {{
                    // Scroll up - zoom in
                    if (currentZoom < maxZoom) {{
                        currentZoom = Math.min(maxZoom, currentZoom + zoomStep);
                    }}
                }} else {{
                    // Scroll down - zoom out
                    if (currentZoom > minZoom) {{
                        currentZoom = Math.max(minZoom, currentZoom - zoomStep);
                    }}
                }}

                // Update zoom centered on cursor position
                if (currentZoom !== oldZoom) {{
                    updateZoom(e.clientX, e.clientY);
                }}
            }}
            // When Ctrl is not pressed, let the default scroll behavior happen
            // The wrapper has overflow: auto, so it will scroll naturally
        }}, {{ passive: false }});

        // Pan/drag functionality
        const wrapper = document.getElementById('diagram-wrapper');

        wrapper.addEventListener('mousedown', (e) => {{
            // Only start drag if not clicking on a button or link
            if (e.target.tagName === 'BUTTON' || e.target.tagName === 'A') return;

            isDragging = true;
            wrapper.classList.add('dragging');
            startX = e.pageX - wrapper.offsetLeft;
            startY = e.pageY - wrapper.offsetTop;
            scrollLeft = wrapper.scrollLeft;
            scrollTop = wrapper.scrollTop;
        }});

        wrapper.addEventListener('mouseleave', () => {{
            if (isDragging) {{
                isDragging = false;
                wrapper.classList.remove('dragging');
            }}
        }});

        wrapper.addEventListener('mouseup', () => {{
            isDragging = false;
            wrapper.classList.remove('dragging');
        }});

        wrapper.addEventListener('mousemove', (e) => {{
            if (!isDragging) return;
            e.preventDefault();

            const x = e.pageX - wrapper.offsetLeft;
            const y = e.pageY - wrapper.offsetTop;
            const walkX = (x - startX) * 1.5; // Multiply for faster scroll
            const walkY = (y - startY) * 1.5;

            wrapper.scrollLeft = scrollLeft - walkX;
            wrapper.scrollTop = scrollTop - walkY;
        }});

        // Keyboard shortcuts
        document.addEventListener('keydown', (e) => {{
            if ((e.ctrlKey || e.metaKey) && e.key === '=') {{
                e.preventDefault();
                zoomIn();
            }} else if ((e.ctrlKey || e.metaKey) && e.key === '-') {{
                e.preventDefault();
                zoomOut();
            }} else if ((e.ctrlKey || e.metaKey) && e.key === '0') {{
                e.preventDefault();
                resetZoom();
            }}
        }});

        function toggleCode() {{
            document.getElementById('code-panel').classList.toggle('show');
        }}

        async function exportSVG() {{
            const svg = document.querySelector('#diagram svg');
            if (!svg) return;

            const svgData = svg.outerHTML;
            const blob = new Blob([svgData], {{ type: 'image/svg+xml' }});
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = 'mermaid-diagram.svg';
            a.click();
        }}

        async function exportPNG() {{
            const svg = document.querySelector('#diagram svg');
            if (!svg) return;

            const canvas = document.createElement('canvas');
            const ctx = canvas.getContext('2d');
            const svgData = new XMLSerializer().serializeToString(svg);
            const img = new Image();

            img.onload = () => {{
                canvas.width = img.width * 2;
                canvas.height = img.height * 2;
                ctx.scale(2, 2);
                ctx.drawImage(img, 0, 0);

                canvas.toBlob(blob => {{
                    const url = URL.createObjectURL(blob);
                    const a = document.createElement('a');
                    a.href = url;
                    a.download = 'mermaid-diagram.png';
                    a.click();
                }});
            }};

            img.src = 'data:image/svg+xml;base64,' + btoa(unescape(encodeURIComponent(svgData)));
        }}
    </script>
</body>
</html>"""

def generate_chartjs_html(chart_config: dict, title: str) -> str:
    """Generate self-contained Chart.js HTML"""
    config_json = json.dumps(chart_config)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title}</title>
    <script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
    <style>
        body {{
            margin: 0;
            padding: 40px;
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: #f5f5f5;
        }}
        .container {{
            max-width: 1200px;
            margin: 0 auto;
            background: white;
            padding: 30px;
            border-radius: 12px;
            box-shadow: 0 4px 12px rgba(0,0,0,0.1);
        }}
        h1 {{
            margin: 0 0 30px 0;
            color: #333;
            font-size: 24px;
        }}
        .chart-container {{
            position: relative;
            height: 400px;
            width: 100%;
        }}
        .controls {{
            margin-top: 20px;
            display: flex;
            gap: 10px;
        }}
        button {{
            padding: 10px 20px;
            border: none;
            border-radius: 6px;
            background: #6965db;
            color: white;
            cursor: pointer;
            font-size: 14px;
        }}
        button:hover {{
            background: #5753c5;
        }}
    </style>
</head>
<body>
    <div class="container">
        <h1>{title}</h1>
        <div class="chart-container">
            <canvas id="myChart"></canvas>
        </div>
        <div class="controls">
            <button onclick="exportImage()">📷 Export PNG</button>
            <button onclick="exportData()">📊 Export Data</button>
        </div>
    </div>

    <script>
        const config = {config_json};
        const ctx = document.getElementById('myChart').getContext('2d');
        const chart = new Chart(ctx, config);

        function exportImage() {{
            const url = chart.toBase64Image();
            const a = document.createElement('a');
            a.href = url;
            a.download = 'chart.png';
            a.click();
        }}

        function exportData() {{
            const data = chart.data;
            const dataStr = JSON.stringify(data, null, 2);
            const blob = new Blob([dataStr], {{ type: 'application/json' }});
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = 'chart-data.json';
            a.click();
        }}
    </script>
</body>
</html>"""

def generate_heatmap_html(plot_data: list, layout: dict, title: str) -> str:
    """Generate beautiful heatmap HTML with insights"""
    trace = plot_data[0]

    # Extract variables from x/y labels
    variables = trace.get('x', [])
    correlation_matrix = trace.get('z', [])

    # Generate insights based on correlation values
    insights = []
    if len(variables) >= 2 and len(correlation_matrix) >= 2:
        # Find strongest correlations (excluding diagonal)
        correlations = []
        for i in range(len(variables)):
            for j in range(len(variables)):
                if i != j and len(correlation_matrix[i]) > j:
                    correlations.append({
                        'var1': variables[i],
                        'var2': variables[j],
                        'value': correlation_matrix[i][j]
                    })

        # Sort by absolute value
        correlations.sort(key=lambda x: abs(x['value']), reverse=True)

        # Generate insights for top correlations
        icons = ['💰', '📊', '🎯', '🔄', '✨', '📈']
        for idx, corr in enumerate(correlations[:6]):
            strength = "very strong" if abs(corr['value']) >= 0.8 else "strong" if abs(corr['value']) >= 0.6 else "moderate" if abs(corr['value']) >= 0.4 else "weak"
            relationship = "positive" if corr['value'] > 0 else "negative"

            insight_text = f"<strong>{corr['var1']} & {corr['var2']}:</strong> "
            if abs(corr['value']) >= 0.8:
                insight_text += f"Very strong {relationship} correlation ({corr['value']:.2f}) indicates a direct relationship."
            elif abs(corr['value']) >= 0.6:
                insight_text += f"Strong {relationship} correlation ({corr['value']:.2f}) shows significant interdependence."
            elif abs(corr['value']) >= 0.4:
                insight_text += f"Moderate {relationship} correlation ({corr['value']:.2f}) suggests a notable connection."
            else:
                insight_text += f"Weak {relationship} correlation ({corr['value']:.2f}) indicates limited direct relationship."

            insights.append({
                'icon': icons[idx % len(icons)],
                'text': insight_text
            })

    # Build insights HTML
    insights_html = "\n".join([
        f'''<div class="insight-item">
          <div class="insight-icon">{insight['icon']}</div>
          <div>{insight['text']}</div>
        </div>''' for insight in insights[:4]  # Limit to 4 insights
    ])

    # Create annotations for each cell
    annotations_js = "["
    for i in range(len(variables)):
        for j in range(len(variables)):
            if len(correlation_matrix[i]) > j:
                value = correlation_matrix[i][j]
                annotations_js += f'''{{
                    x: "{variables[j]}",
                    y: "{variables[i]}",
                    text: {value:.2f},
                    font: {{
                        size: 16,
                        color: {'"white"' if value > 0.7 else '"#1e293b"'},
                        family: '-apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif',
                        weight: 600
                    }},
                    showarrow: false
                }},'''
    annotations_js += "]"

    variables_json = json.dumps(variables)
    matrix_json = json.dumps(correlation_matrix)

    return f"""<!doctype html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>{title}</title>
    <script src="https://cdnjs.cloudflare.com/ajax/libs/plotly.js/2.26.0/plotly.min.js"></script>
    <style>
      body {{
        margin: 0;
        padding: 20px;
        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
        background: linear-gradient(135deg, #1e3a8a 0%, #3b82f6 100%);
        min-height: 100vh;
      }}
      .container {{
        max-width: 1000px;
        margin: 0 auto;
        background: white;
        border-radius: 16px;
        padding: 40px;
        box-shadow: 0 20px 60px rgba(0, 0, 0, 0.3);
      }}
      h1 {{
        color: #1e293b;
        margin-top: 0;
        font-size: 32px;
        font-weight: 700;
        text-align: center;
      }}
      .subtitle {{
        color: #64748b;
        margin-bottom: 30px;
        font-size: 16px;
        text-align: center;
      }}
      #heatmap {{
        width: 100%;
        height: 600px;
        margin: 20px 0;
      }}
      .legend {{
        background: #f8fafc;
        border-radius: 12px;
        padding: 25px;
        margin-top: 30px;
      }}
      .legend-title {{
        font-size: 18px;
        font-weight: 700;
        color: #1e293b;
        margin-bottom: 15px;
      }}
      .legend-grid {{
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
        gap: 15px;
      }}
      .legend-item {{
        display: flex;
        align-items: center;
        gap: 10px;
      }}
      .legend-color {{
        width: 40px;
        height: 20px;
        border-radius: 4px;
        border: 1px solid #cbd5e1;
      }}
      .legend-text {{
        font-size: 14px;
        color: #475569;
      }}
      .insights {{
        background: linear-gradient(135deg, #1e3a8a 0%, #3b82f6 100%);
        border-radius: 12px;
        padding: 25px;
        margin-top: 20px;
        color: white;
      }}
      .insights-title {{
        font-size: 18px;
        font-weight: 700;
        margin-bottom: 15px;
      }}
      .insight-item {{
        display: flex;
        align-items: start;
        gap: 10px;
        margin-bottom: 12px;
        font-size: 14px;
        line-height: 1.6;
      }}
      .insight-icon {{
        flex-shrink: 0;
        width: 20px;
        height: 20px;
        background: rgba(255, 255, 255, 0.2);
        border-radius: 50%;
        display: flex;
        align-items: center;
        justify-content: center;
        font-weight: bold;
        margin-top: 2px;
      }}
    </style>
  </head>
  <body>
    <div class="container">
      <h1>{title}</h1>
      <p class="subtitle">
        Understanding the relationships between key performance indicators
      </p>

      <div id="heatmap"></div>

      <div class="legend">
        <div class="legend-title">Understanding Correlation Values</div>
        <div class="legend-grid">
          <div class="legend-item">
            <div class="legend-color" style="background: #0c4a6e"></div>
            <div class="legend-text">
              <strong>0.8 - 1.0:</strong> Very Strong
            </div>
          </div>
          <div class="legend-item">
            <div class="legend-color" style="background: #1d4ed8"></div>
            <div class="legend-text"><strong>0.6 - 0.8:</strong> Strong</div>
          </div>
          <div class="legend-item">
            <div class="legend-color" style="background: #60a5fa"></div>
            <div class="legend-text"><strong>0.4 - 0.6:</strong> Moderate</div>
          </div>
          <div class="legend-item">
            <div class="legend-color" style="background: #dbeafe"></div>
            <div class="legend-text"><strong>0.0 - 0.4:</strong> Weak</div>
          </div>
        </div>
      </div>

      <div class="insights">
        <div class="insights-title">Key Insights</div>
        {insights_html}
      </div>
    </div>

    <script>
      const variables = {variables_json};
      const correlationMatrix = {matrix_json};

      // Create annotations for each cell
      const annotations = {annotations_js};

      // Create heatmap trace
      const trace = {{
        z: correlationMatrix,
        x: variables,
        y: variables,
        type: "heatmap",
        colorscale: [
          [0, "#dbeafe"],
          [0.25, "#93c5fd"],
          [0.5, "#60a5fa"],
          [0.75, "#1d4ed8"],
          [1, "#0c4a6e"]
        ],
        colorbar: {{
          title: "Correlation<br>Coefficient",
          titleside: "right",
          thickness: 20,
          len: 0.7,
          tickmode: "linear",
          tick0: 0,
          dtick: 0.2,
          tickfont: {{
            size: 12
          }}
        }},
        hovertemplate:
          "<b>%{{y}}</b> vs <b>%{{x}}</b><br>Correlation: %{{z:.2f}}<extra></extra>",
        zmin: 0,
        zmax: 1
      }};

      const layout = {{
        annotations: annotations,
        xaxis: {{
          side: "bottom",
          tickfont: {{
            size: 14,
            color: "#1e293b",
            family: '-apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif'
          }},
          showgrid: false
        }},
        yaxis: {{
          tickfont: {{
            size: 14,
            color: "#1e293b",
            family: '-apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif'
          }},
          showgrid: false,
          autorange: "reversed"
        }},
        margin: {{
          l: 100,
          r: 100,
          t: 50,
          b: 100
        }},
        paper_bgcolor: "white",
        plot_bgcolor: "white"
      }};

      const config = {{
        responsive: true,
        displayModeBar: true,
        displaylogo: false,
        modeBarButtonsToRemove: ["pan2d", "select2d", "lasso2d", "autoScale2d"]
      }};

      Plotly.newPlot("heatmap", [trace], layout, config);
    </script>
  </body>
</html>"""

def generate_plotly_html(plot_data: list, layout: dict, title: str) -> str:
    """Generate self-contained Plotly HTML with beautiful UI"""
    data_json = json.dumps(plot_data)
    layout_json = json.dumps(layout)

    # Extract subtitle from layout if available
    subtitle = layout.get('title', {}).get('text', 'Interactive 3D Visualization') if isinstance(layout.get('title'), dict) else 'Interactive Data Visualization'

    # Determine plot type for appropriate subtitle
    plot_type = plot_data[0].get('type', 'scatter') if plot_data else 'scatter'
    if plot_type == 'scatter3d':
        default_subtitle = '3D visualization with interactive rotation and zoom'
    elif plot_type == 'heatmap':
        default_subtitle = 'Interactive heatmap showing correlations and patterns'
    elif plot_type == 'surface':
        default_subtitle = '3D surface plot with contour mapping'
    else:
        default_subtitle = 'Interactive data visualization with zoom and pan'

    return f"""<!doctype html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>{title}</title>
    <script src="https://cdnjs.cloudflare.com/ajax/libs/plotly.js/2.26.0/plotly.min.js"></script>
    <style>
      body {{
        margin: 0;
        padding: 20px;
        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        min-height: 100vh;
      }}
      .container {{
        max-width: 1200px;
        margin: 0 auto;
        background: white;
        border-radius: 16px;
        padding: 30px;
        box-shadow: 0 20px 60px rgba(0, 0, 0, 0.3);
      }}
      h1 {{
        color: #2d3748;
        margin-top: 0;
        font-size: 28px;
        font-weight: 700;
      }}
      .subtitle {{
        color: #718096;
        margin-bottom: 25px;
        font-size: 14px;
      }}
      #plot {{
        width: 100%;
        height: 600px;
      }}
      .stats {{
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
        gap: 15px;
        margin-top: 25px;
      }}
      .stat-card {{
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        padding: 20px;
        border-radius: 12px;
        color: white;
      }}
      .stat-label {{
        font-size: 12px;
        opacity: 0.9;
        text-transform: uppercase;
        letter-spacing: 0.5px;
      }}
      .stat-value {{
        font-size: 24px;
        font-weight: 700;
        margin-top: 5px;
      }}
    </style>
  </head>
  <body>
    <div class="container">
      <h1>{title}</h1>
      <p class="subtitle" id="subtitle">{default_subtitle}</p>

      <div id="plot"></div>

      <div class="stats" id="statsContainer"></div>
    </div>

    <script>
      const data = {data_json};
      const layout = {layout_json};

      const config = {{
        responsive: true,
        displayModeBar: true,
        displaylogo: false,
        modeBarButtonsToRemove: ["pan3d", "select3d", "lasso3d"],
      }};

      Plotly.newPlot("plot", data, layout, config);

      // Calculate and display statistics dynamically
      const statsContainer = document.getElementById("statsContainer");

      if (data.length > 0) {{
        const trace = data[0];
        const stats = [];

        // Detect data points count
        if (trace.x) {{
          stats.push({{
            label: "Data Points",
            value: Array.isArray(trace.x) ? trace.x.length : trace.x
          }});
        }}

        // Calculate averages for different axes
        if (trace.y && Array.isArray(trace.y)) {{
          const avgY = trace.y.reduce((a, b) => a + b, 0) / trace.y.length;
          const yLabel = layout.yaxis?.title?.text || layout.scene?.yaxis?.title || "Y Axis";
          stats.push({{
            label: `Avg ${{yLabel}}`,
            value: formatNumber(avgY, yLabel)
          }});
        }}

        if (trace.z && Array.isArray(trace.z)) {{
          // Handle 2D array (heatmaps/surfaces)
          let avgZ;
          if (Array.isArray(trace.z[0])) {{
            const flatZ = trace.z.flat();
            avgZ = flatZ.reduce((a, b) => a + b, 0) / flatZ.length;
          }} else {{
            avgZ = trace.z.reduce((a, b) => a + b, 0) / trace.z.length;
          }}
          const zLabel = layout.zaxis?.title?.text || layout.scene?.zaxis?.title || "Z Axis";
          stats.push({{
            label: `Avg ${{zLabel}}`,
            value: formatNumber(avgZ, zLabel)
          }});
        }}

        // For scatter plots with color scale
        if (trace.marker && trace.marker.color && Array.isArray(trace.marker.color)) {{
          const avgColor = trace.marker.color.reduce((a, b) => a + b, 0) / trace.marker.color.length;
          const colorLabel = trace.marker.colorbar?.title?.text || trace.marker.colorbar?.title || "Color Scale";
          stats.push({{
            label: `Avg ${{colorLabel}}`,
            value: formatNumber(avgColor, colorLabel)
          }});
        }}

        // Render stat cards
        stats.forEach(stat => {{
          const card = document.createElement("div");
          card.className = "stat-card";
          card.innerHTML = `
            <div class="stat-label">${{stat.label}}</div>
            <div class="stat-value">${{stat.value}}</div>
          `;
          statsContainer.appendChild(card);
        }});
      }}

      function formatNumber(num, label) {{
        const lowerLabel = label.toLowerCase();

        // Format as currency if label mentions revenue, cost, price, etc.
        if (lowerLabel.includes("revenue") || lowerLabel.includes("cost") ||
            lowerLabel.includes("price") || lowerLabel.includes("$")) {{
          if (num >= 1000) {{
            return `$${{(num / 1000).toFixed(1)}}K`;
          }}
          return `$${{num.toFixed(0)}}`;
        }}

        // Format as percentage if label mentions rate, growth, percent, etc.
        if (lowerLabel.includes("rate") || lowerLabel.includes("growth") ||
            lowerLabel.includes("%") || lowerLabel.includes("percent") ||
            lowerLabel.includes("profitability")) {{
          return `${{num.toFixed(1)}}%`;
        }}

        // Default number formatting
        if (num >= 1000000) {{
          return `${{(num / 1000000).toFixed(2)}}M`;
        }} else if (num >= 1000) {{
          return `${{(num / 1000).toFixed(1)}}K`;
        }} else if (num < 1) {{
          return num.toFixed(3);
        }} else {{
          return num.toFixed(1);
        }}
      }}
    </script>
  </body>
</html>"""

def generate_gauge_dashboard_html(metrics: list, title: str = "System Monitoring Dashboard", subtitle: str = "Real-time infrastructure metrics and performance indicators") -> str:
    """Generate beautiful gauge dashboard with the user's custom UI template"""

    # Icon mappings
    icon_map = {
        "server": '<path d="M5 12s2.545-5 7-5c4.454 0 7 5 7 5s-2.546 5-7 5c-4.455 0-7-5-7-5z"/><path d="M12 13a1 1 0 1 0 0-2 1 1 0 0 0 0 2z"/><path d="M21 16v2a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-2"/><path d="M21 8V6a2 2 0 0 0-2-2H5a2 2 0 0 0-2 2v2"/>',
        "activity": '<polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/>',
        "harddrive": '<line x1="22" y1="12" x2="2" y2="12"/><path d="M5.45 5.11L2 12v6a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2v-6l-3.45-6.89A2 2 0 0 0 16.76 4H7.24a2 2 0 0 0-1.79 1.11z"/><line x1="6" y1="16" x2="6.01" y2="16"/><line x1="10" y1="16" x2="10.01" y2="16"/>',
        "wifi": '<path d="M5 12.55a11 11 0 0 1 14.08 0"/><path d="M1.42 9a16 16 0 0 1 21.16 0"/><path d="M8.53 16.11a6 6 0 0 1 6.95 0"/><line x1="12" y1="20" x2="12.01" y2="20"/>',
        "clock": '<circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/>',
        "database": '<ellipse cx="12" cy="5" rx="9" ry="3"/><path d="M21 12c0 1.66-4 3-9 3s-9-1.34-9-3"/><path d="M3 5v14c0 1.66 4 3 9 3s9-1.34 9-3V5"/>',
        "zap": '<polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/>',
        "alert": '<path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/>',
        "cpu": '<rect x="4" y="4" width="16" height="16" rx="2" ry="2"/><rect x="9" y="9" width="6" height="6"/><line x1="9" y1="1" x2="9" y2="4"/><line x1="15" y1="1" x2="15" y2="4"/><line x1="9" y1="20" x2="9" y2="23"/><line x1="15" y1="20" x2="15" y2="23"/><line x1="20" y1="9" x2="23" y2="9"/><line x1="20" y1="14" x2="23" y2="14"/><line x1="1" y1="9" x2="4" y2="9"/><line x1="1" y1="14" x2="4" y2="14"/>',
        "memory": '<path d="M4 6h16M4 10h16M4 14h16M4 18h16M2 4h20v16H2z"/>',
        "network": '<circle cx="12" cy="12" r="2"/><path d="M16.24 7.76a6 6 0 0 1 0 8.49m-8.48-.01a6 6 0 0 1 0-8.49m11.31-2.82a10 10 0 0 1 0 14.14m-14.14 0a10 10 0 0 1 0-14.14"/>'
    }

    # Convert metrics to JavaScript array format
    metrics_js = []
    for metric in metrics:
        icon = metric.get("icon", "server")
        if icon not in icon_map:
            icon = "server"

        thresholds_js = "{"
        thresholds = metric.get("thresholds", {})
        threshold_parts = []
        for key, value in thresholds.items():
            threshold_parts.append(f'{key}: {value}')
        thresholds_js += ', '.join(threshold_parts) + "}"

        metric_js = f"""{{
            label: "{metric['label']}",
            value: {metric['value']},
            max: {metric['max']},
            unit: "{metric.get('unit', '')}",
            icon: "{icon}",
            thresholds: {thresholds_js}
        }}"""
        metrics_js.append(metric_js)

    metrics_array = ",\n        ".join(metrics_js)

    # Generate icons object for JavaScript
    icons_js = "{\n"
    for icon_name, icon_svg in icon_map.items():
        icons_js += f"        {icon_name}: '{icon_svg}',\n"
    icons_js += "      }"

    return f"""<!doctype html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>{title}</title>
    <style>
      * {{
        margin: 0;
        padding: 0;
        box-sizing: border-box;
      }}

      body {{
        font-family:
          -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Oxygen, Ubuntu,
          Cantarell, sans-serif;
        background: linear-gradient(135deg, #f8fafc 0%, #e2e8f0 100%);
        min-height: 100vh;
        padding: 2rem;
      }}

      .container {{
        max-width: 1400px;
        margin: 0 auto;
      }}

      .header {{
        margin-bottom: 2rem;
      }}

      .header h1 {{
        font-size: 2.5rem;
        color: #1e293b;
        margin-bottom: 0.5rem;
      }}

      .header p {{
        color: #64748b;
        font-size: 1.1rem;
      }}

      .alert-banner {{
        background: #fef3c7;
        border: 2px solid #fbbf24;
        border-radius: 0.5rem;
        padding: 1rem;
        margin-top: 1rem;
        display: flex;
        align-items: center;
        gap: 0.5rem;
      }}

      .alert-banner svg {{
        flex-shrink: 0;
      }}

      .alert-text {{
        color: #92400e;
        font-weight: 600;
      }}

      .dashboard-grid {{
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
        gap: 1.5rem;
        margin-bottom: 2rem;
      }}

      .gauge-card {{
        background: white;
        border-radius: 0.75rem;
        box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1);
        padding: 1.5rem;
        display: flex;
        flex-direction: column;
        align-items: center;
      }}

      .gauge-header {{
        display: flex;
        align-items: center;
        gap: 0.5rem;
        margin-bottom: 1.5rem;
      }}

      .gauge-header svg {{
        width: 20px;
        height: 20px;
        color: #64748b;
      }}

      .gauge-header h3 {{
        font-size: 1rem;
        color: #475569;
        font-weight: 600;
      }}

      .gauge-container {{
        position: relative;
        width: 200px;
        height: 100px;
        margin-bottom: 1.5rem;
      }}

      .gauge-svg {{
        width: 100%;
        height: 100%;
      }}

      .gauge-bg {{
        fill: none;
        stroke: #e5e7eb;
        stroke-width: 12;
        stroke-linecap: round;
      }}

      .gauge-progress {{
        fill: none;
        stroke-width: 12;
        stroke-linecap: round;
        transition:
          stroke-dasharray 1s ease-out,
          stroke 0.3s ease;
      }}

      .gauge-needle {{
        stroke-width: 3;
        stroke-linecap: round;
        transition: transform 1s ease-out;
        transform-origin: 100px 90px;
      }}

      .gauge-center {{
        transition: fill 0.3s ease;
      }}

      .gauge-labels {{
        position: absolute;
        bottom: 0;
        width: 100%;
        display: flex;
        justify-content: space-between;
        font-size: 0.75rem;
        color: #6b7280;
      }}

      .gauge-value {{
        text-align: center;
      }}

      .value-number {{
        font-size: 2rem;
        font-weight: bold;
        transition: color 0.3s ease;
      }}

      .value-status {{
        font-size: 0.875rem;
        font-weight: 600;
        margin-top: 0.25rem;
        transition: color 0.3s ease;
      }}

      .legend {{
        background: white;
        border-radius: 0.75rem;
        box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1);
        padding: 1.5rem;
      }}

      .legend h2 {{
        font-size: 1.25rem;
        color: #1e293b;
        margin-bottom: 1rem;
      }}

      .legend-grid {{
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
        gap: 1rem;
      }}

      .legend-item {{
        display: flex;
        align-items: center;
        gap: 0.5rem;
      }}

      .legend-color {{
        width: 16px;
        height: 16px;
        border-radius: 50%;
      }}

      .legend-color.good {{
        background: #10b981;
      }}

      .legend-color.warning {{
        background: #f59e0b;
      }}

      .legend-color.critical {{
        background: #ef4444;
      }}

      .legend-item span {{
        color: #475569;
        font-size: 0.875rem;
      }}

      .dashboard-wrapper {{
        position: relative;
        width: 100%;
        min-height: 80vh;
        overflow: hidden;
        display: flex;
        align-items: center;
        justify-content: center;
      }}

      .dashboard-content {{
        transform-origin: center center;
        flex-shrink: 0;
        position: relative;
      }}

      .zoom-controls {{
        position: fixed;
        bottom: 30px;
        right: 30px;
        background: white;
        border-radius: 8px;
        box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
        padding: 8px;
        z-index: 1000;
        display: flex;
        gap: 4px;
      }}

      .zoom-controls button {{
        width: 36px;
        height: 36px;
        border: none;
        background: #f8fafc;
        color: #1e293b;
        border-radius: 4px;
        cursor: pointer;
        font-size: 18px;
        display: flex;
        align-items: center;
        justify-content: center;
        transition: all 0.2s;
      }}

      .zoom-controls button:hover {{
        background: #e2e8f0;
        transform: scale(1.05);
      }}

      .zoom-controls button:active {{
        transform: scale(0.95);
      }}

      .zoom-info-badge {{
        position: fixed;
        bottom: 30px;
        right: 90px;
        background: white;
        color: #1e293b;
        padding: 8px 12px;
        border-radius: 8px;
        box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
        font-size: 14px;
        font-weight: 600;
        z-index: 1000;
      }}

      .dashboard-wrapper.panning {{
        cursor: grab;
      }}

      .dashboard-wrapper.panning:active {{
        cursor: grabbing;
      }}

      @media (max-width: 768px) {{
        body {{
          padding: 1rem;
        }}

        .header h1 {{
          font-size: 1.75rem;
        }}

        .dashboard-grid {{
          grid-template-columns: 1fr;
        }}
      }}
    </style>
  </head>
  <body>
    <div class="dashboard-wrapper" id="dashboardWrapper">
      <div class="zoom-controls">
        <button onclick="resetDashboardView()" title="Reset View">↺</button>
      </div>
      <div class="zoom-info-badge" id="zoomInfo">100%</div>

      <div class="dashboard-content" id="dashboardContent">
        <div class="container">
          <div class="header">
            <h1>{title}</h1>
            <p>{subtitle}</p>
            <div class="alert-banner" id="alertBanner" style="display: none">
              <svg
                width="20"
                height="20"
                viewBox="0 0 24 24"
                fill="none"
                stroke="#d97706"
                stroke-width="2"
              >
                <path
                  d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"
                />
                <line x1="12" y1="9" x2="12" y2="13" />
                <line x1="12" y1="17" x2="12.01" y2="17" />
              </svg>
              <span class="alert-text" id="alertText"></span>
            </div>
          </div>

          <div class="dashboard-grid" id="dashboard"></div>

          <div class="legend">
            <h2>Threshold Legend</h2>
            <div class="legend-grid">
              <div class="legend-item">
                <div class="legend-color good"></div>
                <span>Good / Optimal Range</span>
              </div>
              <div class="legend-item">
                <div class="legend-color warning"></div>
                <span>Warning Threshold</span>
              </div>
              <div class="legend-item">
                <div class="legend-color critical"></div>
                <span>Critical Threshold</span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>

    <script>
      const metrics = [
        {metrics_array}
      ];

      const icons = {icons_js};

      function getStatus(metric) {{
        const {{ value, thresholds }} = metric;

        if (!thresholds) return {{ color: "#10b981", status: "Good" }};

        if (thresholds.critical !== undefined && value >= thresholds.critical) {{
          return {{ color: "#ef4444", status: "Critical" }};
        }}
        if (thresholds.warning !== undefined && value >= thresholds.warning) {{
          return {{ color: "#f59e0b", status: "Warning" }};
        }}
        if (thresholds.good !== undefined && value >= thresholds.good) {{
          return {{ color: "#f59e0b", status: "Warning" }};
        }}
        if (thresholds.optimal !== undefined && value < thresholds.optimal) {{
          return {{ color: "#f59e0b", status: "Below Optimal" }};
        }}
        if (
          thresholds.goodAbove !== undefined &&
          value < thresholds.goodAbove
        ) {{
          return {{ color: "#f59e0b", status: "Below Target" }};
        }}

        return {{ color: "#10b981", status: "Good" }};
      }}

      function createGauge(metric, index) {{
        const percentage = (metric.value / metric.max) * 100;
        const angle = (percentage / 100) * 180 - 90;
        const arcLength = 251.2;
        const progressLength = (percentage / 100) * arcLength;
        const {{ color, status }} = getStatus(metric);

        return `
                <div class="gauge-card">
                    <div class="gauge-header">
                        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                            ${{icons[metric.icon]}}
                        </svg>
                        <h3>${{metric.label}}</h3>
                    </div>
                    <div class="gauge-container">
                        <svg class="gauge-svg" viewBox="0 0 200 100">
                            <path class="gauge-bg" d="M 20 90 A 80 80 0 0 1 180 90"/>
                            <path
                                class="gauge-progress"
                                id="progress-${{index}}"
                                d="M 20 90 A 80 80 0 0 1 180 90"
                                stroke="${{color}}"
                                stroke-dasharray="0 ${{arcLength}}"
                            />
                            <line
                                class="gauge-needle"
                                id="needle-${{index}}"
                                x1="100" y1="90" x2="100" y2="30"
                                stroke="${{color}}"
                                transform="rotate(-90 100 90)"
                            />
                            <circle class="gauge-center" id="center-${{index}}" cx="100" cy="90" r="6" fill="${{color}}"/>
                        </svg>
                        <div class="gauge-labels">
                            <span>0</span>
                            <span>${{metric.max}}</span>
                        </div>
                    </div>
                    <div class="gauge-value">
                        <div class="value-number" id="value-${{index}}" style="color: ${{color}}">
                            ${{metric.value}}${{metric.unit}}
                        </div>
                        <div class="value-status" id="status-${{index}}" style="color: ${{color}}">
                            ${{status}}
                        </div>
                    </div>
                </div>
            `;
      }}

      function animateGauges() {{
        metrics.forEach((metric, index) => {{
          const percentage = (metric.value / metric.max) * 100;
          const angle = (percentage / 100) * 180 - 90;
          const arcLength = 251.2;
          const progressLength = (percentage / 100) * arcLength;
          const {{ color }} = getStatus(metric);

          setTimeout(() => {{
            const progress = document.getElementById(`progress-${{index}}`);
            const needle = document.getElementById(`needle-${{index}}`);

            progress.style.strokeDasharray = `${{progressLength}} ${{arcLength}}`;
            needle.style.transform = `rotate(${{angle}}deg)`;
          }}, index * 100);
        }});
      }}

      function showAlertBanner() {{
        const warningCount = metrics.filter((metric) => {{
          const {{ status }} = getStatus(metric);
          return status !== "Good";
        }}).length;

        if (warningCount > 0) {{
          const banner = document.getElementById("alertBanner");
          const text = document.getElementById("alertText");
          banner.style.display = "flex";
          text.textContent = `${{warningCount}} metric${{warningCount > 1 ? "s" : ""}} requiring attention`;
        }}
      }}

      function init() {{
        const dashboard = document.getElementById("dashboard");
        dashboard.innerHTML = metrics
          .map((metric, index) => createGauge(metric, index))
          .join("");

        setTimeout(() => {{
          animateGauges();
          showAlertBanner();
        }}, 100);
      }}

      init();

      // Zoom and Pan functionality
      const dashboardWrapper = document.getElementById("dashboardWrapper");
      const dashboardContent = document.getElementById("dashboardContent");
      const zoomInfo = document.getElementById("zoomInfo");

      let dashboardScale = 1;
      let dashboardTranslateX = 0;
      let dashboardTranslateY = 0;
      let isPanning = false;
      let panStartX = 0;
      let panStartY = 0;

      function updateDashboardTransform() {{
        dashboardContent.style.transform = `translate(${{dashboardTranslateX}}px, ${{dashboardTranslateY}}px) scale(${{dashboardScale}})`;
        zoomInfo.textContent = Math.round(dashboardScale * 100) + '%';
      }}

      function resetDashboardView() {{
        dashboardScale = 1;
        dashboardTranslateX = 0;
        dashboardTranslateY = 0;
        updateDashboardTransform();
      }}

      // Zoom with Ctrl + Mouse Wheel
      dashboardWrapper.addEventListener('wheel', (e) => {{
        if (e.ctrlKey) {{
          e.preventDefault();

          const wrapperRect = dashboardWrapper.getBoundingClientRect();
          const mouseX = e.clientX - wrapperRect.left;
          const mouseY = e.clientY - wrapperRect.top;

          const contentRect = dashboardContent.getBoundingClientRect();
          const contentCenterX = contentRect.left - wrapperRect.left + contentRect.width / 2;
          const contentCenterY = contentRect.top - wrapperRect.top + contentRect.height / 2;

          const mouseRelativeX = mouseX - contentCenterX;
          const mouseRelativeY = mouseY - contentCenterY;

          const delta = e.deltaY > 0 ? 0.9 : 1.1;
          const oldScale = dashboardScale;
          const newScale = Math.min(Math.max(dashboardScale * delta, 0.1), 10);

          const scaleDiff = newScale - oldScale;
          dashboardTranslateX -= mouseRelativeX * (scaleDiff / oldScale);
          dashboardTranslateY -= mouseRelativeY * (scaleDiff / oldScale);

          dashboardScale = newScale;
          updateDashboardTransform();
        }}
      }}, {{ passive: false }});

      // Pan with Click & Drag
      dashboardWrapper.addEventListener('mousedown', (e) => {{
        isPanning = true;
        panStartX = e.clientX - dashboardTranslateX;
        panStartY = e.clientY - dashboardTranslateY;
        dashboardWrapper.classList.add('panning');
      }});

      document.addEventListener('mousemove', (e) => {{
        if (isPanning) {{
          dashboardTranslateX = e.clientX - panStartX;
          dashboardTranslateY = e.clientY - panStartY;
          updateDashboardTransform();
        }}
      }});

      document.addEventListener('mouseup', () => {{
        if (isPanning) {{
          isPanning = false;
          dashboardWrapper.classList.remove('panning');
        }}
      }});
    </script>
  </body>
</html>"""

def generate_echarts_html(option: dict, title: str) -> str:
    """Generate self-contained ECharts HTML"""
    option_json = json.dumps(option)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title}</title>
    <script src="https://cdn.jsdelivr.net/npm/echarts@5.4.3/dist/echarts.min.js"></script>
    <style>
        body {{
            margin: 0;
            padding: 40px;
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: #f5f5f5;
        }}
        .container {{
            max-width: 1400px;
            margin: 0 auto;
            background: white;
            padding: 30px;
            border-radius: 12px;
            box-shadow: 0 4px 12px rgba(0,0,0,0.1);
        }}
        h1 {{
            margin: 0 0 20px 0;
            color: #333;
            font-size: 24px;
        }}
        #chart {{
            width: 100%;
            height: 600px;
        }}
        .controls {{
            margin-top: 20px;
            display: flex;
            gap: 10px;
        }}
        button {{
            padding: 10px 20px;
            border: none;
            border-radius: 6px;
            background: #6965db;
            color: white;
            cursor: pointer;
            font-size: 14px;
        }}
        button:hover {{
            background: #5753c5;
        }}
    </style>
</head>
<body>
    <div class="container">
        <h1>{title}</h1>
        <div id="chart"></div>
        <div class="controls">
            <button onclick="exportPNG()">📷 Export PNG</button>
            <button onclick="exportSVG()">🎨 Export SVG</button>
        </div>
    </div>

    <script>
        const chart = echarts.init(document.getElementById('chart'));
        const option = {option_json};

        chart.setOption(option);

        window.addEventListener('resize', () => {{
            chart.resize();
        }});

        function exportPNG() {{
            const url = chart.getDataURL({{
                type: 'png',
                pixelRatio: 2,
                backgroundColor: '#fff'
            }});
            const a = document.createElement('a');
            a.href = url;
            a.download = 'chart.png';
            a.click();
        }}

        function exportSVG() {{
            const url = chart.getDataURL({{
                type: 'svg'
            }});
            const a = document.createElement('a');
            a.href = url;
            a.download = 'chart.svg';
            a.click();
        }}
    </script>
</body>
</html>"""

# MCP Tools
@app.list_tools()
async def list_tools() -> list[Tool]:
    """List available visualization tools"""
    return [
        Tool(
            name="create_diagram",
            description="Create an interactive SVG diagram with pre-populated elements based on the user's requirements. Parse the user's prompt to extract components/services and generate initial shapes and connections. Each element should have: id, x, y, width, height, shape (rectangle/rounded-rect/circle/ellipse/diamond), fillColor, strokeColor, textColor, and text label.",
            inputSchema={
                "type": "object",
                "properties": {
                    "diagram_id": {
                        "type": "string",
                        "description": "Unique identifier for the diagram (e.g., 'ecommerce-system', 'microservices-arch')"
                    },
                    "elements": {
                        "type": "array",
                        "description": "Array of diagram elements extracted from user's prompt. Each element represents a component/service mentioned by the user.",
                        "items": {
                            "type": "object",
                            "properties": {
                                "text": {"type": "string", "description": "Label for the element (e.g., 'API Gateway', 'User Service')"},
                                "x": {"type": "number", "description": "X position (50-1000)"},
                                "y": {"type": "number", "description": "Y position (50-600)"},
                                "width": {"type": "number", "description": "Width (150-250)"},
                                "height": {"type": "number", "description": "Height (60-100)"},
                                "shape": {"type": "string", "enum": ["rectangle", "rounded-rect", "circle", "ellipse", "diamond"]},
                                "fillColor": {"type": "string", "description": "Hex color (e.g., '#a5d8ff')"},
                                "strokeColor": {"type": "string", "description": "Hex color (e.g., '#1971c2')"}
                            },
                            "required": ["text", "x", "y", "width", "height", "shape"]
                        }
                    },
                    "connections": {
                        "type": "array",
                        "description": "Array of connections between elements. Use fromId and toId that match element array indices.",
                        "items": {
                            "type": "object",
                            "properties": {
                                "fromId": {"type": "string", "description": "Source element ID (e.g., 'element1')"},
                                "fromPoint": {"type": "string", "enum": ["top", "right", "bottom", "left"]},
                                "toId": {"type": "string", "description": "Target element ID (e.g., 'element2')"},
                                "toPoint": {"type": "string", "enum": ["top", "right", "bottom", "left"]}
                            },
                            "required": ["fromId", "fromPoint", "toId", "toPoint"]
                        }
                    }
                },
                "required": ["diagram_id", "elements"]
            }
        ),
        Tool(
            name="load_diagram",
            description="Load a previously saved Excalidraw diagram for viewing or editing",
            inputSchema={
                "type": "object",
                "properties": {
                    "diagram_id": {
                        "type": "string",
                        "description": "ID of the diagram to load"
                    }
                },
                "required": ["diagram_id"]
            }
        ),
        Tool(
            name="list_diagrams",
            description="List all saved diagrams with their metadata",
            inputSchema={
                "type": "object",
                "properties": {}
            }
        ),
        Tool(
            name="generate_flowchart",
            description="Generate flowcharts and sequence diagrams. For detailed sequence diagrams with multiple services, use description parameter with bullet points. For simple flowcharts, use mermaid_code.",
            inputSchema={
                "type": "object",
                "properties": {
                    "diagram_type": {
                        "type": "string",
                        "description": "Type of diagram: 'flowchart', 'sequence', 'class', 'state', 'er', 'gantt', 'pie', 'journey'",
                        "enum": ["flowchart", "sequence", "class", "state", "er", "gantt", "pie", "journey"]
                    },
                    "mermaid_code": {
                        "type": "string",
                        "description": "Mermaid syntax code for the diagram (optional if description is provided)"
                    },
                    "description": {
                        "type": "string",
                        "description": "Detailed description with bullet points for complex sequence diagrams. Each bullet should describe a step like: '- Frontend sends request to API Gateway'. Use this for multi-service authentication flows, microservices interactions, etc."
                    },
                    "title": {
                        "type": "string",
                        "description": "Title for the diagram"
                    }
                },
                "required": ["diagram_type"]
            }
        ),
        Tool(
            name="create_chart",
            description="Create interactive Chart.js visualizations. Supports bar, line, pie, doughnut, radar, polar area, and bubble charts.",
            inputSchema={
                "type": "object",
                "properties": {
                    "chart_type": {
                        "type": "string",
                        "description": "Type of chart: 'bar', 'line', 'pie', 'doughnut', 'radar', 'polarArea', 'bubble'",
                        "enum": ["bar", "line", "pie", "doughnut", "radar", "polarArea", "bubble"]
                    },
                    "data": {
                        "type": "object",
                        "description": "Chart.js data object with labels and datasets"
                    },
                    "options": {
                        "type": "object",
                        "description": "Chart.js options for customization"
                    },
                    "title": {
                        "type": "string",
                        "description": "Title for the chart"
                    }
                },
                "required": ["chart_type", "data", "title"]
            }
        ),
        Tool(
            name="create_plot",
            description="Create advanced Plotly visualizations. Supports 3D plots, heatmaps, contour plots, scatter plots, and complex multi-trace visualizations.",
            inputSchema={
                "type": "object",
                "properties": {
                    "plot_type": {
                        "type": "string",
                        "description": "Type of plot: 'scatter', 'line', 'bar', 'heatmap', 'surface', '3d_scatter', 'contour', 'box', 'violin'",
                        "enum": ["scatter", "line", "bar", "heatmap", "surface", "3d_scatter", "contour", "box", "violin"]
                    },
                    "data": {
                        "type": "array",
                        "description": "Array of Plotly trace objects"
                    },
                    "layout": {
                        "type": "object",
                        "description": "Plotly layout configuration"
                    },
                    "title": {
                        "type": "string",
                        "description": "Title for the plot"
                    }
                },
                "required": ["plot_type", "data", "title"]
            }
        ),
        Tool(
            name="create_dashboard",
            description="Create comprehensive dashboards. For gauge dashboards, use metrics array. For other types, use ECharts option object. Supports complex multi-chart dashboards, geographic maps, gauge charts, tree maps, and advanced customizations.",
            inputSchema={
                "type": "object",
                "properties": {
                    "dashboard_type": {
                        "type": "string",
                        "description": "Type of dashboard: 'line', 'bar', 'pie', 'gauge', 'funnel', 'treemap', 'sunburst', 'graph', 'sankey'",
                        "enum": ["line", "bar", "pie", "gauge", "funnel", "treemap", "sunburst", "graph", "sankey"]
                    },
                    "metrics": {
                        "type": "array",
                        "description": "Array of metric objects for gauge dashboards. Each metric has: label, value, max, unit, icon, thresholds. Only used when dashboard_type is 'gauge'.",
                        "items": {
                            "type": "object",
                            "properties": {
                                "label": {"type": "string", "description": "Metric name (e.g., 'Server CPU', 'Memory Usage')"},
                                "value": {"type": "number", "description": "Current value"},
                                "max": {"type": "number", "description": "Maximum value for the gauge"},
                                "unit": {"type": "string", "description": "Unit (e.g., '%', 'ms', ' Mbps', '')"},
                                "icon": {
                                    "type": "string",
                                    "description": "Icon name: server, activity, harddrive, wifi, clock, database, zap, alert, cpu, memory, network",
                                    "enum": ["server", "activity", "harddrive", "wifi", "clock", "database", "zap", "alert", "cpu", "memory", "network"]
                                },
                                "thresholds": {
                                    "type": "object",
                                    "description": "Threshold values: warning, critical, optimal, good, goodAbove",
                                    "properties": {
                                        "warning": {"type": "number"},
                                        "critical": {"type": "number"},
                                        "optimal": {"type": "number"},
                                        "good": {"type": "number"},
                                        "goodAbove": {"type": "number"}
                                    }
                                }
                            },
                            "required": ["label", "value", "max"]
                        }
                    },
                    "option": {
                        "type": "object",
                        "description": "ECharts option configuration object. Used for non-gauge dashboards."
                    },
                    "title": {
                        "type": "string",
                        "description": "Title for the dashboard"
                    },
                    "subtitle": {
                        "type": "string",
                        "description": "Subtitle/description for gauge dashboards"
                    }
                },
                "required": ["dashboard_type", "title"]
            }
        )
    ]

@app.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    """Handle tool calls"""
    try:
        if name == "create_diagram":
            diagram_id = arguments["diagram_id"]
            elements = arguments.get("elements", [])
            connections = arguments.get("connections", [])

            # Save metadata
            metadata = {
                "id": diagram_id,
                "created_at": datetime.now().isoformat(),
                "type": "diagram",
                "elements_count": len(elements)
            }
            metadata_file = STORAGE_DIR / f"{diagram_id}.meta.json"
            safe_write_json(metadata_file, metadata)

            # Generate HTML with custom elements and connections
            html = generate_excalidraw_html(diagram_id, None, elements, connections)

            return [TextContent(
                type="text",
                text=html
            )]

        elif name == "load_diagram":
            diagram_id = arguments["diagram_id"]
            metadata_file = STORAGE_DIR / f"{diagram_id}.meta.json"

            if not metadata_file.exists():
                return [TextContent(
                    type="text",
                    text=f"❌ Diagram '{diagram_id}' not found. Use list_diagrams to see available diagrams."
                )]

            metadata = safe_read_json(metadata_file)
            html = generate_excalidraw_html(diagram_id)

            return [TextContent(
                type="text",
                text=html
            )]

        elif name == "list_diagrams":
            diagram_files = list(STORAGE_DIR.glob("*.meta.json"))

            if not diagram_files:
                return [TextContent(
                    type="text",
                    text="📋 No diagrams saved yet. Create one with create_diagram!"
                )]

            diagrams_info = []
            for meta_file in diagram_files:
                metadata = safe_read_json(meta_file)
                diagrams_info.append(f"""
• {metadata.get('id', 'Unknown')}
  - Type: {metadata.get('type', 'Unknown')}
  - Created: {metadata.get('created_at', 'Unknown')}
  - Elements: {metadata.get('elements_count', 0)}""")

            return [TextContent(
                type="text",
                text=f"""📋 Saved Diagrams ({len(diagram_files)}):
{chr(10).join(diagrams_info)}

Use load_diagram to view any of these diagrams."""
            )]

        elif name == "generate_flowchart":
            diagram_type = arguments["diagram_type"]
            title = arguments.get("title", f"{diagram_type.title()} Diagram")
            description = arguments.get("description", "")
            mermaid_code = arguments.get("mermaid_code", "")

            # Check if description has bullet points (detailed format)
            has_bullet_points = description and ('-' in description or '•' in description or '*' in description)
            has_multiple_lines = description and '\n' in description

            # Use custom HTML templates for diagrams with bullet-point descriptions
            if diagram_type == "sequence" and has_bullet_points and has_multiple_lines:
                # Beautiful custom SVG for sequence diagrams
                html = generate_sequence_diagram_html(title, description)
            elif diagram_type == "flowchart" and has_bullet_points and has_multiple_lines:
                # Beautiful custom HTML for flowcharts
                html = generate_flowchart_html(title, description)
            elif mermaid_code:
                # Use Mermaid if mermaid_code is provided
                # Automatically fix common Mermaid syntax errors
                mermaid_code = fix_mermaid_syntax(mermaid_code)
                html = generate_mermaid_html(mermaid_code, diagram_type)
            else:
                # Neither proper description nor mermaid_code provided
                return [TextContent(
                    type="text",
                    text="Error: Provide either:\n1. 'description' with bullet points (- Step 1\\n- Step 2) for custom templates\n2. 'mermaid_code' with Mermaid syntax for standard rendering"
                )]

            return [TextContent(
                type="text",
                text=html
            )]

        elif name == "create_chart":
            chart_type = arguments["chart_type"]
            data = arguments["data"]
            options = arguments.get("options", {})
            title = arguments["title"]

            # Build Chart.js config
            config = {
                "type": chart_type,
                "data": data,
                "options": {
                    "responsive": True,
                    "maintainAspectRatio": False,
                    "plugins": {
                        "legend": {"display": True},
                        "title": {"display": True, "text": title}
                    },
                    **options
                }
            }

            html = generate_chartjs_html(config, title)

            return [TextContent(
                type="text",
                text=html
            )]

        elif name == "create_plot":
            plot_type = arguments["plot_type"]
            data = arguments["data"]
            layout = arguments.get("layout", {})
            title = arguments["title"]

            # Ensure layout has title
            if "title" not in layout:
                layout["title"] = title

            # Use special heatmap template for heatmaps
            if plot_type == "heatmap" and len(data) > 0 and data[0].get("type") == "heatmap":
                html = generate_heatmap_html(data, layout, title)
            else:
                html = generate_plotly_html(data, layout, title)

            return [TextContent(
                type="text",
                text=html
            )]

        elif name == "create_dashboard":
            dashboard_type = arguments["dashboard_type"]
            title = arguments["title"]
            subtitle = arguments.get("subtitle", "Real-time infrastructure metrics and performance indicators")

            # Use new gauge dashboard for gauge type
            if dashboard_type == "gauge":
                metrics = arguments.get("metrics", [])
                html = generate_gauge_dashboard_html(metrics, title, subtitle)
            else:
                # Use ECharts for other dashboard types
                option = arguments["option"]

                # Ensure option has title
                if "title" not in option:
                    option["title"] = {"text": title, "left": "center"}

                html = generate_echarts_html(option, title)

            return [TextContent(
                type="text",
                text=html
            )]

        else:
            return [TextContent(
                type="text",
                text=f"❌ Unknown tool: {name}"
            )]

    except Exception as e:
        return [TextContent(
            type="text",
            text=f"❌ Error: {str(e)}"
        )]

# MCP Prompts Resource
@app.list_prompts()
async def list_prompts() -> list[Prompt]:
    """List available prompts"""
    return [
        Prompt(
            name="visualization_agent",
            description="System instructions for Visualization Agent"
        )
    ]

@app.get_prompt()
async def get_prompt(name: str, arguments: dict[str, str] | None = None) -> GetPromptResult:
    """Get prompt content"""
    if name == "visualization_agent":
        return GetPromptResult(
            description="Instructions for creating effective visualizations",
            messages=[
                PromptMessage(
                    role="user",
                    content=TextContent(
                        type="text",
                        text="""🎨 VISUALIZATION AGENT - CRITICAL INSTRUCTIONS

⚠️ SEQUENCE DIAGRAMS - ALWAYS USE BULLET-POINT DESCRIPTION ⚠️

DEFAULT BEHAVIOR FOR ALL SEQUENCE DIAGRAMS:
✅ ALWAYS use "description" parameter with bullet-point format
❌ NEVER use "mermaid_code" parameter (unless user explicitly requests Mermaid)
✅ Generates beautiful custom SVG with gradient colors
✅ Professional styling with phase labels and numbered arrows

REQUIRED FORMAT (USE THIS):
{
  "diagram_type": "sequence",
  "title": "Your Title",
  "description": "- Service A sends request to Service B\\n- Service B queries Database\\n- Database returns data\\n- Service B returns response to Service A"
}
⚠️ DO NOT include mermaid_code parameter ⚠️

CRITICAL RULES:
1. Use \\n for newlines (NOT actual line breaks in JSON)
2. Each step MUST start with "- " (dash space)
3. Capitalize service names: "Frontend", "API Gateway", "Auth Service"
4. Use action verbs: sends, forwards, queries, returns, validates, checks
5. Include "to/from/with": "sends request to", "returns data to"
6. NEVER use mermaid_code parameter by default

COMPLETE EXAMPLE for authentication flow:
{
  "diagram_type": "sequence",
  "title": "Microservices Authentication Flow",
  "description": "- User submits login credentials to Frontend\\n- Frontend sends request to API Gateway\\n- API Gateway forwards to Auth Service\\n- Auth Service queries User Database\\n- User Database returns user data\\n- Auth Service validates password with Encryption Service\\n- Encryption Service returns validation result\\n- Auth Service generates JWT token\\n- Auth Service stores session in Redis Cache\\n- Auth Service returns token to API Gateway\\n- API Gateway logs event to Logging Service\\n- API Gateway returns token to Frontend\\n- Frontend stores token in local storage\\n- Frontend displays user dashboard"
}

Action verbs for REQUESTS (solid arrow →): sends, forwards, queries, requests, submits, validates, checks, logs, stores, generates
Action verbs for RESPONSES (dashed arrow ←): returns, responds, sends back, displays, replies

BENEFITS OF BULLET-POINT DESCRIPTION:
✓ Beautiful custom SVG with gradient-colored service boxes
✓ Automatic color assignment for each service
✓ Numbered arrows showing sequence (1, 2, 3...)
✓ Professional dark gradient background
✓ Hover effects on services and arrows
✓ Implicit response handling (returns automatically go back)

OTHER VISUALIZATIONS:

For create_chart (Chart.js):
{
  "chart_type": "bar",
  "data": {
    "labels": ["Q1", "Q2", "Q3", "Q4"],
    "datasets": [{"label": "Revenue", "data": [12, 19, 3, 5]}]
  },
  "title": "Quarterly Revenue"
}

For create_plot heatmap:
{
  "plot_type": "heatmap",
  "title": "Correlation Matrix",
  "data": [{
    "type": "heatmap",
    "z": [[1.0, 0.8], [0.8, 1.0]],
    "x": ["A", "B"],
    "y": ["A", "B"],
    "colorscale": "Blues"
  }]
}

For create_dashboard gauge:
{
  "dashboard_type": "gauge",
  "title": "System Monitoring",
  "metrics": [{
    "label": "CPU",
    "value": 78,
    "max": 100,
    "unit": "%",
    "icon": "cpu",
    "thresholds": {"warning": 70, "critical": 90}
  }]
}

REMEMBER:
✅ Sequence diagrams MUST use "description" parameter (NOT mermaid_code)
✅ Each line starts with "- " (dash space)
✅ Capitalize all service names
✅ Use \\n for newlines in the description string
✅ Use proper action verbs and connectors (to/from/with)
❌ DO NOT use mermaid_code parameter unless explicitly requested"""
                    )
                )
            ]
        )

    raise ValueError(f"Unknown prompt: {name}")

# Server entry point
async def main():
    """Run the MCP server"""
    async with stdio_server() as (read_stream, write_stream):
        await app.run(
            read_stream,
            write_stream,
            app.create_initialization_options()
        )

if __name__ == "__main__":
    asyncio.run(main())
