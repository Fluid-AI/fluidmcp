# Custom Website Generation with AI

Your Netlify Deploy MCP Server now supports generating **ANY kind of single-page application** dynamically using AI!

## How It Works

The server uses Claude AI to generate custom HTML, CSS, and JavaScript based on your natural language prompts.

### Pre-defined Templates (Fast, No API Key Required)

For common site types, the server uses optimized templates:

- ✅ **Todo Apps**: "create a todo app", "make a task manager"
- 💼 **Portfolio Websites**: "build a portfolio", "create a resume site"
- 🚀 **Landing Pages**: "create a landing page", "make a product page"

### Custom Generation (Requires API Key)

For any other type of application, the server uses AI to generate it:

- 🧮 "create a calculator app"
- 🌤️ "build a weather dashboard"
- ⏰ "make a countdown timer"
- 🖼️ "create a photo gallery"
- 📝 "build a note-taking app"
- 🎮 "create a memory card game"
- 💱 "make a currency converter"
- 🎨 "build a color picker tool"
- **...anything you can imagine!**

## Setup for Custom Generation

### Step 1: Get an Anthropic API Key

1. Go to: https://console.anthropic.com/
2. Sign up or log in
3. Navigate to API Keys
4. Create a new API key
5. Copy the key (starts with `sk-ant-...`)

### Step 2: Add API Key to Configuration

Edit `examples/netlify-deploy-config.json`:

```json
{
  "mcpServers": {
    "netlify-deploy": {
      "command": "python3",
      "args": [
        "/workspaces/fluidmcp/examples/netlify-deploy-mcp/server.py"
      ],
      "env": {
        "NETLIFY_AUTH_TOKEN": "nfp_5zLPPdQdtB7VpqRVEjTb3YnWSnxNZK12d8e8",
        "ANTHROPIC_API_KEY": "sk-ant-your-key-here"
      }
    }
  }
}
```

### Step 3: Restart the Server

```bash
fluidmcp run examples/netlify-deploy-config.json --file --start-server
```

## Usage Examples

Once configured, just ask for any kind of application:

### Via MCP Agent

```
"create a calculator app with basic operations"
"build a simple quiz application with 5 questions"
"make a countdown timer for events"
"create a BMI calculator"
"build a tip calculator for restaurants"
"make a pomodoro timer"
"create a random password generator"
"build a unit converter (length, weight, temperature)"
```

### What You Get

The AI generates:
- ✅ Complete HTML structure
- ✅ Beautiful CSS with modern design
- ✅ Fully functional JavaScript
- ✅ Responsive mobile layout
- ✅ Interactive features
- ✅ LocalStorage persistence (when applicable)
- ✅ Error handling
- ✅ Professional UI/UX

## Generation Time

- **Pre-defined templates**: < 1 second
- **AI-generated custom sites**: 10-20 seconds (one-time generation)
- **Deployment**: 60-90 seconds (background, for all sites)

## Fallback Behavior

If `ANTHROPIC_API_KEY` is not set:
- Pre-defined templates (todo, portfolio, landing) still work perfectly
- Custom prompts will return an error asking you to configure the API key

## Cost

Anthropic API costs:
- Claude 3.5 Sonnet: $3 per million input tokens, $15 per million output tokens
- Typical website generation: ~1000 input tokens, ~3000 output tokens
- **Cost per website**: ~$0.05 (5 cents)

You get $5 free credits when you sign up, enough for ~100 websites!

## Examples of Generated Sites

### Calculator App
```
Prompt: "create a calculator app with basic arithmetic operations"

Generated:
- Display screen
- Number buttons (0-9)
- Operation buttons (+, -, *, /)
- Clear and equals buttons
- Keyboard support
- Beautiful gradient design
```

### Quiz Application
```
Prompt: "build a trivia quiz app about space"

Generated:
- Multiple choice questions
- Score tracking
- Progress indicator
- Next/Previous navigation
- Results summary at the end
- Restart option
```

### Timer App
```
Prompt: "create a pomodoro timer"

Generated:
- 25-minute work timer
- 5-minute break timer
- Start/Pause/Reset controls
- Visual progress indicator
- Audio notification when complete
- Session counter
```

## Tips for Best Results

1. **Be specific**: "create a calculator with scientific functions" vs "make a calculator"
2. **Mention features**: "build a todo app with categories and due dates"
3. **Specify design**: "make a dark-themed weather dashboard"
4. **Include interactions**: "create a memory game with flip animations"

## Limitations

- Single-page applications only (no multi-page sites)
- No backend/server-side code (static sites only)
- No external API dependencies (unless explicitly provided in prompt)
- Generated in one go (not iterative refinement)

## Support

If custom generation isn't working:
1. Verify `ANTHROPIC_API_KEY` is correctly set
2. Check server logs: `tail -f /tmp/server.log`
3. Ensure `anthropic` package is installed: `pip install anthropic`
4. Test pre-defined templates first (todo/portfolio/landing)

---

**Ready to create amazing custom websites? Just ask!** 🚀
