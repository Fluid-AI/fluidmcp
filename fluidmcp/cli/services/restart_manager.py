"""Restart policy management with exponential backoff."""

import time
from datetime import datetime, timedelta
from typing import Dict, Optional, Tuple
from loguru import logger

from ..models.server_status import RestartPolicy


class RestartManager:
    """Manages server restart policies and tracks restart attempts."""

    def __init__(self):
        """Initialize restart manager."""
        self._restart_history: Dict[str, list] = {}  # server_name -> list of restart timestamps
        self._backoff_state: Dict[str, int] = {}  # server_name -> current backoff level

    def can_restart(
        self,
        server_name: str,
        policy: RestartPolicy,
        current_restart_count: int
    ) -> Tuple[bool, Optional[str]]:
        """Check if a server can be restarted based on its policy.

        Args:
            server_name: Name of the server
            policy: Restart policy configuration
            current_restart_count: Current number of restarts

        Returns:
            Tuple of (can_restart, reason_if_not)
        """
        # Check if max restarts reached
        if current_restart_count >= policy.max_restarts:
            return False, f"Max restarts ({policy.max_restarts}) reached"

        # Check restart window if configured
        if policy.restart_window_seconds:
            now = datetime.now()
            window_start = now - timedelta(seconds=policy.restart_window_seconds)

            # Get restart history within window
            history = self._restart_history.get(server_name, [])
            recent_restarts = [
                ts for ts in history
                if ts > window_start
            ]

            # Check if too many restarts in window
            if len(recent_restarts) >= policy.max_restarts:
                return False, (
                    f"Too many restarts ({len(recent_restarts)}) "
                    f"in {policy.restart_window_seconds}s window"
                )

        return True, None

    def calculate_backoff_delay(
        self,
        server_name: str,
        policy: RestartPolicy,
        restart_count: int
    ) -> float:
        """Calculate backoff delay before next restart.

        Uses exponential backoff: initial_delay * (backoff_multiplier ^ restart_count)

        Args:
            server_name: Name of the server
            policy: Restart policy configuration
            restart_count: Number of restarts so far

        Returns:
            Delay in seconds
        """
        # Calculate exponential backoff with a conservative exponent cap to avoid excessively large delays
        exponent = min(restart_count, 10)  # Cap exponent to prevent excessively large intermediate values
        delay = policy.initial_delay_seconds * (policy.backoff_multiplier ** exponent)
        delay = min(delay, policy.max_delay_seconds)

        logger.debug(
            f"Calculated backoff delay for {server_name}: "
            f"{delay:.2f}s (restart #{restart_count})"
        )

        return delay

    def record_restart(self, server_name: str) -> None:
        """Record a restart attempt.

        Args:
            server_name: Name of the server
        """
        now = datetime.now()

        if server_name not in self._restart_history:
            self._restart_history[server_name] = []

        self._restart_history[server_name].append(now)

        logger.debug(f"Recorded restart for {server_name} at {now}")

    def reset_restart_history(self, server_name: str) -> None:
        """Reset restart history for a server (e.g., after successful recovery).

        Args:
            server_name: Name of the server
        """
        if server_name in self._restart_history:
            del self._restart_history[server_name]

        if server_name in self._backoff_state:
            del self._backoff_state[server_name]

        logger.info(f"Reset restart history for {server_name}")

    def cleanup_old_history(self, max_age_seconds: int = 3600) -> None:
        """Clean up old restart history entries.

        Args:
            max_age_seconds: Maximum age of history entries to keep
        """
        cutoff = datetime.now() - timedelta(seconds=max_age_seconds)

        for server_name in list(self._restart_history.keys()):
            history = self._restart_history[server_name]

            # Filter out old entries
            recent = [ts for ts in history if ts > cutoff]

            if recent:
                self._restart_history[server_name] = recent
            else:
                # Remove server if no recent history
                del self._restart_history[server_name]

    def get_restart_stats(self, server_name: str) -> Dict:
        """Get restart statistics for a server.

        Args:
            server_name: Name of the server

        Returns:
            Dictionary with restart statistics
        """
        history = self._restart_history.get(server_name, [])

        if not history:
            return {
                "total_restarts": 0,
                "last_restart": None,
                "recent_restarts_1h": 0,
                "recent_restarts_24h": 0
            }

        now = datetime.now()
        one_hour_ago = now - timedelta(hours=1)
        one_day_ago = now - timedelta(days=1)

        return {
            "total_restarts": len(history),
            "last_restart": max(history).isoformat(),
            "recent_restarts_1h": len([ts for ts in history if ts > one_hour_ago]),
            "recent_restarts_24h": len([ts for ts in history if ts > one_day_ago])
        }

    def wait_with_backoff(
        self,
        server_name: str,
        policy: RestartPolicy,
        restart_count: int
    ) -> None:
        """Wait for the appropriate backoff delay before restarting.

        Args:
            server_name: Name of the server
            policy: Restart policy configuration
            restart_count: Number of restarts so far
        """
        delay = self.calculate_backoff_delay(server_name, policy, restart_count)

        if delay > 0:
            logger.info(
                f"Waiting {delay:.2f}s before restarting {server_name} "
                f"(attempt #{restart_count + 1})"
            )
            time.sleep(delay)
