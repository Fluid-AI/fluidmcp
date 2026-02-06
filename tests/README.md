# FluidMCP Test Suite

This directory contains the FluidMCP test suite with various types of tests.

## Quick Start

### Run fast tests (default - recommended for development)
```bash
pytest
# or
pytest -v
```

**Default behavior**: Skips slow E2E tests automatically (completes in ~30 seconds)

### Run specific test types

```bash
# Fast API tests only
pytest tests/test_serve_api.py -v

# Slow E2E tests only (5-10 minutes)
pytest -m slow -v

# Run ALL tests (fast + slow)
pytest -m "" -v
```

## Test Organization

### Automated Tests (run with pytest)

**Fast Tests** (default, ~30 seconds total):
- `test_serve_api.py` - FastAPI endpoint tests (no actual servers)
- `test_*.py` - Other unit and integration tests

**Slow Tests** (opt-in with `-m slow`, 5-10 minutes):
- `test_serve_e2e.py` - End-to-end tests with actual MCP servers
  - Requires: MongoDB, Node.js/npx
  - Marked with `@pytest.mark.slow`

### Manual Tests (run as Python scripts)

Located in `tests/manual/`:
- `integration_test_multi_model.py` - Requires GPU, vLLM, running server
- `integration_test_streaming.py` - Requires running FluidMCP server
- `test_advanced_config.py` - Manual vLLM config validation

**Run manually:**
```bash
python tests/manual/test_advanced_config.py
```

## Prerequisites

### For fast tests:
- MongoDB (local or Atlas)
  ```bash
  docker run -d -p 27017:27017 --name mongodb-test mongo:latest
  ```

### For slow E2E tests:
- MongoDB
- Node.js and npx installed
- `@modelcontextprotocol/server-memory` package (installed via npx)

### For manual tests:
- Varies by test (see file headers for requirements)

## CI/CD Integration

```yaml
# Fast tests on every commit
- name: Run fast tests
  run: pytest -v

# Slow tests before merge or nightly
- name: Run slow E2E tests
  run: pytest -m slow -v
```

## Configuration

Test behavior is controlled by `pytest.ini`:
- Default: `-m "not slow"` (skips slow tests)
- Override with `-m slow` or `-m ""` to run slow tests

## Custom MongoDB URI

```bash
FMCP_TEST_MONGODB_URI="mongodb://localhost:27017" pytest -v
```

## Shared Fixtures

Common test fixtures are in `conftest.py`:
- MongoDB connection management
- FastAPI test app setup
- Polling utilities (`wait_for_server_status`, `wait_for_condition`)
