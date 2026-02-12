# Backend to Frontend Flow - Snake Game MCP

This document explains how the snake game HTML/JavaScript is sent from the backend MCP server to your frontend application.

## How It Works

The snake game MCP server returns **complete, self-contained HTML** that includes all the CSS and JavaScript needed to run the game. Your frontend simply needs to receive this HTML and display it.

## Backend Response Flow

### 1. Frontend Calls MCP Tool

Your frontend (or AI agent) makes a request to the MCP server:

```javascript
// Example: Frontend JavaScript calling the MCP endpoint
fetch('http://localhost:8099/snake-game/mcp', {
  method: 'POST',
  headers: {
    'Content-Type': 'application/json'
  },
  body: JSON.stringify({
    "jsonrpc": "2.0",
    "id": 1,
    "method": "tools/call",
    "params": {
      "name": "start_game",
      "arguments": {
        "difficulty": "medium",
        "board_size": "medium"
      }
    }
  })
})
.then(response => response.json())
.then(data => {
  // Parse the response
  const result = JSON.parse(data.result.content[0].text);
  const gameHTML = result.game_ui;

  // Now you have the complete game HTML!
  displayGame(gameHTML);
});
```

### 2. Backend Returns Complete HTML

The MCP server (server.py) generates and returns the complete game HTML:

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "result": {
    "content": [
      {
        "type": "text",
        "text": "{
          \"status\": \"success\",
          \"message\": \"Snake game started!\",
          \"game_ui\": \"<!DOCTYPE html><html>...complete game HTML with CSS and JS...</html>\",
          \"settings\": {
            \"difficulty\": \"medium\",
            \"board_size\": \"medium\"
          }
        }"
      }
    ]
  }
}
```

### 3. Frontend Displays the Game

You have several options to display the game HTML:

#### Option A: Display in an iframe (Recommended)

```javascript
function displayGame(gameHTML) {
  // Create an iframe
  const iframe = document.createElement('iframe');
  iframe.style.width = '100%';
  iframe.style.height = '800px';
  iframe.style.border = 'none';

  // Add to page
  document.getElementById('game-container').appendChild(iframe);

  // Write the game HTML to the iframe
  iframe.contentWindow.document.open();
  iframe.contentWindow.document.write(gameHTML);
  iframe.contentWindow.document.close();
}
```

#### Option B: Create a Blob URL and Open in New Tab

```javascript
function displayGame(gameHTML) {
  // Create a blob from the HTML
  const blob = new Blob([gameHTML], { type: 'text/html' });
  const url = URL.createObjectURL(blob);

  // Open in new window/tab
  window.open(url, '_blank');
}
```

#### Option C: Display in a Modal/Dialog

```javascript
function displayGame(gameHTML) {
  // Create a modal backdrop
  const modal = document.createElement('div');
  modal.className = 'game-modal';
  modal.style.cssText = `
    position: fixed;
    top: 0;
    left: 0;
    width: 100%;
    height: 100%;
    background: rgba(0,0,0,0.8);
    display: flex;
    justify-content: center;
    align-items: center;
    z-index: 9999;
  `;

  // Create iframe for game
  const iframe = document.createElement('iframe');
  iframe.style.cssText = `
    width: 90%;
    max-width: 900px;
    height: 90%;
    border: none;
    border-radius: 10px;
  `;

  // Close button
  const closeBtn = document.createElement('button');
  closeBtn.textContent = '✕ Close';
  closeBtn.style.cssText = `
    position: absolute;
    top: 20px;
    right: 20px;
    padding: 10px 20px;
    background: white;
    border: none;
    border-radius: 5px;
    cursor: pointer;
    font-size: 16px;
  `;
  closeBtn.onclick = () => modal.remove();

  modal.appendChild(iframe);
  modal.appendChild(closeBtn);
  document.body.appendChild(modal);

  // Load game into iframe
  iframe.contentWindow.document.open();
  iframe.contentWindow.document.write(gameHTML);
  iframe.contentWindow.document.close();
}
```

## Complete Frontend Example

Here's a complete HTML page that calls the MCP backend and displays the game:

```html
<!DOCTYPE html>
<html>
<head>
  <title>Snake Game Frontend</title>
  <style>
    body {
      font-family: Arial, sans-serif;
      max-width: 1200px;
      margin: 0 auto;
      padding: 20px;
    }

    button {
      background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
      color: white;
      border: none;
      padding: 15px 30px;
      font-size: 16px;
      border-radius: 5px;
      cursor: pointer;
      margin: 10px 5px;
    }

    button:hover {
      transform: translateY(-2px);
      box-shadow: 0 4px 15px rgba(0,0,0,0.3);
    }

    #game-container {
      margin-top: 20px;
    }
  </style>
</head>
<body>
  <h1>Snake Game - MCP Frontend Demo</h1>

  <div>
    <h3>Choose Game Settings:</h3>
    <label>
      Difficulty:
      <select id="difficulty">
        <option value="easy">Easy</option>
        <option value="medium" selected>Medium</option>
        <option value="hard">Hard</option>
      </select>
    </label>

    <label>
      Board Size:
      <select id="boardSize">
        <option value="small">Small (20x20)</option>
        <option value="medium" selected>Medium (30x30)</option>
        <option value="large">Large (40x40)</option>
      </select>
    </label>

    <button onclick="startGame()">Start Game</button>
    <button onclick="startGameNewTab()">Start in New Tab</button>
  </div>

  <div id="game-container"></div>

  <script>
    const MCP_ENDPOINT = 'http://localhost:8099/snake-game/mcp';

    async function callMCPTool(toolName, args) {
      const response = await fetch(MCP_ENDPOINT, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          "jsonrpc": "2.0",
          "id": Date.now(),
          "method": "tools/call",
          "params": {
            "name": toolName,
            "arguments": args
          }
        })
      });

      const data = await response.json();
      return JSON.parse(data.result.content[0].text);
    }

    async function startGame() {
      const difficulty = document.getElementById('difficulty').value;
      const boardSize = document.getElementById('boardSize').value;

      // Call MCP backend
      const result = await callMCPTool('start_game', {
        difficulty: difficulty,
        board_size: boardSize
      });

      // Get the HTML from backend
      const gameHTML = result.game_ui;

      // Display in iframe
      const container = document.getElementById('game-container');
      container.innerHTML = '';

      const iframe = document.createElement('iframe');
      iframe.style.width = '100%';
      iframe.style.height = '800px';
      iframe.style.border = '2px solid #667eea';
      iframe.style.borderRadius = '10px';

      container.appendChild(iframe);

      // Write game HTML to iframe
      iframe.contentWindow.document.open();
      iframe.contentWindow.document.write(gameHTML);
      iframe.contentWindow.document.close();
    }

    async function startGameNewTab() {
      const difficulty = document.getElementById('difficulty').value;
      const boardSize = document.getElementById('boardSize').value;

      // Call MCP backend
      const result = await callMCPTool('start_game', {
        difficulty: difficulty,
        board_size: boardSize
      });

      // Get the HTML from backend
      const gameHTML = result.game_ui;

      // Open in new tab
      const blob = new Blob([gameHTML], { type: 'text/html' });
      const url = URL.createObjectURL(blob);
      window.open(url, '_blank');
    }
  </script>
</body>
</html>
```

## Key Points

1. **Backend sends complete HTML**: The `server.py` generates the entire game HTML including CSS and JavaScript
2. **No external dependencies**: The game HTML is self-contained and works standalone
3. **Frontend just displays**: Your frontend receives the HTML string and displays it (iframe, new tab, modal, etc.)
4. **Customizable**: Pass `difficulty` and `board_size` arguments to get different game configurations

## Testing the Flow

### Step 1: Start the MCP Server

```bash
cd /workspaces/fluidmcp
fluidmcp run examples/snake-game-config.json --file --start-server
```

### Step 2: Save the Frontend Example

Save the complete frontend example above as `frontend-demo.html`

### Step 3: Open in Browser

Open `frontend-demo.html` in your browser and click "Start Game"

The frontend will:
1. Call the MCP backend endpoint
2. Receive the complete game HTML
3. Display it in an iframe

That's it! The backend handles all the game logic and UI generation, and your frontend just needs to display the HTML.

## Architecture Diagram

```
┌─────────────────┐
│   Frontend      │
│   (Browser)     │
│                 │
│  [Start Game]   │
└────────┬────────┘
         │
         │ HTTP POST
         │ /snake-game/mcp
         │ { method: "tools/call", name: "start_game", args: {...} }
         │
         ▼
┌─────────────────┐
│   MCP Server    │
│   (Backend)     │
│                 │
│  server.py      │
│  - Generates    │
│    HTML/CSS/JS  │
└────────┬────────┘
         │
         │ Returns JSON
         │ { game_ui: "<html>...</html>" }
         │
         ▼
┌─────────────────┐
│   Frontend      │
│                 │
│  Displays HTML  │
│  in iframe or   │
│  new tab        │
└─────────────────┘
```

## Next Steps

- Integrate with your AI agent to generate games on demand
- Add score tracking by calling `save_score` tool after games
- Display leaderboards by calling `get_high_scores` tool
- Customize the game HTML in `server.py` for your branding
