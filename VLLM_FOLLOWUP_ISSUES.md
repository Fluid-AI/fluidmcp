# vLLM Error Recovery - Follow-up Issues to Fix

**Context**: Branch `feature/vllm-error-recovery` was merged to main and deleted. These issues were found AFTER the merge and need to be addressed in a follow-up PR.

**Date**: 2026-01-28
**Original Branch**: feature/vllm-error-recovery (merged and deleted)
**Follow-up Branch**: fix/vllm-error-recovery-issues (to be created)

---

## Issues Overview

**Total Issues**: 13
- **Critical**: 3 (path traversal, blocking I/O, backoff calculation)
- **High**: 4 (file leak, multiple restarts, cleanup, on-failure policy)
- **Medium**: 3 (documentation, deduplication)
- **Low**: 3 (edge cases, clarity)

---

## CRITICAL Issues (Must Fix)

### Issue #1: Path Traversal Vulnerability
**File**: `fluidmcp/cli/services/llm_launcher.py:122, 290`
**Severity**: 🔴 CRITICAL (Security)

**Problem**: `model_id` used directly in file paths without sanitization
```python
stderr_log_path = os.path.join(log_dir, f"llm_{self.model_id}_stderr.log")
```

**Attack**: `model_id="../../etc/passwd"` → writes outside logs directory

**Fix**:
```python
import re

def sanitize_model_id(model_id: str) -> str:
    """Sanitize model ID to prevent path traversal."""
    sanitized = re.sub(r'[^a-zA-Z0-9_-]', '_', model_id)
    sanitized = sanitized.replace('..', '_')
    if not sanitized:
        sanitized = 'unnamed_model'
    return sanitized

# Use in paths
safe_model_id = sanitize_model_id(self.model_id)
stderr_log_path = os.path.join(log_dir, f"llm_{safe_model_id}_stderr.log")
```

**Status**: ✅ Fixed in comprehensive review (but lost when branch deleted)

---

### Issue #2: Backoff Calculation Wrong
**File**: `fluidmcp/cli/services/llm_launcher.py:486-493`
**Severity**: 🔴 CRITICAL (Logic Bug)

**Problem**: `restart_count` incremented BEFORE delay calculation
```python
self.restart_count += 1  # Now restart_count = 1
delay = self.calculate_restart_delay()  # Uses restart_count=1, delay = 5 * 2^1 = 10s
```

**Result**: First restart waits 10s instead of documented 5s

**Expected**: 5s → 10s → 20s → 40s
**Actual**: 10s → 20s → 40s → 80s

**Fix Option 1** (Calculate before increment):
```python
# Calculate delay BEFORE incrementing counter
delay = self.calculate_restart_delay()
logger.info(f"Waiting {delay}s before restart...")
await asyncio.sleep(delay)

# Increment after delay
self.restart_count += 1
logger.info(f"Attempting to restart (attempt {self.restart_count}/{self.max_restarts})")
```

**Fix Option 2** (Use restart_count - 1 for exponent):
```python
def calculate_restart_delay(self) -> float:
    # Use (restart_count - 1) so first attempt uses exponent 0
    exponent = min(self.restart_count - 1, MAX_BACKOFF_EXPONENT)
    return self.restart_delay * (2 ** max(0, exponent))
```

**Status**: ❌ Not fixed yet (found by Copilot after merge)

---

### Issue #3: Blocking CUDA OOM Check in Management API
**File**: `fluidmcp/cli/api/management.py:1217, 1416`
**Severity**: 🔴 CRITICAL (Performance)

**Problem**: Two endpoints call sync `check_for_cuda_oom()` directly
```python
# Line 1217 - GET /api/llm/models/{model_id}
"has_cuda_oom": process.check_for_cuda_oom()  # BLOCKS event loop!

# Line 1416 - POST /api/llm/models/{model_id}/health-check
"has_cuda_oom": process.check_for_cuda_oom()  # BLOCKS event loop!
```

**Impact**: File I/O blocks FastAPI event loop under load

**Fix**:
```python
# Both locations need async wrapper
"has_cuda_oom": await asyncio.to_thread(process.check_for_cuda_oom)
```

**Status**: ❌ Not fixed (we only fixed the monitor loop, missed API endpoints)

---

## HIGH Priority Issues

### Issue #4: File Handle Leak
**File**: `fluidmcp/cli/services/llm_launcher.py:155-162`
**Severity**: ⚠️ HIGH (Resource Leak)

**Problem**: File handle not properly closed if exception occurs
```python
stderr_log = open(stderr_log_path, "a")
self.process = subprocess.Popen(...)  # Can raise exception
self._stderr_log = stderr_log  # Never reached if exception
```

**Fix**:
```python
stderr_log = None
try:
    stderr_log = open(stderr_log_path, "a")
    self.process = subprocess.Popen(...)
    self._stderr_log = stderr_log
    stderr_log = None  # Transfer ownership
finally:
    if stderr_log is not None:
        stderr_log.close()
```

**Status**: ✅ Fixed in comprehensive review (but lost when branch deleted)

---

### Issue #5: Multiple Restart Tasks Still Possible
**File**: `fluidmcp/cli/services/llm_launcher.py:606`
**Severity**: ⚠️ HIGH (Operational)

**Problem**: Monitor creates new restart task every 30s if `needs_restart()` stays True
```python
if process.needs_restart():
    asyncio.create_task(self._handle_restart(model_id, process))
    # Next check in 30s will create ANOTHER task if restart still in progress!
```

**Our Fix**: Added `_restart_in_progress` flag on LLMProcess ✅

**Copilot's Additional Suggestion**: Also track at monitor level
```python
# In __init__
self._restarts_in_progress = set()

# In monitor loop
if model_id not in self._restarts_in_progress:
    self._restarts_in_progress.add(model_id)

    async def _restart_wrapper():
        try:
            await self._handle_restart(model_id, process)
        finally:
            self._restarts_in_progress.discard(model_id)

    asyncio.create_task(_restart_wrapper())
```

**Status**: ⚠️ Partially fixed (we added flag, but Copilot wants double protection)

---

### Issue #6: on-failure Policy Too Broad
**File**: `fluidmcp/cli/services/llm_launcher.py:407-409`
**Severity**: ⚠️ HIGH (Logic Bug)

**Problem**: `on-failure` restarts on ANY stop, not just failures
```python
if not self.is_running():
    if self.restart_policy in ("on-failure", "always"):
        return True  # Restarts even if user manually stopped!
```

**Impact**: User stops model via API → monitor auto-restarts it

**Fix**: Check exit code
```python
if self.restart_policy == "always":
    return True

if self.restart_policy == "on-failure":
    if self.process and self.process.poll() is not None:
        returncode = self.process.poll()
        # Only restart on non-zero exit (failure)
        if returncode != 0:
            return True
```

**Status**: ❌ Not fixed yet

---

### Issue #7: Cleanup Doesn't Cancel Tasks
**File**: `fluidmcp/cli/services/run_servers.py:1138-1147`
**Severity**: ⚠️ HIGH (Resource Leak)

**Problem**: Setting `_running = False` doesn't cancel asyncio task
```python
_llm_health_monitor._running = False  # Just sets flag
_llm_health_monitor = None  # Drops reference, but task still running!
```

**Impact**: Background tasks (monitor + restart tasks) left running during shutdown

**Fix**: Properly await cancellation
```python
if _llm_health_monitor and _llm_health_monitor.is_running():
    logger.info("Stopping LLM health monitor...")
    try:
        # Use the async stop() method properly
        # This requires running in an async context or using run_coroutine_threadsafe
        loop = asyncio.get_event_loop()
        if loop.is_running():
            # Schedule stop on the running loop
            future = asyncio.run_coroutine_threadsafe(_llm_health_monitor.stop(), loop)
            future.result(timeout=5)  # Wait for completion
        else:
            # If no loop, just set flag (best effort)
            _llm_health_monitor._running = False
    except Exception as e:
        logger.warning(f"Error stopping health monitor: {e}")
    finally:
        _llm_health_monitor = None
```

**Status**: ❌ Not fixed yet

---

## MEDIUM Priority Issues

### Issue #8: Documentation Backoff Formula Unclear
**File**: `docs/VLLM_ERROR_RECOVERY.md:62-63`
**Severity**: 📊 MEDIUM (Documentation)

**Problem**: Formula doesn't clarify if attempt starts at 0 or 1
```markdown
- Actual delay uses exponential backoff: `delay * (2 ^ attempt)`
- Example: 5s, 10s, 20s, 40s, 80s, 160s
```

**Fix**:
```markdown
- Actual delay uses exponential backoff: `restart_delay * (2 ^ (attempt - 1))`
- Where `attempt` is the restart attempt number starting at 1
- Example with restart_delay=5:
  - Attempt 1 → 5s (5 * 2^0)
  - Attempt 2 → 10s (5 * 2^1)
  - Attempt 3 → 20s (5 * 2^2)
  - Attempt 4 → 40s (5 * 2^3)
```

**Status**: ❌ Not fixed yet

---

### Issue #9: URL Edge Case
**File**: `fluidmcp/cli/services/llm_launcher.py:254-261`
**Severity**: 📊 MEDIUM (Edge Case)

**Problem**: If `base_url="/v1"` exactly, normalization fails
```python
normalized = "/v1"
root = "" (after stripping "/v1")
# Fallback sets it back to "/v1" → wrong URLs
```

**Fix**:
```python
if not root_base_url:
    root_base_url = "http://localhost"
    logger.warning(f"base_url '{base_url}' resulted in empty root, defaulting to {root_base_url}")
```

**Status**: ✅ Fixed in comprehensive review (but lost when branch deleted)

---

### Issue #10: "always" Policy Documentation
**File**: `docs/VLLM_ERROR_RECOVERY.md:53`
**Severity**: 📊 MEDIUM (Documentation)

**Problem**: Docs say "planned for future" but it's already implemented
```markdown
- `"always"` - Restart whenever process stops (planned for future)
```

**Fix**:
```markdown
- `"always"` - Restart whenever process stops, regardless of exit reason
```

**Status**: ❌ Not fixed yet

---

## LOW Priority Issues

### Issue #11: max_restarts=0 Clarity
**File**: `fluidmcp/cli/services/llm_launcher.py:387`
**Severity**: ℹ️ LOW (Code Clarity)

**Problem**: Behavior correct but not obvious from code
```python
if self.restart_count >= self.max_restarts:  # 0 >= 0 = True
    return False
```

**Fix**: Add explicit check with comment
```python
if self.max_restarts == 0:
    logger.debug(f"max_restarts=0 means no restarts allowed")
    return False

if self.restart_count >= self.max_restarts:
    logger.warning(f"Reached max restarts ({self.max_restarts})")
    return False
```

**Status**: ✅ Fixed in comprehensive review (but lost when branch deleted)

---

## Summary Table

| # | Issue | Severity | Status | Source |
|---|-------|----------|--------|--------|
| 1 | Path Traversal | 🔴 CRITICAL | ✅ Fixed (lost) | Comprehensive Review |
| 2 | Backoff Calculation | 🔴 CRITICAL | ❌ Not Fixed | Copilot |
| 3 | Blocking CUDA OOM in API | 🔴 CRITICAL | ❌ Not Fixed | Copilot |
| 4 | File Handle Leak | ⚠️ HIGH | ✅ Fixed (lost) | Comprehensive Review |
| 5 | Multiple Restart Tasks | ⚠️ HIGH | ⚠️ Partial | Both |
| 6 | on-failure Too Broad | ⚠️ HIGH | ❌ Not Fixed | Copilot |
| 7 | Cleanup Task Leak | ⚠️ HIGH | ❌ Not Fixed | Copilot |
| 8 | Backoff Formula Docs | 📊 MEDIUM | ❌ Not Fixed | Copilot |
| 9 | URL Edge Case | 📊 MEDIUM | ✅ Fixed (lost) | Comprehensive Review |
| 10 | "always" Policy Docs | 📊 MEDIUM | ❌ Not Fixed | Copilot |
| 11 | max_restarts=0 Clarity | ℹ️ LOW | ✅ Fixed (lost) | Comprehensive Review |

---

## Next Steps

1. **Create new branch**: `fix/vllm-error-recovery-issues`
2. **Apply all fixes** from this document
3. **Add tests** for critical issues
4. **Create PR** with reference to this document
5. **Get review** and merge to main

---

## Files to Modify

- `fluidmcp/cli/services/llm_launcher.py` - 8 fixes
- `fluidmcp/cli/api/management.py` - 2 fixes
- `fluidmcp/cli/services/run_servers.py` - 1 fix
- `docs/VLLM_ERROR_RECOVERY.md` - 2 fixes

---

## Test Coverage Needed

- [ ] Test sanitize_model_id() with malicious inputs
- [ ] Test backoff timing (5s, 10s, 20s progression)
- [ ] Test no duplicate restarts during long restart
- [ ] Test on-failure doesn't restart manual stops
- [ ] Test cleanup cancels all tasks

---

**Generated**: 2026-01-28
**By**: Claude Code Review Session
**For**: Next PR to fix post-merge issues
