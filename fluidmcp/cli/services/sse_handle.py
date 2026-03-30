"""
SSE transport handle for MCP servers.

Kept in its own module to avoid circular imports between
package_launcher.py and server_manager.py.
"""
import subprocess
from loguru import logger


class SseSubprocessHandle:
    """
    Wraps a subprocess.Popen for an SSE-transport MCP server.

    We still OWN the process (spawned via uv/python/etc.) so we keep the
    real Popen for lifecycle management (kill/terminate/poll).
    Communication happens over HTTP instead of stdin/stdout.

    Attributes:
        _process:  The real subprocess.Popen — used for kill/terminate/poll.
        sse_url:   Base HTTP URL, e.g. "http://127.0.0.1:8000".
        pid:       Delegated to the underlying process.
        returncode: Delegated to the underlying process.
    """

    def __init__(self, process: subprocess.Popen, sse_url: str):
        self._process = process
        self.sse_url = sse_url

    @property
    def pid(self):
        return self._process.pid

    @property
    def returncode(self):
        return self._process.returncode

    def poll(self):
        return self._process.poll()

    def terminate(self):
        self._process.terminate()

    def kill(self):
        self._process.kill()

    def wait(self, timeout=None):
        return self._process.wait(timeout=timeout)