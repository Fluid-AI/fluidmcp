# Watchdog / Auto-Respawn Feature

## Overview

The watchdog monitors MCP server processes. Currently supports stdio-based MCP servers with crash detection and alerting. Auto-restart capability is built-in for future HTTP-based servers.

## Usage

### Enable Watchdog

```bash
# Basic (30s health checks, 5 max restarts)
fluidmcp run config.json --file --start-server --watchdog

# Custom interval
fluidmcp run config.json --file --start-server --watchdog --health-check-interval 60

# Custom max restarts
fluidmcp run config.json --file --start-server --watchdog --max-restarts 10
```

### CLI Options

| Flag | Default | Description |
|------|---------|-------------|
| `--watchdog` | Disabled | Enable watchdog monitoring |
| `--health-check-interval` | 30 | Health check interval (seconds) |
| `--max-restarts` | 5 | Max restart attempts per server |

## Architecture

```
FastAPI Router
 └── stdio MCP servers (filesystem, memory, etc.)
      └── Watchdog monitors processes
           ├── Detects crashes
           ├── Logs failures
           └── Marks as FAILED (no auto-restart for stdio)
```

**Note**: Auto-restart is disabled for stdio-based MCP servers because they communicate through stdin/stdout pipes managed by the FastAPI router. Restarting the process alone won't reconnect the pipes.

### Server Lifecycle States

- **STOPPED**: Not running
- **STARTING**: Being started
- **RUNNING**: Process alive
- **HEALTHY**: Running + responding
- **UNHEALTHY**: Running but not responding
- **CRASHED**: Process died
- **RESTARTING**: Being restarted
- **FAILED**: Max restarts reached or restart disabled

### Restart Policy (Default)

- **Max restarts**: 5 attempts
- **Initial delay**: 2 seconds
- **Backoff**: Exponential (2s → 4s → 8s → 16s → 32s → 60s)
- **Max delay**: 60 seconds
- **Restart window**: 300 seconds (5 minutes)

## Testing

### Test 1: Basic Startup

```bash
# Create test directory
mkdir -p /tmp/test-directory

# Start with watchdog
fluidmcp run examples/test-watchdog.json --file --start-server --watchdog --health-check-interval 10
```

**Expected**: Server starts, watchdog monitoring enabled.

### Test 2: Crash Detection (Stdio Server)

```bash
# Terminal 1: Server running from Test 1

# Terminal 2: Kill the MCP process
ps aux | grep "mcp-server-filesystem" | grep -v grep | awk '{print $2}' | head -1 | xargs kill -9

# Terminal 1: Watch logs
```

**Expected Output** (one time only, no repetition):
```
WARNING - Server filesystem is unhealthy: crashed - Process not running
INFO - Auto-restart is disabled for filesystem (stdio-based server). Marking as FAILED and stopping watchdog monitoring.
```

**Expected Behavior**:
- ✅ Crash detected within 10 seconds
- ✅ Logged once
- ✅ Server marked as FAILED
- ✅ No auto-restart (stdio server)
- ✅ No log spam

### Test 3: Graceful Shutdown

```bash
# Press Ctrl+C in Terminal 1
```

**Expected**:
- ✅ Watchdog stops monitoring
- ✅ All processes cleaned up
- ✅ Clean exit

## Implementation Details

### Components

1. **ServerStatus & ServerState** (`fluidai_mcp/models/server_status.py`)
   - Data models for tracking server state
   - Restart policy configuration

2. **HealthChecker** (`fluidai_mcp/services/health_checker.py`)
   - Process-level health checks (psutil)
   - HTTP endpoint health checks
   - JSON-RPC ping support

3. **RestartManager** (`fluidai_mcp/services/restart_manager.py`)
   - Manages restart attempts and history
   - Implements exponential backoff
   - Enforces restart limits

4. **ProcessMonitor** (`fluidai_mcp/services/process_monitor.py`)
   - Monitors individual server processes
   - Performs health checks
   - Manages process lifecycle

5. **WatchdogManager** (`fluidai_mcp/services/watchdog_manager.py`)
   - Coordinates all monitoring activities
   - Manages multiple ProcessMonitors
   - Runs background monitoring loop

### Key Changes

**Modified Files**:
- `fluidai_mcp/cli.py` - Added CLI flags
- `fluidai_mcp/services/run_servers.py` - Integrated watchdog
- `fluidai_mcp/services/package_launcher.py` - Returns process info

**New Files**:
- `fluidai_mcp/models/__init__.py`
- `fluidai_mcp/models/server_status.py`
- `fluidai_mcp/services/health_checker.py`
- `fluidai_mcp/services/process_monitor.py`
- `fluidai_mcp/services/restart_manager.py`
- `fluidai_mcp/services/watchdog_manager.py`

## Current Behavior

### Stdio-based MCP Servers

All current MCP servers (filesystem, memory, etc.) use stdio communication:

- ✅ **Monitored**: Yes - Watchdog tracks process health
- ❌ **Auto-restart**: No (requires FastAPI router integration)
- ✅ **Crash detection**: Yes (logged once, no spam)
- ✅ **Marked as FAILED**: Yes (stops monitoring after detection)
- ✅ **Clean logs**: No repeated warnings

**When a stdio MCP server crashes**:
1. Watchdog detects crash within health-check interval
2. Logs: "Server X is unhealthy: crashed"
3. Logs: "Auto-restart is disabled... Marking as FAILED"
4. Server marked as FAILED
5. Monitoring stops for that server (no log spam)
6. **User action required**: Restart FluidMCP to restore service

## Troubleshooting

### Issue: Watchdog not starting

**Solution**: Check that `--watchdog` flag is present and psutil is installed:
```bash
pip install psutil
```

### Issue: Logs repeating after crash

**Solution**: Ensure you're running the latest code with FAILED state check.

### Issue: Server not restarting

**This is expected behavior**. Current MCP servers are stdio-based and cannot be auto-restarted. When a crash is detected:
- Server is marked as FAILED
- Monitoring stops
- You must restart FluidMCP to restore service

## Future Enhancements

When HTTP-based servers are added:
- [ ] Auto-restart with exponential backoff (infrastructure ready)
- [ ] Per-server restart policies
- [ ] HTTP endpoint health checks
- [ ] Webhook notifications for failures
- [ ] Web Dashboard integration

## Quick Reference

```bash
# Start with watchdog
fluidmcp run config.json --file --start-server --watchdog

# Custom settings
fluidmcp run config.json --file --start-server \
  --watchdog \
  --health-check-interval 60 \
  --max-restarts 10

# Test crash detection
ps aux | grep "mcp-server" | grep -v grep | awk '{print $2}' | xargs kill -9
```

---

**Branch**: `watchdog-auto-respawn`
**Date**: 2026-01-02
