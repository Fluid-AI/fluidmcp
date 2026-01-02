"""Server status and state tracking models for watchdog."""

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Optional


class ServerState(str, Enum):
    """Server lifecycle states."""
    STOPPED = "stopped"
    STARTING = "starting"
    RUNNING = "running"
    HEALTHY = "healthy"
    UNHEALTHY = "unhealthy"
    CRASHED = "crashed"
    RESTARTING = "restarting"
    FAILED = "failed"


@dataclass
class ServerStatus:
    """Server status information."""
    name: str
    state: ServerState
    pid: Optional[int] = None
    port: Optional[int] = None
    started_at: Optional[datetime] = None
    last_health_check: Optional[datetime] = None
    restart_count: int = 0
    error_message: Optional[str] = None

    def get_status_display(self) -> str:
        """Get human-readable status display for CLI with colors."""
        state_emoji = {
            ServerState.STOPPED: "⏹️ ",
            ServerState.STARTING: "🔄",
            ServerState.RUNNING: "▶️ ",
            ServerState.HEALTHY: "✅",
            ServerState.UNHEALTHY: "⚠️ ",
            ServerState.CRASHED: "💥",
            ServerState.RESTARTING: "🔄",
            ServerState.FAILED: "❌"
        }

        emoji = state_emoji.get(self.state, "❓")
        uptime_str = ""

        if hasattr(self, '_uptime_seconds'):
            uptime = getattr(self, '_uptime_seconds')
            hours = int(uptime // 3600)
            minutes = int((uptime % 3600) // 60)
            seconds = int(uptime % 60)
            uptime_str = f" (uptime: {hours}h {minutes}m {seconds}s)"

        base_str = f"{emoji} {self.name} [{self.state.value}]"

        if self.pid:
            base_str += f" PID:{self.pid}"
        if self.port:
            base_str += f" Port:{self.port}"
        if self.restart_count > 0:
            base_str += f" Restarts:{self.restart_count}"

        base_str += uptime_str

        if self.error_message:
            base_str += f"\n  Error: {self.error_message}"

        return base_str


@dataclass
class RestartPolicy:
    """Restart policy configuration."""
    max_restarts: int = 5
    initial_delay_seconds: float = 2.0
    backoff_multiplier: float = 2.0
    max_delay_seconds: float = 60.0
    restart_window_seconds: Optional[int] = 300  # 5 minutes
