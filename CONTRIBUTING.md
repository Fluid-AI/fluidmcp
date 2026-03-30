# Contributing to FluidMCP

Thank you for your interest in contributing to FluidMCP! This guide will help you get started with development and contribution.

## 🚀 Development Setup

### Prerequisites

- Python 3.6 or higher
- Git

### Setting Up Your Development Environment

1. **Fork and Clone the Repository**

```bash
git clone https://github.com/YOUR_USERNAME/fluidmcp.git
cd fluidmcp
```

2. **Install Dependencies**

```bash
pip install -r requirements.txt
```

3. **Install in Development Mode**

Install the package in editable mode so your code changes take effect immediately:

```bash
pip install -e .
```

4. **Verify Installation**

After installation, you can run the CLI using any of these commands:

```bash
fluidmcp --help
# or
fmcp --help
# or
fluidai-mcp --help
```

5. **Test with Sample Configurations**

We provide sample configuration files in the `examples/` directory for testing. These configs use direct server specifications (no installation required):

```bash
# Create a test directory
mkdir -p /tmp/test-directory

# Run with sample config
fluidmcp run examples/sample-config.json --file --start-server

# Server will start on port 8099 with Swagger UI at http://localhost:8099/docs

# In another terminal, test the endpoint
curl -X POST http://localhost:8099/filesystem/mcp \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc": "2.0", "id": 1, "method": "tools/list"}'
```

The sample configs work immediately without any package installation. FluidMCP automatically creates temporary metadata files for direct server configurations.

See [examples/README.md](examples/README.md) for more testing scenarios and available sample configurations.

## 📁 Project Structure

```
fluidmcp/
├── fluidai_mcp/
│   ├── cli.py                 # Main CLI implementation with argument parsing
│   └── services/              # Core services layer
│       ├── package_installer.py   # MCP package installation
│       ├── package_launcher.py    # Launch MCP servers via FastAPI
│       ├── env_manager.py         # Environment variable management
│       ├── s3_utils.py            # S3 upload/download for master mode
│       ├── network_utils.py       # Port management utilities
│       └── package_list.py        # Package version resolution
├── examples/                  # Sample configurations for testing
│   ├── README.md              # Examples documentation
│   ├── sample-config.json     # Basic config with two servers
│   ├── sample-metadata.json   # Sample package metadata
│   └── sample-config-with-api-keys.json  # Config with API keys
├── setup.py                   # Package configuration and entry points
├── requirements.txt           # Python dependencies
├── README.md                  # User documentation
├── CONTRIBUTING.md            # Developer documentation (this file)
├── CLAUDE.md                  # AI assistant guidance
└── LICENSE                    # GPL-3.0 License
```

### Key Components

- **Entry Point**: `fluidai_mcp/cli.py` - Main CLI with command handlers
- **Services**: `fluidai_mcp/services/` - Core functionality modules
- **Installation Directory**: `.fmcp-packages/Author/Package/Version/`
- **Default Ports**:
  - `8090` - Individual package server (MCP_CLIENT_SERVER_PORT)
  - `8099` - All packages unified server (MCP_CLIENT_SERVER_ALL_PORT)

## 🛠️ Development Workflow

### Making Changes

1. **Create a Feature Branch**

```bash
git checkout -b feature/your-feature-name
```

2. **Make Your Changes**

Edit the code in your favorite editor. Since you installed with `-e`, changes take effect immediately.

3. **Test Your Changes**

Manually test your changes by running the CLI:

```bash
fluidmcp list
fluidmcp run all --start-server
# etc.
```

4. **Commit Your Changes**

```bash
git add .
git commit -m "Description of your changes"
```

Follow conventional commit messages:
- `feat:` - New feature
- `fix:` - Bug fix
- `docs:` - Documentation changes
- `refactor:` - Code refactoring
- `test:` - Adding tests
- `chore:` - Maintenance tasks

### Testing

Currently, there are no automated tests in the repository. When contributing:

- Manually test all affected functionality
- Test edge cases and error conditions
- Verify existing features still work

**Note**: Contributions that add test coverage are highly welcomed!

## 📝 Code Style Guidelines

- Follow PEP 8 Python style guidelines
- Use meaningful variable and function names
- Add docstrings to functions and classes
- Keep functions focused and modular
- Handle errors gracefully with appropriate logging

## 🔧 Key Data Structures

### MCP Server Configuration Format

```json
{
  "mcpServers": {
    "server-name": {
      "command": "npx",
      "args": ["-y", "@package/server"],
      "env": {
        "API_KEY": "value"
      }
    }
  }
}
```

### Package Metadata

Each installed package has a `metadata.json` file in `.fmcp-packages/Author/Package/Version/`:

```json
{
  "mcpServers": {
    "maps": {
      "command": "npx",
      "args": ["-y", "@package/server"],
      "env": {
        "API_KEY": "xxx"
      }
    }
  }
}
```

## 🌍 Environment Variables

When developing features that use environment variables:

```bash
# S3 credentials (for --master mode)
export S3_BUCKET_NAME="..."
export S3_ACCESS_KEY="..."
export S3_SECRET_KEY="..."
export S3_REGION="..."

# Registry access
export MCP_FETCH_URL="https://registry.fluidmcp.com/fetch-mcp-package"
export MCP_TOKEN="..."

# Port configuration
export MCP_CLIENT_SERVER_PORT=8090
export MCP_CLIENT_SERVER_ALL_PORT=8099
```

## 🚀 Submitting a Pull Request

1. **Push Your Branch**

```bash
git push origin feature/your-feature-name
```

2. **Create a Pull Request**

- Go to the [FluidMCP repository](https://github.com/Fluid-AI/fluidmcp)
- Click "New Pull Request"
- Select your branch
- Fill out the PR template with:
  - **Summary**: What does this PR do?
  - **Changes**: List of changes made
  - **Testing**: How did you test it?
  - **Related Issues**: Link any related issues

3. **PR Review Process**

- Maintainers will review your PR
- Address any feedback or requested changes
- Once approved, your PR will be merged!

## 🐛 Reporting Issues

Found a bug or have a feature request?

1. Check if an issue already exists
2. If not, create a new issue with:
   - Clear, descriptive title
   - Steps to reproduce (for bugs)
   - Expected vs actual behavior
   - Environment details (OS, Python version, etc.)
   - Relevant logs or screenshots

## 💡 Feature Requests

We welcome feature requests! When proposing a feature:

- Explain the use case and problem it solves
- Describe your proposed solution
- Consider alternative approaches
- Be open to feedback and discussion

## 📚 Additional Resources

- [MCP Protocol Documentation](https://modelcontextprotocol.io/)
- [FastAPI Documentation](https://fastapi.tiangolo.com/)
- [Python Packaging Guide](https://packaging.python.org/)

## 🤝 Code of Conduct

- Be respectful and inclusive
- Welcome newcomers and help them learn
- Focus on constructive feedback
- Assume good intentions

## 📄 License

By contributing to FluidMCP, you agree that your contributions will be licensed under the [GNU General Public License v3.0](LICENSE).

---

**Questions?** Feel free to open an issue or reach out to the maintainers. We're here to help!

Thank you for contributing to FluidMCP! 🌀
