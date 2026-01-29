## Overview: How FluidMCP Handles metadata.json

In FluidMCP, metadata.json is not a single static schema.
Instead, it represents the final normalized runtime configuration that FluidMCP uses to start MCP servers.

Users are allowed to define MCP servers in multiple ways (package references, GitHub repositories, or direct commands). FluidMCP resolves all these inputs into a uniform executable structure before running the servers.

The goal of this design is to provide flexibility at the input level while keeping execution logic simple and predictable.

### Conceptual Model
FluidMCP processes server configuration in three conceptual layers:

1. Input Layer (User-Facing Configuration)

Users define servers using one of the supported configuration formats:
    - Package string reference
    - Direct command configuration
    - GitHub repository reference

These inputs may appear in:
    - A local JSON file
    - An S3-hosted configuration
    - CLI-provided configuration

These formats are not executed directly.


2. Resolution Layer (Internal Processing)

FluidMCP resolves user input by:
    - Installing packages
    - Cloning GitHub repositories
    - Reading or generating metadata.json
    - Extracting commands from README files when needed
    - Injecting runtime fields such as ports and installation paths
At the end of this process, all servers are normalized into the same runtime format.

3. Runtime Metadata Layer (Executable Truth)

All resolved configurations converge into a canonical structure:
{
    "mcpServers": {
        "<serverName>": {
        "command": "string",
        "args": ["string"],
        "env": {},
        "port": "number",
        "install_path": "string"
        }
    }
}


This is the only format consumed by:
    - The MCP launcher
    - Port assignment logic
    - Metadata merging
    - S3 synchronization

Files such as `examples/sample-metadata.json` represent this final resolved state, not all possible input formats.

### metadata.json Structure

Top-Level Structure
{
  "mcpServers": { }
}

    Field   => mcpServers			
    Required  => Yes
    Type    =>  object 
    Description => Map of MCP server definitions

Keys are server names (strings)
Values define how each server is configured

## Server Entry Types

Each entry inside mcpServers can be one of the following:
    String → Package reference
    Object → Direct configuration or GitHub configuration

The allowed shape depends on the configuration format used.

## Runtime Server Fields (Resolved Metadata)

After resolution, every server entry contains the following fields:

Field	        Required	            Description
command	        Yes	            Executable used to start the server
args	          Yes	            Command-line arguments
env	            No	            Environment variables
port	          Yes (auto)	    Unique port assigned by FluidMCP
install_path	  Yes (auto)	    Path where server is installed or cloned

Note:
port and install_path are never expected to be provided by the user.
They are injected during resolution.

### Field Types and Validation Rules

# Structural Validation
    mcpServers must exist
    mcpServers must be an object
    Server names must be strings
    Invalid JSON or missing structure results in immediate failure

Validation is performed before resolution begins.

# Package String Validation

Example:

"filesystem": "@modelcontextprotocol/server-filesystem"

Rules:
    - Must be a valid package identifier
    - Must be resolvable from the package registry
    - Must provide valid metadata after installation

Failure cases:
    - Package not found
    - Missing or invalid metadata.json
    - Registry lookup failure

# Direct Configuration Validation

Example:

"filesystem": {
  "command": "npx",
  "args": [
    "-y",
    "@modelcontextprotocol/server-filesystem",
    "/tmp/test-directory"
  ],
  "env": {}
}

Rules:
    - command is required
    - args must be an array (defaults to empty if missing)
    - env must be an object if provided

Resolution behavior:
    - FluidMCP creates a temporary directory
    - A metadata.json file is generated automatically
    - The server is treated like a packaged server internally

# GitHub Repository Validation

Example:

"myServer": {
  "github_repo": "owner/repo",
  "branch": "main"
}

Rules:
    - github_repo is required
    - A GitHub access token must be available
    - Repository must be clonable
    - Startup metadata must be extractable or creatable

Resolution behavior:
    - Repository is cloned locally
    - If command is provided, it is used directly
    - Otherwise, FluidMCP attempts to extract startup information from:
        * Existing metadata.json, or
        * README files

Failure cases:
  - Missing GitHub token
  - Clone failure
  - No startup instructions found

### Supported Configuration Formats (Examples)
1. Package String Configuration
{
  "mcpServers": {
    "filesystem": "@modelcontextprotocol/server-filesystem"
  }
}

FluidMCP will:
  - Install the package
  - Read its metadata
  - Expand it into a runtime server configuration
  - Package strings are expanded during preprocessing before validation.
Note: This format is supported by FluidMCP but is not shown in the current sample files.

2. Direct Configuration
Source: `sample-config.json`, `sample-config-with-api-keys.json`

{ 
  "mcpServers": { 
    "filesystem": { 
      "command": "npx", 
      "args": [ "-y", "@modelcontextprotocol/server-filesystem", "/tmp/test-directory" ], 
      "env": {} 
    } 
  } 
}

Example with environment variables:

{ 
  "mcpServers": { 
    "google-maps": { 
      "command": "npx", 
      "args": [ "-y", "@google-maps/mcp-server" ], 
      "env": { "GOOGLE_MAPS_API_KEY": "your-api-key-here" } 
    } 
  } 
}

FluidMCP will:
  - Generate a temporary metadata.json
  - Assign a port
  - Run the server like any other MCP server

3. GitHub Repository Configuration (Automatic Metadata Extraction)
Source: `sample-github-config.json`

{ 
  "mcpServers": { 
    "fastmcp-quickstart": { 
      "github_repo": "modelcontextprotocol/python-sdk", 
      "github_token": "your-github-token-here", 
      "branch": "main", 
      "env": {} 
    } 
  } 
}

FluidMCP will:
  - Clone the repository
  - If metadata.json exists, it is used directly
  - Otherwise, FluidMCP searches for a README file and attempts to infer startup commands

4. GitHub Repository Configuration (Explicit Command)
Source: `sample-github-with-command.json`

{ 
  "mcpServers": { 
    "python-quickstart-explicit": { 
      "github_repo": "modelcontextprotocol/python-sdk", 
      "branch": "main", 
      "command": "uv", 
      "args": [ "run", "examples/snippets/servers/fastmcp_quickstart.py" ], 
      "env": {} 
    } 
  } 
}

When command and args are explicitly provided:
  - README parsing is skipped
  - metadata.json is generated directly from the provided command


### Common Mistakes and How to Avoid Them

WRONG: Mixing configuration formats incorrectly
"server": {
  "command": "node",
  "github_repo": "owner/repo"
}
    CORRECT: Use one format per server entry.


WRONG: Missing GitHub token
GitHub-based servers require authentication.
CORRECT: Set one of:
    - github_token in config
    - FMCP_GITHUB_TOKEN
    - GITHUB_TOKEN


WRONG: Assuming port is user-defined
Ports are auto-assigned.
    CORRECT: Let FluidMCP manage ports.


WRONG: Invalid package strings
Unresolvable package names cause preprocessing failures.
    CORRECT: Verify package identifiers before use.


WRONG: Assuming README parsing is guaranteed
README extraction is a fallback, not a guarantee.
CORRECT: Prefer repositories with existing metadata.json or provide command explicitly.


### Summary
    - metadata.json is a resolved runtime contract, not just user input.
    - Multiple configuration formats are supported.
    - All inputs normalize into a single executable structure.
    - Understanding the resolution pipeline is key to correct usage.