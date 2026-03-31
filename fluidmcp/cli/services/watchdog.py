"""
Event loop watchdog for detecting asyncio lag.

Runs a background task that periodically measures how long a short
asyncio.sleep takes in wall-clock time. A large delta indicates the
event loop is blocked or severely overloaded.
"""
import asyncio
import time
import os
from loguru import logger


def _get_env_float(name: str, default: float, min_value: float | None = None) -> float:
    """Safely parse a float env var, falling back to default on invalid values.

    Does NOT call logger — safe to use at module import time before loguru
    is configured. Invalid values are silently replaced with the default.
    """
    raw = os.getenv(name)
    if raw is None or raw == "":
        return default
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return default
    if min_value is not None and value < min_value:
        return default
    return value


# Thresholds configurable via env vars (seconds)
_WARN_THRESHOLD = _get_env_float("FMCP_LOOP_LAG_WARN_S", 0.5)
_ERROR_THRESHOLD = _get_env_float("FMCP_LOOP_LAG_ERROR_S", 2.0)
_CHECK_INTERVAL = _get_env_float("FMCP_LOOP_LAG_INTERVAL_S", 10.0, min_value=0.001)


class EventLoopWatchdog:
    """
    Detects event loop lag by measuring asyncio.sleep() wall-clock drift.

    A sleep of `_CHECK_INTERVAL` seconds that takes significantly longer
    indicates the event loop was blocked — usually by a slow synchronous
    call, a CPU-heavy coroutine, or resource contention.

    Usage::

        watchdog = EventLoopWatchdog()
        watchdog.start()
        # ... run server ...
        await watchdog.stop()
    """

    def __init__(self) -> None:
        self._task: asyncio.Task | None = None

    def start(self) -> None:
        """Schedule the watchdog loop as a background asyncio task."""
        if self._task is not None and not self._task.done():
            logger.warning("Event loop watchdog is already running — ignoring duplicate start()")
            return
        self._task = asyncio.create_task(self._loop(), name="event-loop-watchdog")
        logger.info(
            f"Event loop watchdog started "
            f"(warn>{_WARN_THRESHOLD}s, error>{_ERROR_THRESHOLD}s, interval={_CHECK_INTERVAL}s)"
        )

    async def stop(self) -> None:
        """Cancel the background watchdog task and wait for it to finish."""
        if self._task is None:
            return
        self._task.cancel()
        try:
            await self._task
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.warning(f"Event loop watchdog task exited with unexpected error: {e}")
        self._task = None
        logger.info("Event loop watchdog stopped")

    async def _loop(self) -> None:
        """Continuously measure event loop lag."""
        try:
            while True:
                before = time.monotonic()
                await asyncio.sleep(_CHECK_INTERVAL)
                lag = time.monotonic() - before - _CHECK_INTERVAL

                if lag >= _ERROR_THRESHOLD:
                    logger.error(
                        f"Event loop lag {lag:.2f}s exceeds error threshold "
                        f"({_ERROR_THRESHOLD}s) — event loop may be severely blocked"
                    )
                elif lag >= _WARN_THRESHOLD:
                    logger.warning(
                        f"Event loop lag {lag:.2f}s exceeds warn threshold "
                        f"({_WARN_THRESHOLD}s) — check for blocking calls"
                    )
        except asyncio.CancelledError:
            raise
