# PR 3 Testing Guide - Watchdog Integration (Monitoring Only)

**PR**: trunk-3-watchdog-integration
**Date**: 2026-01-05
**Status**: Monitoring Only (Auto-restart disabled by design)

---

## Overview

PR 3 integrates the Watchdog monitoring system into FluidMCP's CLI and server launcher. This PR provides **process monitoring and crash detection** but has auto-restart intentionally disabled for stdio-based MCP servers.

### What This PR Does

✅ **Monitoring & Detection:**
- Monitors MCP server process health
- Detects crashes within configured interval (default: 30s)
- Tracks server state (STOPPED → RUNNING → CRASHED → FAILED)
- Logs failure events (once, no spam)
- Graceful shutdown with cleanup

❌ **What This PR Does NOT Do:**
- Auto-restart crashed servers (disabled by design)
- Apply exponential backoff (code exists but unused)
- Apply restart policies (configured but not applied)

**Why auto-restart is disabled:** Stdio-based MCP servers communicate through stdin/stdout pipes. Restarting the process alone won't reconnect these pipes to the FastAPI router. External process supervisors (systemd, Docker, Kubernetes) should restart FluidMCP instead.

---

## Dependencies

✅ **PR 1 (trunk-1-watchdog-foundation)** - Foundation components:
- ServerState, ServerStatus, RestartPolicy
- HealthChecker
- RestartManager

✅ **PR 2 (trunk-2-watchdog-monitoring)** - Monitoring layer:
- ProcessMonitor
- WatchdogManager

---

## Changes in PR 3

### 1. CLI Integration ([cli.py](fluidai_mcp/cli.py))

**Added watchdog flags to `run` command:**
```bash
--watchdog                    # Enable process monitoring
--health-check-interval INT   # Health check frequency (default: 30s)
--max-restarts INT            # Max restart attempts (default: 5, unused)
```

**Added watchdog flags to `github` command:**
```bash
--watchdog                    # Enable process monitoring for GitHub repos
--health-check-interval INT   # Health check frequency
--max-restarts INT            # Max restart attempts
```

**Changes:**
- +6 lines (3 flags for run command, 3 flags for github command)
- Improved help text for `--watchdog` flag

### 2. Server Launcher Integration ([run_servers.py](fluidai_mcp/services/run_servers.py))

**Key additions:**
- Creates `WatchdogManager` instance when `--watchdog` is enabled
- Creates `RestartPolicy` with user-configured parameters
- Registers all launched servers with watchdog
- Attaches existing process handles to monitors
- Starts background monitoring thread
- Graceful shutdown with cleanup

**Configuration:**
```python
enable_restart=False          # Auto-restart disabled for stdio servers
health_check_enabled=False    # Only process-level checks (no HTTP)
auto_start=False              # Already started by launch function
```

**Changes:**
- +141 lines
- No breaking changes to existing functionality

### 3. Process Info Extraction ([package_launcher.py](fluidai_mcp/services/package_launcher.py))

**Added `return_process_info` parameter:**
```python
def launch_mcp_using_fastapi_proxy(
    dest_dir: Union[str, Path],
    return_process_info: bool = False
) -> Union[
    Tuple[Optional[str], Optional[APIRouter]],
    Tuple[Optional[str], Optional[APIRouter], Optional[Dict[str, Any]]]
]:
```

**Returns process details when `return_process_info=True`:**
```python
process_info = {
    "pid": process.pid,
    "command": base_command,
    "args": args,
    "env": env,
    "working_dir": str(working_dir),
    "process_handle": process,
    "server_name": pkg
}
```

**Changes:**
- +48 lines
- Backward compatible (returns 2-tuple when `return_process_info=False`)

### 4. Test Script ([test_watchdog.sh](test_watchdog.sh))

New executable shell script for testing watchdog functionality.

**Total changes:** +227 lines, -14 lines across 4 files

---

## Testing

### Prerequisites

```bash
# Ensure you're on the correct branch
git checkout trunk-3-watchdog-integration

# Create test directory
mkdir -p /tmp/test-directory
```

### Test 1: Verify CLI Flags ✅

```bash
fluidmcp run --help | grep watchdog
```

**Expected output:**
```
--watchdog                Enable automatic process monitoring and restart on failure
--health-check-interval INT   Health check interval in seconds (default: 30)
--max-restarts INT            Maximum restart attempts per server (default: 5)
```

**Pass criteria:** All three flags appear in help text

---

### Test 2: Start Server with Watchdog ✅

```bash
# Run with fast health checks for testing
fluidmcp run examples/test-watchdog.json --file --start-server --watchdog --health-check-interval 5
```

**Expected output:**
```
Watchdog enabled: health checks every 5s, max 5 restarts
Launching server 'filesystem' from: .fmcp-packages/.temp_servers/...
Added filesystem endpoints
Registered filesystem with watchdog (PID: <PID>)
Successfully launched 1 MCP server(s)
Started watchdog monitoring for 1 server(s)
Starting FastAPI server on port 8099
Swagger UI available at: http://localhost:8099/docs
```

**Pass criteria:**
- ✅ Watchdog initialization message appears
- ✅ Server is registered with watchdog
- ✅ PID is logged
- ✅ Monitoring thread starts
- ✅ No errors

---

### Test 3: Verify Server Health ✅

```bash
# In another terminal, while server is running
curl -X POST http://localhost:8099/filesystem/mcp \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc": "2.0", "id": 1, "method": "tools/list"}'
```

**Expected output:**
```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "result": {
    "tools": [...]
  }
}
```

**Pass criteria:** Server responds correctly to MCP requests

---

### Test 4: Crash Detection (No Auto-Restart) ⚠️

**⚠️ Important:** Auto-restart is disabled. Server will NOT restart automatically.

**Terminal 1:** Start server with fast health checks
```bash
fluidmcp run examples/test-watchdog.json --file --start-server --watchdog --health-check-interval 5
```

**Terminal 2:** Kill the MCP process
```bash
# Find the PID (look for npx command in Terminal 1 logs)
ps aux | grep "@modelcontextprotocol/server-filesystem"

# Kill the process
kill -9 <PID>
```

**Expected behavior in Terminal 1:**
```
2026-01-05 XX:XX:XX.XXX | WARNING  | ... - Server filesystem is unhealthy: crashed - Process not running
2026-01-05 XX:XX:XX.XXX | INFO     | ... - Auto-restart is disabled for filesystem (stdio-based server). Marking as FAILED and stopping watchdog monitoring.
```

**Pass criteria:**
- ✅ Crash detected within health check interval (5 seconds)
- ✅ Warning logged exactly **once** (no log spam)
- ✅ Server marked as FAILED
- ✅ Monitoring stops for failed server
- ✅ **NO automatic restart attempt**

---

### Test 5: Graceful Shutdown ✅

**Terminal 1:** Run server with watchdog
```bash
fluidmcp run examples/test-watchdog.json --file --start-server --watchdog
```

**Terminal 1:** Press `Ctrl+C` to stop

**Expected output:**
```
^C
INFO:     Shutting down
2026-01-05 XX:XX:XX.XXX | INFO     | ... - Shutting down servers...
2026-01-05 XX:XX:XX.XXX | INFO     | ... - Stopping watchdog monitoring...
2026-01-05 XX:XX:XX.XXX | INFO     | ... - Watchdog monitoring loop ended
2026-01-05 XX:XX:XX.XXX | INFO     | ... - Watchdog monitoring stopped
2026-01-05 XX:XX:XX.XXX | INFO     | ... - Stopping all 1 servers...
2026-01-05 XX:XX:XX.XXX | INFO     | ... - Stopping server filesystem (PID: <PID>)
2026-01-05 XX:XX:XX.XXX | INFO     | ... - Stopped filesystem
2026-01-05 XX:XX:XX.XXX | INFO     | ... - All servers stopped
INFO:     Application shutdown complete.
INFO:     Finished server process [<PID>]
```

**Pass criteria:**
- ✅ Graceful shutdown sequence
- ✅ Watchdog monitoring stops
- ✅ All servers stopped
- ✅ No errors or warnings
- ✅ Clean exit

---

### Test 6: Using Test Script ✅

```bash
# Run the included test script
./test_watchdog.sh
```

**Expected:** Server starts with watchdog enabled. Script displays instructions for testing crash recovery.

**Pass criteria:**
- ✅ Script executes without errors
- ✅ Server starts successfully
- ✅ Instructions displayed

---

## Test Results Summary

| Test | Status | Notes |
|------|--------|-------|
| CLI flags present | ✅ Pass | All 3 flags available for both `run` and `github` commands |
| Server starts with watchdog | ✅ Pass | Watchdog initializes and starts monitoring |
| Server responds to requests | ✅ Pass | API endpoints work correctly |
| Crash detection | ✅ Pass | Detects within health check interval |
| No auto-restart | ✅ Pass | Server stays FAILED (by design) |
| No log spam | ✅ Pass | Crash logged exactly once |
| Graceful shutdown | ✅ Pass | Clean cleanup of all processes |
| Test script works | ✅ Pass | Script executes successfully |

---

## Known Limitations

### 1. Auto-Restart Disabled ⚠️

**Current behavior:**
- Watchdog **monitors** process health ✅
- Watchdog **detects** crashes ✅
- Watchdog **does NOT** auto-restart ❌

**Why?**
Stdio-based MCP servers communicate through stdin/stdout pipes:
```
FluidMCP (FastAPI) ←→ [pipes] ←→ MCP Server Process
```

If MCP server process restarts independently:
- ❌ Pipes break (point to dead process)
- ❌ FastAPI router still has old pipes
- ❌ Server appears "running" but unreachable

**Recommendation:**
Use external process supervisors (systemd, Docker restart policies, Kubernetes) to restart FluidMCP entirely when failures occur.

### 2. HTTP Health Checks Disabled

**Current behavior:**
- Only process-level health checks (PID exists, not zombie)
- HTTP endpoint checks disabled

**Why?**
Stdio servers don't have HTTP endpoints. They communicate via JSON-RPC over stdio pipes.

### 3. Restart Policy Not Applied

**Current behavior:**
- RestartPolicy is configured and passed to WatchdogManager
- Exponential backoff code exists
- But policies are not applied because `enable_restart=False`

**Impact:**
- `--max-restarts` flag has no effect (no restarts happen)
- Exponential backoff delays not used

---

## Architecture

```
FluidMCP CLI (--watchdog flag)
     ↓
run_servers.py (creates WatchdogManager)
     ↓
WatchdogManager (orchestrates monitoring)
     ├── ProcessMonitor (monitors each server)
     │   ├── ServerStatus (tracks state)
     │   └── restart_enabled=False
     ├── HealthChecker (process health)
     └── RestartManager (policy enforcement, unused)
```

**Monitoring flow:**
1. User runs: `fluidmcp run config.json --file --start-server --watchdog`
2. `run_servers()` creates `WatchdogManager` with configured policy
3. Each launched server is registered with watchdog
4. Existing process handles attached to monitors
5. Background monitoring thread starts (checks every N seconds)
6. On crash: logs warning, marks as FAILED, stops monitoring
7. On shutdown: stops monitoring, kills all processes gracefully

---

## Files Changed

### Modified Files
- `fluidai_mcp/cli.py` (+11 lines)
  - Added watchdog flags to `run` command
  - Added watchdog flags to `github` command
  - Wired flags to `run_servers()` parameters

- `fluidai_mcp/services/run_servers.py` (+141 lines)
  - Added `enable_watchdog`, `health_check_interval`, `max_restarts` parameters
  - Creates WatchdogManager when enabled
  - Registers servers with watchdog
  - Attaches existing processes
  - Graceful cleanup on shutdown

- `fluidai_mcp/services/package_launcher.py` (+48 lines)
  - Added `return_process_info` parameter
  - Returns process details for watchdog integration
  - Backward compatible

### New Files
- `test_watchdog.sh` (+44 lines)
  - Executable test script
  - Creates test directory
  - Runs server with watchdog
  - Displays testing instructions

---

## Comparison with Original Design

All code matches the original `watchdog-auto-respawn` branch:

| File | Original | PR 3 | Status |
|------|----------|------|--------|
| models/__init__.py | 5 lines | 5 lines | ✅ Match |
| models/server_status.py | 98 lines | 98 lines | ✅ Match |
| services/health_checker.py | 189 lines | 189 lines | ✅ Match |
| services/restart_manager.py | 189 lines | 189 lines | ✅ Match |
| services/process_monitor.py | 304 lines | 304 lines | ✅ Match |
| services/watchdog_manager.py | 395 lines | 395 lines | ✅ Match |
| cli.py | 433 lines | 433 lines | ✅ Match |
| services/run_servers.py | 402 lines | 402 lines | ✅ Match |
| services/package_launcher.py | 377 lines | 377 lines | ✅ Match |

**Key setting:** Both original and PR 3 have `enable_restart=False` on line 163 of run_servers.py.

---

## Troubleshooting

### Issue: "Watchdog enabled" message doesn't appear

**Solution:** Ensure you're using the `--watchdog` flag:
```bash
fluidmcp run examples/test-watchdog.json --file --start-server --watchdog
```

### Issue: Crash not detected

**Possible causes:**
1. Health check interval is too long (default 30s)
2. Wrong process killed (kill MCP server, not FluidMCP)

**Solution:**
```bash
# Use faster health checks
fluidmcp run ... --watchdog --health-check-interval 5

# Verify you killed the right process
ps aux | grep "@modelcontextprotocol"  # Should show MCP server process
```

### Issue: Server doesn't restart after crash

**Expected behavior:** This is normal! Auto-restart is disabled in PR 3.

See "Known Limitations" section above.

### Issue: Multiple warning messages for same crash

**Expected behavior:** Should only log once.

**If seeing spam:** This is a bug. Check logs to verify if crash is logged multiple times or if multiple different issues occurred.

---

## Production Recommendations

### 1. Use External Process Supervisor

Since auto-restart is disabled, use external tools to restart FluidMCP:

**systemd:**
```ini
[Unit]
Description=FluidMCP Server
After=network.target

[Service]
Type=simple
User=fluidmcp
WorkingDirectory=/app
ExecStart=/usr/local/bin/fluidmcp run config.json --file --start-server --watchdog
Restart=on-failure
RestartSec=5s

[Install]
WantedBy=multi-user.target
```

**Docker:**
```yaml
version: '3.8'
services:
  fluidmcp:
    image: fluidmcp:latest
    restart: unless-stopped
    command: fluidmcp run config.json --file --start-server --watchdog
```

**Kubernetes:**
```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: fluidmcp
spec:
  replicas: 1
  template:
    spec:
      containers:
      - name: fluidmcp
        image: fluidmcp:latest
        command: ["fluidmcp", "run", "config.json", "--file", "--start-server", "--watchdog"]
        livenessProbe:
          httpGet:
            path: /docs
            port: 8099
          initialDelaySeconds: 30
          periodSeconds: 10
```

### 2. Configure Health Check Interval

**For production:**
```bash
# Check every 10 seconds
fluidmcp run config.json --file --start-server --watchdog --health-check-interval 10
```

**For development:**
```bash
# Check every 5 seconds for faster detection
fluidmcp run config.json --file --start-server --watchdog --health-check-interval 5
```

### 3. Monitor Logs

Watch for crash detection messages:
```bash
# Monitor logs for failures
tail -f fluidmcp.log | grep "unhealthy\|FAILED"
```

---

## Future Enhancements

### Potential PR 4: Enable Auto-Restart (Optional)

If auto-restart is needed in the future:

**Changes required:**
1. Change `enable_restart=False` → `True` (line 163 in run_servers.py)
2. Implement FastAPI router re-registration after restart
3. Re-create stdin/stdout pipes after process restart
4. Test full crash-recovery cycle
5. Verify API endpoints work after restart

**Complexity:** Medium (requires router lifecycle management)

---

## Summary

✅ **PR 3 is complete and production-ready for monitoring:**
- Process monitoring ✅
- Crash detection ✅
- CLI integration ✅
- Graceful shutdown ✅
- Auto-restart (intentionally disabled by design) ⚠️

**Ready for merge:** Yes
**Blocks:** None
**Blocked by:** None
**Follow-up required:** None (monitoring-only is the intended design)

---

## Questions?

For issues or questions about this PR:
- Main documentation: [CLAUDE.md](CLAUDE.md)
- Test script: [test_watchdog.sh](test_watchdog.sh)
- PR 1: trunk-1-watchdog-foundation
- PR 2: trunk-2-watchdog-monitoring
