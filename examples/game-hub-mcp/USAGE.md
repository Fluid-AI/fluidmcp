# Snake Game MCP Server - Usage Guide

This guide shows you how to use the Snake Game MCP server with FluidMCP.

## Quick Start

### 1. Start the Server

Run the snake game server using FluidMCP:

```bash
fluidmcp run examples/snake-game-config.json --file --start-server
```

The server will start and be available at:
- Main endpoint: `http://localhost:8099`
- API documentation: `http://localhost:8099/docs`
- MCP endpoint: `http://localhost:8099/snake-game/mcp`

### 2. Test the Server

List available tools:

```bash
curl -X POST http://localhost:8099/snake-game/mcp \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "id": 1,
    "method": "tools/list"
  }'
```

### 3. Start a Game

Request a new game with custom settings:

```bash
curl -X POST http://localhost:8099/snake-game/mcp \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "id": 2,
    "method": "tools/call",
    "params": {
      "name": "start_game",
      "arguments": {
        "difficulty": "hard",
        "board_size": "large"
      }
    }
  }' | python3 -m json.tool
```

The response will include:
- `status`: Success/error status
- `message`: Confirmation message
- `game_ui`: Complete HTML for the interactive game (as a string)
- `settings`: Applied game settings

### 4. Save the Game HTML

Extract and save the game HTML to a file:

```bash
# This script extracts the game HTML from the MCP response
curl -X POST http://localhost:8099/snake-game/mcp \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "id": 2,
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
with open('my-snake-game.html', 'w') as f:
    f.write(game_data['game_ui'])
print('Game saved to my-snake-game.html')
"
```

Then open `my-snake-game.html` in your browser to play!

## Available Tools

### 1. start_game

Generates a new snake game with customizable settings.

**Parameters:**
- `difficulty` (optional): "easy", "medium", or "hard"
  - Easy: 150ms per frame (slower)
  - Medium: 100ms per frame (default)
  - Hard: 50ms per frame (faster)

- `board_size` (optional): "small", "medium", or "large"
  - Small: 20x20 grid
  - Medium: 30x30 grid (default)
  - Large: 40x40 grid

**Example:**
```bash
curl -X POST http://localhost:8099/snake-game/mcp \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "id": 2,
    "method": "tools/call",
    "params": {
      "name": "start_game",
      "arguments": {
        "difficulty": "easy",
        "board_size": "small"
      }
    }
  }'
```

### 2. get_high_scores

Retrieves the leaderboard of high scores.

**Parameters:**
- `limit` (optional): Number of scores to return (default: 10)

**Example:**
```bash
curl -X POST http://localhost:8099/snake-game/mcp \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "id": 3,
    "method": "tools/call",
    "params": {
      "name": "get_high_scores",
      "arguments": {
        "limit": 5
      }
    }
  }'
```

**Response:**
```json
{
  "status": "success",
  "high_scores": [
    {
      "player_name": "Alice",
      "score": 350,
      "difficulty": "hard",
      "timestamp": "2024-02-09T10:30:00"
    },
    ...
  ]
}
```

### 3. save_score

Saves a game score to the leaderboard.

**Parameters:**
- `player_name` (required): Player's name
- `score` (required): Game score
- `difficulty` (optional): Difficulty level played

**Example:**
```bash
curl -X POST http://localhost:8099/snake-game/mcp \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "id": 4,
    "method": "tools/call",
    "params": {
      "name": "save_score",
      "arguments": {
        "player_name": "Bob",
        "score": 280,
        "difficulty": "medium"
      }
    }
  }'
```

**Response:**
```json
{
  "status": "success",
  "message": "Score saved!",
  "score_entry": {
    "player_name": "Bob",
    "score": 280,
    "difficulty": "medium",
    "timestamp": "2024-02-09T10:35:00"
  },
  "rank": 3
}
```

## Game Controls

Once you have the game HTML open in a browser:

- **Arrow Keys** or **WASD**: Control snake direction
- **Space Bar**: Pause/Resume game
- **Start Button**: Begin playing
- **Pause Button**: Pause the game
- **Reset Button**: Reset to initial state

## Integration with AI Agents

The snake game MCP server is designed to work with AI agents. An agent can:

1. **Call `start_game`** to generate the interactive UI
2. **Return the HTML** to the user's frontend (e.g., in an iframe or new tab)
3. **Call `save_score`** when the user completes a game
4. **Call `get_high_scores`** to show leaderboards

### Example Agent Flow

```python
# Pseudo-code for an AI agent integration

user_asks("I want to play snake game with hard difficulty")

# Agent calls the MCP tool
response = call_mcp_tool(
    server="snake-game",
    tool="start_game",
    arguments={"difficulty": "hard", "board_size": "medium"}
)

# Extract the HTML
game_html = response["game_ui"]

# Display to user (implementation depends on your frontend)
display_in_iframe(game_html)
# or
open_in_new_tab(game_html)
# or
save_and_return_url(game_html)

agent_says("Here's your snake game! Use arrow keys or WASD to play.")
```

## Customization

### Modify Game Speed

Edit the difficulty mapping in [server.py](server.py):

```python
speed_map = {
    "easy": 150,      # Slower
    "medium": 100,    # Default
    "hard": 50        # Faster
}
```

### Modify Board Sizes

Edit the size mapping in [server.py](server.py):

```python
size_map = {
    "small": 20,      # 20x20 grid
    "medium": 30,     # 30x30 grid
    "large": 40       # 40x40 grid
}
```

### Customize Colors

Edit the CSS in the `generate_game_html()` method to change:
- Background gradients
- Snake colors
- Food color
- Button styles

## Troubleshooting

### Server won't start

Make sure Python 3 is installed:
```bash
python3 --version
```

### Port already in use

Change the port in your FluidMCP config or stop other services using port 8099:
```bash
lsof -i :8099
```

### Game HTML not displaying

Make sure you're extracting the HTML correctly from the JSON response. The game UI is nested in:
```
response -> result -> content[0] -> text (parse as JSON) -> game_ui
```

## Demo

A demo HTML file is included: [demo-game.html](demo-game.html)

Open it directly in your browser to see what the game looks like without needing to run the MCP server.

## Next Steps

- Integrate with your AI agent or application
- Customize the game appearance and mechanics
- Add more difficulty levels or game modes
- Implement persistent storage for high scores (currently in-memory)
- Add multiplayer features

## Support

For issues or questions:
- Check the [README.md](README.md) for architecture details
- Review the [server.py](server.py) source code
- Open an issue in the FluidMCP repository
