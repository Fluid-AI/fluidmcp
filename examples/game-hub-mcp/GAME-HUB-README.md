# 🎮 Game Hub MCP Server

A complete arcade with **15 fully playable games** accessible through the Model Context Protocol (MCP). All games are delivered as interactive HTML with CSS and JavaScript.

## 🎯 Features

- **15 Complete Games** - All playable in browser
- **2 MCP Tools** - Simple interface for listing and playing games
- **No External Dependencies** - Self-contained HTML games
- **Beautiful UI** - Modern design with gradients and animations
- **Instant Delivery** - Games returned as HTML in observation

## 🎲 Available Games

### 1. 🐍 Snake
Classic snake game - eat food and grow! Supports easy/medium/hard difficulty.
- **Controls**: Arrow keys or WASD
- **Features**: Score tracking, high scores, difficulty levels

### 2. 🚀 Space Impact
Shoot enemies in space! Classic shooter game.
- **Controls**: Arrow keys/WASD to move, Space to shoot
- **Features**: Lives system, score tracking

### 3. 🔢 Sudoku
Fill the grid with numbers 1-9
- **Controls**: Click cells and type numbers
- **Features**: New puzzle button, solution reveal

### 4. ❌ Tic-Tac-Toe
Three in a row wins!
- **Controls**: Click to place X or O
- **Features**: Two-player, win detection

### 5. 🧱 Breakout
Break all the bricks!
- **Controls**: Mouse to move paddle
- **Features**: Lives, score, brick destruction

### 6. ✊ Rock-Paper-Scissors
Beat the computer!
- **Controls**: Click your choice
- **Features**: Score tracking, visual feedback

### 7. 🏓 Pong
Classic paddle game
- **Controls**: Mouse to move paddle
- **Features**: AI opponent, score tracking

### 8. 🃏 Memory Matching
Find matching pairs!
- **Controls**: Click cards
- **Features**: Move counter, match tracking

### 9. 🎯 Number Guessing
Guess the secret number (1-100)
- **Controls**: Type number and click Guess
- **Features**: Hints (too high/low), attempt counter

### 10. 🐦 Flappy Bird
Fly between pipes!
- **Controls**: Click or tap to flap
- **Features**: Score, game over detection

### 11. 💣 Minesweeper
Find all the mines!
- **Controls**: Click to reveal, right-click to flag
- **Features**: 10x10 grid, flag counter

### 12. 🔢 2048
Merge tiles to reach 2048!
- **Controls**: Arrow keys to slide tiles
- **Features**: Score tracking, tile merging

### 13. 🔴 Connect Four
Connect 4 discs to win!
- **Controls**: Click column to drop disc
- **Features**: Two-player, win detection

### 14. 🔨 Whack-a-Mole
Whack as many moles as you can!
- **Controls**: Click moles
- **Features**: 30-second timer, score tracking

### 15. 👤 Hangman
Guess the word before time runs out!
- **Controls**: Click letters
- **Features**: 6 wrong guesses allowed, word bank

## 🚀 Quick Start

### Start the Server

```bash
cd /workspaces/fluidmcp
fluidmcp run examples/snake-game-config.json --file --start-server
```

Server will be available at:
- **Endpoint**: `http://localhost:8099/snake-game/mcp`
- **Codespaces**: `https://your-codespace-8099.app.github.dev/snake-game/mcp`

### Test from Command Line

```bash
# List all games
curl -X POST http://localhost:8099/snake-game/mcp \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "id": 1,
    "method": "tools/call",
    "params": {
      "name": "list_games",
      "arguments": {}
    }
  }'

# Play Snake game
curl -X POST http://localhost:8099/snake-game/mcp \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "id": 2,
    "method": "tools/call",
    "params": {
      "name": "play_game",
      "arguments": {
        "game_name": "snake",
        "difficulty": "medium"
      }
    }
  }'
```

## 🛠️ MCP Tools

### 1. `list_games`

Shows all 15 available games in a beautiful menu.

**When to use**: When user asks "I want to play a game" or wants to see options

**Parameters**: None

**Returns**: Interactive HTML menu with all 15 games

**Example**:
```json
{
  "name": "list_games",
  "arguments": {}
}
```

### 2. `play_game`

Starts a specific game and returns playable HTML.

**Parameters**:
- `game_name` (required): Game ID from list below
- `difficulty` (optional): "easy", "medium", or "hard" (for games that support it)

**Game IDs**:
- `snake`
- `space-impact`
- `sudoku`
- `tic-tac-toe`
- `breakout`
- `rock-paper-scissors`
- `pong`
- `memory`
- `number-guess`
- `flappy-bird`
- `minesweeper`
- `2048`
- `connect-four`
- `whack-a-mole`
- `hangman`

**Example**:
```json
{
  "name": "play_game",
  "arguments": {
    "game_name": "snake",
    "difficulty": "hard"
  }
}
```

## 📋 Integration Examples

### With AI Agent

```python
# User says: "I want to play a game"
# Agent calls:
response = call_mcp_tool("list_games", {})
# Returns HTML with all 15 game options

# User says: "Let me play Snake on hard mode"
# Agent calls:
response = call_mcp_tool("play_game", {
    "game_name": "snake",
    "difficulty": "hard"
})
# Returns complete playable Snake game HTML
```

### Expected Response Format

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "result": {
    "content": [
      {
        "type": "text",
        "text": "<!DOCTYPE html><html>...complete game HTML...</html>"
      }
    ]
  }
}
```

The HTML is self-contained with:
- ✅ All CSS styles embedded
- ✅ All JavaScript embedded
- ✅ No external dependencies
- ✅ Ready to display in iframe or new tab

## 🎨 Customization

### Add New Games

1. Create HTML generator function in [games_library.py](games_library.py)
2. Add game to `GAME_LIST` array
3. Add case in `play_game` tool handler in [server.py](server.py)

### Modify Existing Games

Edit the HTML generators in [games_library.py](games_library.py):
- `generate_snake_html()`
- `generate_space_impact_html()`
- `generate_tic_tac_toe_html()`
- etc.

## 📁 Project Structure

```
examples/snake-game-mcp/
├── server.py                  # Main MCP server with 2 tools
├── games_library.py           # HTML generators for all 15 games
├── GAME-HUB-README.md        # This file
├── demo-game.html            # Standalone demo
└── package.json              # Package metadata
```

## 🔧 Technical Details

- **Protocol**: MCP 2024-11-05
- **Server**: Python with mcp.server
- **Games**: Pure HTML/CSS/JavaScript
- **No Backend State**: Games run entirely client-side
- **Response Size**: 2-13KB per game

## 🐛 Troubleshooting

### Server not starting

```bash
# Check if port 8099 is available
netstat -tuln | grep 8099

# Check server logs
tail -f /tmp/game-hub-server.log
```

### Games not loading

Make sure the response HTML starts with `<!DOCTYPE html>` - your frontend should detect this and render it as HTML rather than text.

### Import errors

```bash
# Make sure MCP SDK is installed
pip install mcp

# Make sure games_library.py is in the same directory as server.py
ls -la examples/snake-game-mcp/
```

## 🎯 Use Cases

1. **AI Agent Gaming** - Let users play games through conversation
2. **Break Time** - Provide entertainment during long tasks
3. **Testing UI Delivery** - Example of HTML delivery through MCP
4. **Educational** - Learn game development concepts
5. **Stress Relief** - Quick games for users

## 📊 Game Statistics

| Game | Complexity | HTML Size | Controls |
|------|------------|-----------|----------|
| Snake | Medium | 3.3 KB | Keyboard |
| Space Impact | Medium | 2.1 KB | Keyboard |
| Sudoku | Low | 2.5 KB | Mouse |
| Tic-Tac-Toe | Low | 2.5 KB | Mouse |
| Breakout | Medium | 2.4 KB | Mouse |
| Rock-Paper-Scissors | Low | 1.8 KB | Mouse |
| Pong | Medium | 2.2 KB | Mouse |
| Memory | Medium | 2.3 KB | Mouse |
| Number Guess | Low | 1.7 KB | Keyboard |
| Flappy Bird | Medium | 2.0 KB | Mouse |
| Minesweeper | High | 2.9 KB | Mouse |
| 2048 | High | 2.8 KB | Keyboard |
| Connect Four | Medium | 2.6 KB | Mouse |
| Whack-a-Mole | Medium | 2.4 KB | Mouse |
| Hangman | Medium | 2.3 KB | Mouse |

## 🚀 What's Next?

- [ ] Add multiplayer support
- [ ] Persistent high scores across sessions
- [ ] More games (Chess, Checkers, etc.)
- [ ] Difficulty customization for all games
- [ ] Touch controls for mobile
- [ ] Sound effects
- [ ] Achievements system

## 📝 License

Part of the FluidMCP project. See main LICENSE file.

## 🙏 Credits

Built with ❤️ using:
- **MCP Protocol** by Anthropic
- **Python mcp.server** SDK
- **HTML5 Canvas** for graphics
- **Pure JavaScript** for game logic

---

**Ready to play?** Start the server and call `list_games` to see all options! 🎮
