"""
Metrics integration for Replicate inference features.

Registers Replicate-specific metrics (cache, rate limiter) with the unified
FluidMCP metrics system for Prometheus-compatible monitoring.
"""

from loguru import logger

from .metrics import get_registry, Gauge


def register_replicate_metrics():
    """
    Register Replicate-specific metrics with the global metrics registry.

    Metrics registered:
    - fluidmcp_replicate_cache_hits_total: Total cache hits
    - fluidmcp_replicate_cache_misses_total: Total cache misses
    - fluidmcp_replicate_cache_size: Current number of cached entries
    - fluidmcp_replicate_cache_hit_rate: Cache hit rate (0.0-1.0)
    - fluidmcp_replicate_rate_limiter_tokens: Available tokens for rate limiter
    - fluidmcp_replicate_rate_limiter_utilization: Rate limiter utilization (0.0-1.0)
    """
    registry = get_registry()

    # Cache metrics (using Gauge because cache stats track absolute values, not deltas)
    registry.register(Gauge(
        "fluidmcp_replicate_cache_hits_total",
        "Total number of cache hits for Replicate responses",
        labels=[]  # Global cache, no per-model labels
    ))

    registry.register(Gauge(
        "fluidmcp_replicate_cache_misses_total",
        "Total number of cache misses for Replicate responses",
        labels=[]
    ))

    registry.register(Gauge(
        "fluidmcp_replicate_cache_size",
        "Current number of entries in Replicate response cache",
        labels=[]
    ))

    registry.register(Gauge(
        "fluidmcp_replicate_cache_hit_rate",
        "Cache hit rate as a ratio (0.0-1.0)",
        labels=[]
    ))

    # Rate limiter metrics (per-model)
    registry.register(Gauge(
        "fluidmcp_replicate_rate_limiter_tokens",
        "Available tokens in rate limiter bucket",
        labels=["model_id"]
    ))

    registry.register(Gauge(
        "fluidmcp_replicate_rate_limiter_utilization",
        "Rate limiter utilization as a ratio (0.0-1.0)",
        labels=["model_id"]
    ))

    registry.register(Gauge(
        "fluidmcp_replicate_rate_limiter_capacity",
        "Maximum capacity of rate limiter bucket",
        labels=["model_id"]
    ))

    registry.register(Gauge(
        "fluidmcp_replicate_rate_limiter_rate",
        "Rate limiter refill rate (tokens per second)",
        labels=["model_id"]
    ))

    logger.debug("Registered Replicate metrics with global registry")


async def update_cache_metrics():
    """
    Update cache metrics in the global registry.

    Fetches current cache statistics and updates the corresponding
    Prometheus metrics.
    """
    from .response_cache import peek_response_cache

    cache = await peek_response_cache()
    if cache is None:
        # Cache not initialized, set all metrics to 0 using proper API
        registry = get_registry()

        hits_metric = registry.get_metric("fluidmcp_replicate_cache_hits_total")
        misses_metric = registry.get_metric("fluidmcp_replicate_cache_misses_total")
        size_metric = registry.get_metric("fluidmcp_replicate_cache_size")
        hit_rate_metric = registry.get_metric("fluidmcp_replicate_cache_hit_rate")

        # Set all to 0 using Gauge.set() (thread-safe)
        if hits_metric:
            hits_metric.set(0.0)
        if misses_metric:
            misses_metric.set(0.0)
        if size_metric:
            size_metric.set(0.0)
        if hit_rate_metric:
            hit_rate_metric.set(0.0)

        return

    # Get cache stats
    stats = await cache.get_stats()

    # Update metrics using proper Gauge API (thread-safe)
    registry = get_registry()

    hits_metric = registry.get_metric("fluidmcp_replicate_cache_hits_total")
    if hits_metric:
        hits_metric.set(float(stats["hits"]))

    misses_metric = registry.get_metric("fluidmcp_replicate_cache_misses_total")
    if misses_metric:
        misses_metric.set(float(stats["misses"]))

    size_metric = registry.get_metric("fluidmcp_replicate_cache_size")
    if size_metric:
        size_metric.set(float(stats["size"]))

    hit_rate_metric = registry.get_metric("fluidmcp_replicate_cache_hit_rate")
    if hit_rate_metric:
        # Convert percentage to ratio (0.0-1.0)
        hit_rate_metric.set(stats["hit_rate"] / 100.0)


async def update_rate_limiter_metrics():
    """
    Update rate limiter metrics in the global registry.

    Fetches statistics for all rate limiters and updates the corresponding
    Prometheus metrics with per-model labels.
    """
    from .rate_limiter import get_all_rate_limiter_stats

    # Get all rate limiter stats
    all_stats = await get_all_rate_limiter_stats()

    registry = get_registry()

    if not all_stats:
        # No rate limiters active: clear all per-model samples to avoid stale series
        tokens_metric = registry.get_metric("fluidmcp_replicate_rate_limiter_tokens")
        utilization_metric = registry.get_metric("fluidmcp_replicate_rate_limiter_utilization")
        capacity_metric = registry.get_metric("fluidmcp_replicate_rate_limiter_capacity")
        rate_metric = registry.get_metric("fluidmcp_replicate_rate_limiter_rate")

        for metric in (tokens_metric, utilization_metric, capacity_metric, rate_metric):
            if metric:
                # Clear all samples (thread-safe via metric lock)
                with metric._lock:
                    metric.samples.clear()
        return

    tokens_metric = registry.get_metric("fluidmcp_replicate_rate_limiter_tokens")
    utilization_metric = registry.get_metric("fluidmcp_replicate_rate_limiter_utilization")
    capacity_metric = registry.get_metric("fluidmcp_replicate_rate_limiter_capacity")
    rate_metric = registry.get_metric("fluidmcp_replicate_rate_limiter_rate")

    # Update metrics for each model using proper Gauge API (thread-safe)
    for model_id, stats in all_stats.items():
        label_values = {"model_id": model_id}

        if tokens_metric:
            tokens_metric.set(stats["available_tokens"], label_values)

        if utilization_metric:
            # Convert percentage to ratio (0.0-1.0)
            utilization_metric.set(stats["utilization_pct"] / 100.0, label_values)

        if capacity_metric:
            capacity_metric.set(float(stats["capacity"]), label_values)

        if rate_metric:
            rate_metric.set(stats["rate"], label_values)


# Auto-register metrics on module import
register_replicate_metrics()
