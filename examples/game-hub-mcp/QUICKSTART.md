# Snake Game MCP - Quick Start Guide

Get your snake game up and running in 3 minutes!

## 🚀 Step 1: Start the MCP Backend Server

Open a terminal and run:

```bash
cd /workspaces/fluidmcp
fluidmcp run examples/snake-game-config.json --file --start-server
```

You should see output like:
```
✓ MCP Server started on http://localhost:8099
✓ API docs available at http://localhost:8099/docs
✓ snake-game endpoint: http://localhost:8099/snake-game/mcp
```

Keep this terminal open! The backend is now running and ready to send game HTML.

## 🎮 Step 2: Open the Frontend

You have 3 options:

### Option A: Use the Frontend Demo (Recommended)

Open `frontend-demo.html` in your browser:

```bash
# On Linux/Mac
open examples/snake-game-mcp/frontend-demo.html

# Or just navigate to:
# file:///workspaces/fluidmcp/examples/snake-game-mcp/frontend-demo.html
```

Then click **"Start Game (In Page)"** and the backend will send the complete game HTML to display in the page!

### Option B: Test with curl and save HTML

```bash
# Call the backend MCP endpoint
curl -X POST http://localhost:8099/snake-game/mcp \
  -H "Content-Type: application/json" \
  -d '{
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
  }' | python3 -c "
import sys, json
data = json.load(sys.stdin)
game_data = json.loads(data['result']['content'][0]['text'])
with open('my-game.html', 'w') as f:
    f.write(game_data['game_ui'])
print('✓ Game HTML saved to my-game.html - open it in your browser!')
"
```

### Option C: Use the Pre-generated Demo

Simply open the demo file:

```bash
open examples/snake-game-mcp/demo-game.html
```

This is a pre-generated HTML file that shows what the backend sends.

## 🎯 How It Works

```
┌──────────────┐
│   Frontend   │  1. User clicks "Start Game"
│   (Browser)  │  2. Frontend calls: POST http://localhost:8099/snake-game/mcp
└──────┬───────┘     with: { method: "tools/call", name: "start_game" }
       │
       │ HTTP Request
       │
       ▼
┌──────────────┐
│  MCP Backend │  3. Backend generates complete HTML/CSS/JS
│  (server.py) │  4. Returns: { game_ui: "<html>...full game...</html>" }
└──────┬───────┘
       │
       │ HTTP Response
       │
       ▼
┌──────────────┐
│   Frontend   │  5. Frontend receives HTML string
│   (Browser)  │  6. Displays it in an iframe
│              │  7. User plays the game!
└──────────────┘
```

## 🔧 Customize the Game

Edit settings in the frontend:

- **Difficulty**: Easy (slower), Medium (normal), Hard (faster)
- **Board Size**: Small (20x20), Medium (30x30), Large (40x40)

Or pass arguments in your API call:

```javascript
{
  "name": "start_game",
  "arguments": {
    "difficulty": "hard",
    "board_size": "large"
  }
}
```

## 📖 Learn More

- **[BACKEND-FRONTEND-FLOW.md](BACKEND-FRONTEND-FLOW.md)** - Detailed explanation of how backend sends HTML to frontend
- **[USAGE.md](USAGE.md)** - Complete API reference and examples
- **[README.md](README.md)** - Architecture and technical details
- **[frontend-demo.html](frontend-demo.html)** - Live frontend example with source code

## 🎮 Game Controls

- **Arrow Keys** or **WASD**: Move snake
- **Space**: Pause/Resume
- **Start Button**: Begin game
- **Reset Button**: Reset game

## ❓ Troubleshooting

### Backend not starting?

Make sure FluidMCP is installed:
```bash
pip install -r requirements.txt
pip install -e .
```

### Frontend can't connect?

1. Make sure backend is running (Step 1)
2. Check the URL is correct: `http://localhost:8099/snake-game/mcp`
3. Check browser console for errors (F12)

### Port 8099 already in use?

Change the port in your FluidMCP config or stop other services.

## 🎉 That's It!

You now have a fully functional snake game where:
- ✅ Backend generates and sends complete HTML/CSS/JS
- ✅ Frontend receives and displays it
- ✅ No external dependencies needed
- ✅ Perfect for AI agent integration

Have fun! 🐍
