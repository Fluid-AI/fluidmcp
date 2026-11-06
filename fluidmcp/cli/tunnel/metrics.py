"""
Prometheus metrics for the tunnel client, exposed through the existing /metrics endpoint.
"""

from ..services.metrics import Counter, Gauge, Histogram, get_registry

# Tunnel calls include the local MCP server's work, so they run longer than plain HTTP requests.
REQUEST_BUCKETS = [0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 45.0]


def register_tunnel_metrics():
    """
    Register tunnel metrics with the global metrics registry.

    Metrics registered:
    - fluidmcp_tunnel_connected: 1 while the tunnel is up (Gauge)
    - fluidmcp_tunnel_requests_total: Forwarded requests by server and result (Counter)
    - fluidmcp_tunnel_request_seconds: Local handling time per forwarded request (Histogram)
    - fluidmcp_tunnel_handshake_failures_total: Failed or rejected connection attempts (Counter)
    """
    registry = get_registry()
    registry.register(Gauge("fluidmcp_tunnel_connected", "Whether the tunnel to GPT Engine is connected (1) or not (0)"))
    registry.register(Counter(
        "fluidmcp_tunnel_requests_total",
        "Requests received through the tunnel",
        labels=["server", "result"],
    ))
    registry.register(Histogram(
        "fluidmcp_tunnel_request_seconds",
        "Time to handle a tunnel request against the local gateway",
        labels=["server"],
        buckets=REQUEST_BUCKETS,
    ))
    registry.register(Counter(
        "fluidmcp_tunnel_handshake_failures_total",
        "Tunnel connection attempts rejected during authentication or handshake",
    ))


def set_connected(connected: bool) -> None:
    get_registry().get_metric("fluidmcp_tunnel_connected").set(1.0 if connected else 0.0)


def record_request(server: str, result: str, seconds: float) -> None:
    registry = get_registry()
    registry.get_metric("fluidmcp_tunnel_requests_total").inc({"server": server, "result": result})
    registry.get_metric("fluidmcp_tunnel_request_seconds").observe(seconds, {"server": server})


def record_handshake_failure() -> None:
    get_registry().get_metric("fluidmcp_tunnel_handshake_failures_total").inc()


register_tunnel_metrics()
