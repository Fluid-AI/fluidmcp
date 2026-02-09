# Snake Game MCP Server

An interactive snake game delivered through the Model Context Protocol (MCP). This server provides tools to start and play a fully functional snake game with customizable difficulty and board sizes.

## Features

- **Fully Playable Snake Game**: Classic snake game with smooth controls
- **Multiple Difficulty Levels**: Easy, Medium, and Hard modes
- **Customizable Board Sizes**: Small (20x20), Medium (30x30), and Large (40x40)
- **Score Tracking**: Local high score persistence
- **Beautiful UI**: Modern, responsive design with gradient colors
- **Keyboard Controls**: Arrow keys or WASD for movement

## Installation & Usage

### Using with FluidMCP

1. Make sure you have FluidMCP installed:
```bash
pip install -r requirements.txt
pip install -e .
```

2. Run the snake game server using the example config:
```bash
fluidmcp run examples/snake-game-config.json --file --start-server
```

3. The server will start on `http://localhost:8099`

4. Access the API documentation at `http://localhost:8099/docs`

## Available Tools

### 1. `start_game`
Starts a new snake game and returns the interactive HTML UI.

**Parameters:**
- `difficulty` (optional): Game difficulty - "easy", "medium", or "hard" (default: "medium")
- `board_size` (optional): Board size - "small", "medium", or "large" (default: "medium")

**Example Request:**
```bash
curl -X POST http://localhost:8099/snake-game/mcp \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "id": 1,
    "method": "tools/call",
    "params": {
      "name": "start_game",
      "arguments": {
        "difficulty": "hard",
        "board_size": "large"
      }
    }
  }'
```

**Response:**
Returns a JSON object containing:
- `status`: "success"
- `message`: Confirmation message
- `game_ui`: Complete HTML for the interactive game
- `settings`: Applied game settings

### 2. `get_high_scores`
Retrieves the top high scores from the leaderboard.

**Parameters:**
- `limit` (optional): Number of scores to return (default: 10)

**Example Request:**
```bash
curl -X POST http://localhost:8099/snake-game/mcp \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "id": 2,
    "method": "tools/call",
    "params": {
      "name": "get_high_scores",
      "arguments": {
        "limit": 5
      }
    }
  }'
```

### 3. `save_score`
Saves a game score to the leaderboard.

**Parameters:**
- `player_name` (required): Player name
- `score` (required): Game score
- `difficulty` (optional): Difficulty level

**Example Request:**
```bash
curl -X POST http://localhost:8099/snake-game/mcp \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "id": 3,
    "method": "tools/call",
    "params": {
      "name": "save_score",
      "arguments": {
        "player_name": "Alice",
        "score": 150,
        "difficulty": "hard"
      }
    }
  }'
```

## Game Controls

- **Arrow Keys** or **WASD**: Move the snake
- **Space Bar**: Pause/Resume the game
- **Start Button**: Begin a new game
- **Pause Button**: Pause the current game
- **Reset Button**: Reset the game

## Game Rules

1. Control the snake to eat the red food
2. Each food eaten increases your score by 10 points
3. The snake grows longer with each food eaten
4. Don't hit the walls or yourself!
5. Try to beat your high score

## Technical Details

- **Protocol**: Model Context Protocol (MCP) 2024-11-05
- **Language**: Python 3
- **UI**: HTML5 Canvas with JavaScript
- **Storage**: LocalStorage for high scores (client-side)

## Configuration

You can customize the server by modifying the configuration in your FluidMCP config file:

```json
{
  "mcpServers": {
    "snake-game": {
      "command": "python3",
      "args": [
        "/path/to/snake-game-mcp/server.py"
      ],
      "env": {}
    }
  }
}
```

## Architecture

The server implements the MCP protocol with three main tools:
1. **start_game**: Generates and returns the complete HTML/CSS/JS game
2. **get_high_scores**: Retrieves stored high scores
3. **save_score**: Persists scores to the leaderboard

The game UI is fully self-contained in the returned HTML, making it easy to embed in any frontend application.

## Development

To modify the game:

1. Edit `server.py` to change game logic or add new tools
2. Modify the `generate_game_html()` method to customize the UI
3. Test your changes:
```bash
fluidmcp run examples/snake-game-config.json --file --start-server
```

## License

This snake game MCP server is part of the FluidMCP project.
