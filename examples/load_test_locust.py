"""
Load Testing for FluidMCP `fmcp serve` Mode.

Targets the management API, MCP proxy, health, and metrics endpoints
exposed by `fmcp serve --allow-insecure`.

MCP servers are dynamic — running servers are discovered at startup via
GET /api/servers and load is distributed across all running instances.

Installation:
    pip install locust loguru

Usage:
    # Start FluidMCP in serve mode first:
    fmcp serve --allow-insecure

    # Run load test (web UI — open http://localhost:8089)
    locust -f examples/load_test_locust.py \\
           --host=https://fantastic-system-pj47wr6j7wq5hrgpg-8099.app.github.dev

    # Run headless — all user classes
    locust -f examples/load_test_locust.py \\
           --host=https://fantastic-system-pj47wr6j7wq5hrgpg-8099.app.github.dev \\
           --users 20 --spawn-rate 4 --run-time 120s --headless --only-summary

    # Run headless — single class
    locust -f examples/load_test_locust.py \\
           --host=https://fantastic-system-pj47wr6j7wq5hrgpg-8099.app.github.dev \\
           --users 10 --spawn-rate 2 --run-time 60s --headless \\
           -u ManagementAPIUser

Environment Variables:
    AUTH_TOKEN  Bearer token — only needed with --secure mode (omit for --allow-insecure)
"""

import os
import random
from locust import HttpUser, task, between, events  # type: ignore
from loguru import logger


def _auth_headers():
    """Return Authorization header dict if AUTH_TOKEN is set, else empty dict."""
    token = os.getenv("AUTH_TOKEN")
    if token:
        return {"Authorization": f"Bearer {token}"}
    return {}


class HealthUser(HttpUser):
    """
    Lightweight baseline traffic against the health and root endpoints.
    These are always available in serve mode with no auth required.
    """

    wait_time = between(1, 3)

    def on_start(self):
        self.client.headers.update(_auth_headers())

    @task(3)
    def health_check(self):
        """Poll /health — primary liveness indicator."""
        with self.client.get("/health", name="/health", catch_response=True) as resp:
            if resp.status_code == 200:
                resp.success()
            elif resp.status_code == 503:
                resp.failure(f"Server degraded: {resp.text[:200]}")
            else:
                resp.failure(f"Unexpected status {resp.status_code}")

    @task(1)
    def root(self):
        """GET / — API info endpoint."""
        self.client.get("/", name="/")


class ManagementAPIUser(HttpUser):
    """
    Simulates a client managing MCP servers through the REST API.

    Performs read-only operations: list servers, poll status, discover tools,
    and fetch logs. No destructive mutations are performed.
    """

    wait_time = between(1, 4)

    def on_start(self):
        self.client.headers.update(_auth_headers())
        self.server_id = None

        # Prefer a running server; fall back to any server if none are running
        resp = self.client.get("/api/servers", name="/api/servers [discovery]")
        if resp.status_code == 200:
            servers = resp.json()
            if isinstance(servers, list) and servers:
                running = [s for s in servers if isinstance(s, dict) and s.get("status") == "running"]
                source = running if running else servers
                first = source[0]
                self.server_id = first.get("server_id") or first.get("id")
                logger.info(f"ManagementAPIUser: using server_id={self.server_id} (running={bool(running)})")
            else:
                logger.warning("ManagementAPIUser: no servers found — server-specific tasks will be skipped")
        else:
            logger.warning(f"ManagementAPIUser: failed to list servers ({resp.status_code})")

    @task(3)
    def list_servers(self):
        """List all configured servers."""
        self.client.get("/api/servers", name="/api/servers")

    @task(2)
    def server_status(self):
        """Poll the runtime status of a specific server."""
        if not self.server_id:
            return
        self.client.get(
            f"/api/servers/{self.server_id}/status",
            name="/api/servers/{id}/status",
        )

    @task(2)
    def server_tools(self):
        """Discover tools exposed by a specific server."""
        if not self.server_id:
            return
        self.client.get(
            f"/api/servers/{self.server_id}/tools",
            name="/api/servers/{id}/tools",
        )

    @task(1)
    def server_logs(self):
        """Fetch recent logs from a specific server."""
        if not self.server_id:
            return
        self.client.get(
            f"/api/servers/{self.server_id}/logs",
            name="/api/servers/{id}/logs",
        )


class MCPProxyUser(HttpUser):
    """
    Simulates an MCP client sending JSON-RPC requests through the proxy.

    Running servers are discovered dynamically via GET /api/servers on startup.
    Load is distributed randomly across all running servers. No hardcoded server
    names — always uses live discovery.

    Task distribution: 70% tools/call, 30% tools/list.
    """

    wait_time = between(1, 3)

    def on_start(self):
        self.client.headers.update(_auth_headers())
        self.servers = []

        # Discover running servers once — never repeated per request
        resp = self.client.get("/api/servers", name="/api/servers [discovery]")
        if resp.status_code == 200:
            all_servers = resp.json()
            self.servers = [
                s.get("server_id") or s.get("id")
                for s in all_servers
                if isinstance(s, dict) and s.get("status") == "running"
            ]
            # Filter out any None values (malformed entries)
            self.servers = [s for s in self.servers if s]
            logger.info(f"MCPProxyUser: {len(self.servers)} running servers: {self.servers}")
        else:
            logger.warning(f"MCPProxyUser: server discovery failed ({resp.status_code}) — all proxy tasks will be skipped")

    def _pick_tool(self, server_id: str) -> str:
        """Select an appropriate tool based on the server type."""
        if "council" in server_id.lower():
            return "send_response"
        return "tools/list"

    @task(7)
    def tools_call(self):
        """Send tools/call JSON-RPC (70% of requests)."""
        if not self.servers:
            return
        server = random.choice(self.servers)
        tool = self._pick_tool(server)
        self.client.post(
            f"/{server}/mcp",
            json={
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/call",
                "params": {"name": tool, "arguments": {}},
            },
            name="/{server}/mcp [tools/call]",
        )

    @task(3)
    def tools_list(self):
        """Send tools/list JSON-RPC (30% of requests)."""
        if not self.servers:
            return
        server = random.choice(self.servers)
        self.client.post(
            f"/{server}/mcp",
            json={"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}},
            name="/{server}/mcp [tools/list]",
        )


class MetricsUser(HttpUser):
    """
    Simulates a monitoring agent scraping metrics periodically.
    Low frequency — high wait time between requests.
    """

    wait_time = between(5, 10)

    def on_start(self):
        self.client.headers.update(_auth_headers())

    @task
    def scrape_metrics(self):
        """Scrape JSON metrics — silently skips if endpoint is not available."""
        with self.client.get("/metrics/json", name="/metrics/json", catch_response=True) as resp:
            if resp.status_code == 200:
                resp.success()
            elif resp.status_code == 404:
                resp.success()  # endpoint not present in this deployment — skip silently
            elif resp.status_code == 401:
                resp.failure("Metrics requires auth — set AUTH_TOKEN or use --allow-insecure")
            else:
                resp.failure(f"Unexpected status {resp.status_code}")


# ---------------------------------------------------------------------------
# Event hooks
# ---------------------------------------------------------------------------

@events.test_start.add_listener
def on_test_start(environment, **kwargs):
    logger.info("=" * 60)
    logger.info("FluidMCP Serve Mode Load Test Starting")
    logger.info(f"  Target    : {environment.host}")
    logger.info(f"  Auth      : {'yes (AUTH_TOKEN set)' if os.getenv('AUTH_TOKEN') else 'no (insecure mode)'}")
    logger.info("  Discovery : running servers fetched per-user in on_start")
    logger.info("=" * 60)


@events.test_stop.add_listener
def on_test_stop(environment, **kwargs):
    logger.info("=" * 60)
    logger.info("FluidMCP Serve Mode Load Test Complete")
    logger.info("=" * 60)


@events.request.add_listener
def on_request(request_type, name, response_time, response_length, exception, **kwargs):
    if exception:
        logger.warning(f"Request failed: {request_type} {name} — {exception}")
