# Netlify Deploy MCP Server

An MCP server that generates static websites from prompts and automatically deploys them to Netlify. Supports todo apps, portfolio websites, and landing pages.

## Features

- **Automatic Website Generation**: Create complete static websites from simple prompts
- **Netlify Integration**: Automatic deployment with live URL generation
- **Multiple Templates**: Todo app, portfolio, and landing page templates
- **Responsive Design**: All templates are mobile-friendly and modern
- **No Frameworks**: Pure HTML, CSS, and JavaScript for simplicity
- **Production Ready**: Includes netlify.toml configuration

## Prerequisites

Before using this MCP server, you need:

1. **Python 3.8+** with `mcp` library installed
2. **Netlify CLI** installed globally:
   ```bash
   npm install -g netlify-cli
   ```
3. **Netlify Account** and authentication:
   ```bash
   netlify login
   ```

## Installation & Usage

### Using with FluidMCP

1. Make sure you have FluidMCP installed:
```bash
pip install -r requirements.txt
pip install -e .
```

2. Install Netlify CLI if you haven't already:
```bash
npm install -g netlify-cli
netlify login
```

3. Run the server using the example config:
```bash
fluidmcp run examples/netlify-deploy-config.json --file --start-server
```

4. The server will start on `http://localhost:8099`

5. Access the API documentation at `http://localhost:8099/docs`

## Available Tools

### 1. `generate_and_deploy_website`
Generate a website and automatically deploy it to Netlify in one step.

**Parameters:**
- `site_type` (required): Type of website - "todo", "portfolio", or "landing"
- `site_name` (required): Name for the site (used for directory and Netlify site name)
- `custom_content` (optional): Object with custom content (title, description, etc.)

**Example Request:**
```bash
curl -X POST http://localhost:8099/netlify-deploy/mcp \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "id": 1,
    "method": "tools/call",
    "params": {
      "name": "generate_and_deploy_website",
      "arguments": {
        "site_type": "todo",
        "site_name": "my-awesome-todo-app",
        "custom_content": {
          "title": "My Tasks"
        }
      }
    }
  }'
```

**Response:**
```json
{
  "status": "success",
  "message": "Successfully generated and deployed todo website",
  "site_name": "my-awesome-todo-app",
  "project_path": "/home/user/.netlify-mcp/sites/my-awesome-todo-app_20240210_123456",
  "live_url": "https://my-awesome-todo-app.netlify.app",
  "site_type": "todo"
}
```

### 2. `generate_website_files`
Generate website files without deploying (useful for testing or manual deployment).

**Parameters:**
- `site_type` (required): Type of website - "todo", "portfolio", or "landing"
- `site_name` (required): Name for the site directory
- `custom_content` (optional): Object with custom content

**Example Request:**
```bash
curl -X POST http://localhost:8099/netlify-deploy/mcp \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "id": 2,
    "method": "tools/call",
    "params": {
      "name": "generate_website_files",
      "arguments": {
        "site_type": "portfolio",
        "site_name": "john-doe-portfolio",
        "custom_content": {
          "title": "John Doe",
          "description": "Full Stack Developer"
        }
      }
    }
  }'
```

### 3. `deploy_to_netlify`
Deploy an existing project directory to Netlify.

**Parameters:**
- `project_path` (required): Path to the project directory
- `site_name` (optional): Name for the Netlify site

**Example Request:**
```bash
curl -X POST http://localhost:8099/netlify-deploy/mcp \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "id": 3,
    "method": "tools/call",
    "params": {
      "name": "deploy_to_netlify",
      "arguments": {
        "project_path": "/home/user/.netlify-mcp/sites/my-site",
        "site_name": "my-custom-site"
      }
    }
  }'
```

## Website Templates

### Todo App
- **Features**: Add, delete, mark complete, localStorage persistence
- **Sections**: Input field, task list, filters (all/active/completed), clear completed button
- **Storage**: Automatic localStorage persistence
- **Design**: Modern gradient design with responsive layout

### Portfolio Website
- **Sections**: Navigation, hero, about, skills, projects, contact, footer
- **Features**: Smooth scrolling, mobile menu, responsive grid
- **Design**: Professional gradient theme with animations

### Landing Page
- **Sections**: Hero, features (6 cards), benefits, CTA with email form, footer
- **Features**: Email capture form, smooth animations, scroll effects
- **Design**: Marketing-focused with bold CTAs

## File Structure

Generated sites include:
- `index.html` - Main HTML structure
- `style.css` - Complete responsive styling
- `script.js` - Interactive functionality
- `netlify.toml` - Netlify configuration

All files are stored in `~/.netlify-mcp/sites/` with timestamped directories.

## Configuration

You can customize the server by modifying the configuration in your FluidMCP config file:

```json
{
  "mcpServers": {
    "netlify-deploy": {
      "command": "python3",
      "args": [
        "/path/to/netlify-deploy-mcp/server.py"
      ],
      "env": {}
    }
  }
}
```

## Error Handling

The server handles common errors:

- **Missing Netlify CLI**: Returns error with installation instructions
- **Deployment Failure**: Retries without site name to create new site
- **File Write Issues**: Returns detailed error messages
- **Invalid Site Type**: Validates site type before generation
- **Timeout**: 5-minute timeout for deployments

## Troubleshooting

### Netlify CLI Not Found
```bash
npm install -g netlify-cli
```

### Not Logged In
```bash
netlify login
```

### Deployment Permission Denied
Make sure you're logged in and have the correct permissions:
```bash
netlify status
```

### Custom Domain
To use a custom domain, add it in your Netlify dashboard after deployment.

## Development

To modify templates:

1. Edit the generator functions in `server.py`:
   - `generate_todo_app()`
   - `generate_portfolio()`
   - `generate_landing_page()`

2. Test your changes:
```bash
fluidmcp run examples/netlify-deploy-config.json --file --start-server
```

3. The generated files are stored in `~/.netlify-mcp/sites/` for inspection

## Architecture

The server implements the MCP protocol with three main tools:
1. **generate_and_deploy_website**: Full workflow (generate + deploy)
2. **generate_website_files**: Generation only
3. **deploy_to_netlify**: Deployment only

Key components:
- Template generators with responsive HTML/CSS/JS
- File system operations with error handling
- Netlify CLI wrapper with timeout and retry logic
- Async workflow orchestration

## Examples

### Create a Todo App
```bash
curl -X POST http://localhost:8099/netlify-deploy/mcp \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "id": 1,
    "method": "tools/call",
    "params": {
      "name": "generate_and_deploy_website",
      "arguments": {
        "site_type": "todo",
        "site_name": "my-tasks"
      }
    }
  }'
```

### Create a Portfolio
```bash
curl -X POST http://localhost:8099/netlify-deploy/mcp \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "id": 1,
    "method": "tools/call",
    "params": {
      "name": "generate_and_deploy_website",
      "arguments": {
        "site_type": "portfolio",
        "site_name": "jane-developer",
        "custom_content": {
          "title": "Jane Developer",
          "description": "Senior Software Engineer"
        }
      }
    }
  }'
```

### Create a Landing Page
```bash
curl -X POST http://localhost:8099/netlify-deploy/mcp \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "id": 1,
    "method": "tools/call",
    "params": {
      "name": "generate_and_deploy_website",
      "arguments": {
        "site_type": "landing",
        "site_name": "awesome-product",
        "custom_content": {
          "title": "SuperApp",
          "description": "The Ultimate Productivity Tool"
        }
      }
    }
  }'
```

## License

This Netlify Deploy MCP server is part of the FluidMCP project.
