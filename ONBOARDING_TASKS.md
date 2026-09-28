# Onboarding Tasks for New Contributors

Welcome to FluidMCP! This document contains curated tasks designed to help you understand the codebase while making meaningful contributions. Tasks are organized by difficulty and area.

## How to Use This Guide

1. **Pick a task** that matches your interest and skill level
2. **Read the relevant code** mentioned in the task description
3. **Ask questions** if you need clarification
4. **Submit a PR** when ready - we're here to help!

Each task includes:
- **Difficulty**: Easy, Medium, or Complex
- **Area**: What part of the codebase you'll work with
- **Learning Outcome**: What you'll understand after completing it

---

## 📚 Documentation Tasks (Great First Tasks!)

### Task 1: Document metadata.json Schema
**Difficulty**: Easy
**Area**: Documentation
**Files to Review**: `examples/sample-metadata.json`, `fluidai_mcp/services/github_utils.py:118-146`

Create a comprehensive `docs/metadata-schema.md` that documents:
- All fields in metadata.json (required vs optional)
- Field types and validation rules
- Examples for each configuration format (direct config, GitHub repo, package string)
- Common mistakes and how to avoid them

**Learning Outcome**: Understand the three configuration formats and how FluidMCP processes them.

---

### Task 2: Add Docstrings to package_installer.py
**Difficulty**: Easy
**Area**: Code Documentation
**File**: `fluidai_mcp/services/package_installer.py`

Add comprehensive docstrings to all functions:
- `parse_package_string()` - explain the regex pattern and valid formats
- `install_package()` - document the installation flow
- `make_registry_request()` - explain registry interaction
- Follow Google or NumPy docstring style

**Learning Outcome**: Understand package installation flow and registry communication.

---

### Task 3: Create Troubleshooting Guide
**Difficulty**: Easy
**Area**: Documentation
**Files to Review**: Error handling patterns across `cli.py`, `config_resolver.py`

Create `docs/TROUBLESHOOTING.md` with:
- Common error messages and their solutions
- How to debug server startup failures
- Port conflict resolution
- GitHub authentication issues
- Missing dependencies (npm, python, node, uv)

**Learning Outcome**: Understand common failure modes and error handling patterns.

---

### Task 4: Document Port Allocation Strategy
**Difficulty**: Easy
**Area**: Documentation
**Files to Review**: `fluidai_mcp/services/network_utils.py`, `package_launcher.py:283-291`

Document in `docs/ARCHITECTURE.md`:
- How ports are allocated (8090 for single, 8099 for all)
- Port conflict detection and resolution
- Environment variables for port configuration
- Port range searching logic (8100-9000)

**Learning Outcome**: Understand network configuration and multi-server orchestration.

---

## 🧪 Testing Tasks (Learn by Testing!)

### Task 5: Write Tests for parse_package_string()
**Difficulty**: Easy
**Area**: Unit Testing
**File**: `fluidai_mcp/services/package_installer.py:18-35`

Create `tests/test_package_installer.py` with tests for:
- Valid package strings: `Author/Package@1.0.0`, `Author/Package@latest`
- Invalid formats: missing author, missing version, invalid characters
- Edge cases: special characters, very long names

**Learning Outcome**: Understand package string format and validation using pytest.

---

### Task 6: Write Tests for network_utils.py
**Difficulty**: Easy
**Area**: Unit Testing
**File**: `fluidai_mcp/services/network_utils.py`

Create `tests/test_network_utils.py` testing:
- `find_available_port()` returns a valid port number
- `is_port_in_use()` correctly detects occupied ports
- Port range validation (1-65535)

**Learning Outcome**: Understand port management and socket programming basics.

---

### Task 7: Add Validation Tests to test_github_utils.py
**Difficulty**: Medium
**Area**: Unit Testing
**File**: `tests/test_github_utils.py`

Expand existing tests to cover:
- Invalid GitHub URLs (malformed, non-existent repos)
- Invalid GitHub token formats
- Missing branch handling
- Edge cases in `normalize_github_repo()`

**Learning Outcome**: Understand GitHub integration and mocking external services.

---

### Task 8: Write Tests for env_manager.py
**Difficulty**: Medium
**Area**: Unit Testing
**File**: `fluidai_mcp/services/env_manager.py`

Create `tests/test_env_manager.py` with tests for:
- `load_env_file()` and `save_env_file()`
- `update_env_from_config()` merges environment variables correctly
- `write_keys_during_install()` handles existing .env files
- Mock interactive input for testing `edit_env_variables()`

**Learning Outcome**: Understand environment variable management and file I/O.

---

## 🛠️ Small Feature Additions

### Task 9: Add `--version` Flag to CLI
**Difficulty**: Easy
**Area**: CLI Enhancement
**Files**: `fluidai_mcp/cli.py`, `setup.py`

Add version flag that displays:
- FluidMCP version from setup.py
- Python version
- Installation path

**Learning Outcome**: Understand CLI argument parsing with argparse and package metadata.

---

### Task 10: Implement `fluidmcp validate` Command
**Difficulty**: Medium
**Area**: CLI Enhancement, Validation
**Files**: `cli.py`, `config_resolver.py`

Add new command: `fluidmcp validate config.json --file`
- Validates configuration without running servers
- Checks command availability in PATH
- Validates GitHub tokens (if provided)
- Reports issues with helpful error messages
- Exit code 0 for valid, 1 for invalid

**Learning Outcome**: Understand configuration validation and command detection.

---

### Task 11: Add `fluidmcp uninstall` Command
**Difficulty**: Medium
**Area**: CLI Enhancement
**Files**: `cli.py`, package management in `services/`

Implement package uninstallation:
- `fluidmcp uninstall Author/Package@version`
- Removes package directory from `.fmcp-packages/`
- Removes `.env` file
- Confirms before deletion (or add `--yes` flag)
- Lists affected files before removal

**Learning Outcome**: Understand package structure and safe file deletion.

---

### Task 12: Add `--verbose` Flag for Debugging
**Difficulty**: Medium
**Area**: CLI Enhancement, Logging
**Files**: `cli.py`, all service files

Add global `--verbose` flag:
- Configure loguru logger level based on flag
- Replace print statements with logger calls
- Show detailed information during operations
- Display command execution details

**Learning Outcome**: Understand logging configuration and consistent logging patterns.

---

### Task 13: Implement `fluidmcp status` Command
**Difficulty**: Medium
**Area**: CLI Enhancement
**Files**: `cli.py`, `package_launcher.py`

Add command to check running servers:
- List all running FluidMCP processes
- Show port numbers and PIDs
- Check if ports 8090/8099 are in use
- Display uptime (if trackable)
- Color-coded status (running/stopped)

**Learning Outcome**: Understand process management and system inspection.

---

## 🔍 Validation & Error Handling

### Task 14: Create Validators Module
**Difficulty**: Medium
**Area**: Validation
**New File**: `fluidai_mcp/services/validators.py`

Create reusable validation functions:
- `validate_package_string(s: str) -> bool`
- `validate_port_number(port: int) -> bool`
- `validate_github_token(token: str) -> bool`
- `validate_server_config(config: dict) -> list[str]` (returns errors)
- `validate_env_dict(env: dict) -> bool`

Add tests in `tests/test_validators.py`

**Learning Outcome**: Understand validation patterns and type checking.

---

### Task 15: Improve GitHub Clone Error Messages
**Difficulty**: Easy
**Area**: Error Handling
**File**: `fluidai_mcp/services/github_utils.py:55-78`

Enhance `clone_github_repo()` error messages:
- Detect authentication failures vs network failures
- Detect non-existent repository vs permission denied
- Provide actionable suggestions (check token, verify repo name)
- Include GitHub URL in error message

**Learning Outcome**: Understand git operations and error message design.

---

### Task 16: Add Input Validation to CLI Commands
**Difficulty**: Medium
**Area**: Validation, CLI
**File**: `fluidai_mcp/cli.py`

Add validation before processing:
- Validate package string format in `install_command()`
- Check file existence in `run_command()` before processing
- Validate S3 URLs in S3 mode
- Provide helpful error messages for invalid inputs

**Learning Outcome**: Understand input validation and fail-fast principles.

---

### Task 17: Fix Bare Except Blocks
**Difficulty**: Easy
**Area**: Code Quality
**File**: `fluidai_mcp/services/env_manager.py:40`

Replace bare `except:` with specific exception types:
- Identify what exceptions can actually occur
- Catch only expected exceptions
- Log unexpected errors appropriately
- Ensure cleanup in finally blocks where needed

**Learning Outcome**: Understand exception handling best practices.

---

## 🏗️ Architecture & Code Quality

### Task 18: Standardize Logger Usage
**Difficulty**: Medium
**Area**: Code Quality
**Files**: All service files

Replace `print()` with logger calls:
- Use `logger.info()` for normal output
- Use `logger.error()` for errors
- Use `logger.debug()` for verbose output
- Remove emoji from log messages (or make optional)
- Ensure consistent log formatting

**Learning Outcome**: Understand logging best practices and refactoring patterns.

---

### Task 19: Add JSON Schema Validation
**Difficulty**: Medium
**Area**: Validation
**Files**: `config_resolver.py`, create `schemas/metadata.schema.json`

Implement JSON Schema validation:
- Create JSON schema for metadata.json
- Add jsonschema package to requirements
- Validate configs against schema in `resolve_config()`
- Provide clear validation error messages

**Learning Outcome**: Understand JSON Schema and structured validation.

---

### Task 20: Create Example Configurations
**Difficulty**: Easy
**Area**: Documentation, Examples
**Directory**: `examples/`

Add new example files:
- `examples/github-private-repo.json` - private repo with token
- `examples/multi-server-dependencies.json` - servers with shared env vars
- `examples/secure-mode.json` - custom token authentication
- Add README section explaining each

**Learning Outcome**: Understand different use cases and configuration patterns.

---

## 🎯 Complex Features (For Experienced Contributors)

### Task 21: Implement Dependency Checking
**Difficulty**: Complex
**Area**: Feature Addition
**Files**: `cli.py`, create `services/dependency_checker.py`

Check for required dependencies before running:
- Detect if npm, node, python, uv are installed
- Check minimum version requirements
- Provide installation instructions if missing
- Add `--skip-dependency-check` flag

**Learning Outcome**: Understand system integration and subprocess management.

---

### Task 22: Add Dry-Run Mode
**Difficulty**: Complex
**Area**: Feature Addition
**Files**: `cli.py`, all run commands

Implement `--dry-run` flag:
- Show what would be executed without running it
- Display resolved configuration
- Show environment variables that would be set
- Show commands that would be executed
- Validate everything without side effects

**Learning Outcome**: Understand command execution flow and side effect management.

---

### Task 23: Implement Package Update Command
**Difficulty**: Complex
**Area**: Feature Addition
**Files**: `cli.py`, `package_installer.py`, create `services/package_updater.py`

Add `fluidmcp update` command:
- Check registry for newer versions
- Show current vs available versions
- Update specific package or all packages
- Preserve environment variables during update
- Handle breaking changes gracefully

**Learning Outcome**: Understand version management and package lifecycle.

---

## 🚀 Getting Started

1. **Set up your development environment**:
   ```bash
   git clone https://github.com/Fluid-AI/fluidmcp.git
   cd fluidmcp
   pip install -r requirements.txt
   pip install -e .
   ```

2. **Run existing tests**:
   ```bash
   pytest tests/ -v
   ```

3. **Pick a task** and create a branch:
   ```bash
   git checkout -b feature/task-name
   ```

4. **Make your changes** and test thoroughly

5. **Submit a pull request** with:
   - Clear description of what you changed
   - Reference to this task document
   - Tests for new functionality
   - Updated documentation if needed

## 📖 Resources

- **Main Documentation**: `README.md`, `CLAUDE.md`
- **Architecture**: `CODE_FLOW.md`
- **Contributing**: `CONTRIBUTING.md`
- **Examples**: `examples/README.md`
- **Tests**: `tests/` directory

## 💬 Questions?

- Open an issue with the `question` label
- Check existing issues and PRs for similar work
- Read through the test files to understand patterns

---

**Happy Contributing!** Each of these tasks will help you understand different aspects of FluidMCP while making the project better for everyone.
