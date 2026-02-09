"""
Tests for Replicate metrics integration with unified metrics system.
"""

import pytest
from fluidmcp.cli.services.metrics import get_registry
from fluidmcp.cli.services.replicate_metrics import (
    update_cache_metrics,
    update_rate_limiter_metrics
)


def test_replicate_metrics_registered():
    """Test that Replicate metrics are registered in global registry."""
    registry = get_registry()

    # Check cache metrics are registered
    assert registry.get_metric("fluidmcp_replicate_cache_hits_total") is not None
    assert registry.get_metric("fluidmcp_replicate_cache_misses_total") is not None
    assert registry.get_metric("fluidmcp_replicate_cache_size") is not None
    assert registry.get_metric("fluidmcp_replicate_cache_hit_rate") is not None

    # Check rate limiter metrics are registered
    assert registry.get_metric("fluidmcp_replicate_rate_limiter_tokens") is not None
    assert registry.get_metric("fluidmcp_replicate_rate_limiter_utilization") is not None
    assert registry.get_metric("fluidmcp_replicate_rate_limiter_capacity") is not None
    assert registry.get_metric("fluidmcp_replicate_rate_limiter_rate") is not None


@pytest.mark.asyncio
async def test_update_cache_metrics_no_cache():
    """Test updating cache metrics when cache is not initialized."""
    # This should not raise an error
    await update_cache_metrics()

    # Verify metrics are set to 0
    registry = get_registry()
    hits_metric = registry.get_metric("fluidmcp_replicate_cache_hits_total")
    assert hits_metric.samples[()] == 0


@pytest.mark.asyncio
async def test_update_cache_metrics_with_cache():
    """Test updating cache metrics when cache exists."""
    from fluidmcp.cli.services.response_cache import get_response_cache

    # Create cache and add some test data
    cache = await get_response_cache(ttl=300, max_size=100, enabled=True)

    # Simulate some cache hits/misses
    cache._hits = 42
    cache._misses = 8

    # Update metrics
    await update_cache_metrics()

    # Verify metrics are updated
    registry = get_registry()

    hits_metric = registry.get_metric("fluidmcp_replicate_cache_hits_total")
    assert hits_metric.samples[()] == 42.0

    misses_metric = registry.get_metric("fluidmcp_replicate_cache_misses_total")
    assert misses_metric.samples[()] == 8.0

    size_metric = registry.get_metric("fluidmcp_replicate_cache_size")
    assert size_metric.samples[()] == 0.0  # No actual cached items

    hit_rate_metric = registry.get_metric("fluidmcp_replicate_cache_hit_rate")
    # hit_rate = 42 / (42 + 8) * 100 = 84.0%
    # stored as ratio: 0.84
    assert abs(hit_rate_metric.samples[()] - 0.84) < 0.01


@pytest.mark.asyncio
async def test_update_rate_limiter_metrics_no_limiters():
    """Test updating rate limiter metrics when no limiters exist."""
    from fluidmcp.cli.services.rate_limiter import clear_rate_limiters

    # Clear any existing limiters
    await clear_rate_limiters()

    # This should not raise an error
    await update_rate_limiter_metrics()


@pytest.mark.asyncio
async def test_update_rate_limiter_metrics_with_limiter():
    """Test updating rate limiter metrics when limiters exist."""
    from fluidmcp.cli.services.rate_limiter import get_rate_limiter, clear_rate_limiters

    # Clear existing limiters first
    await clear_rate_limiters()

    # Create a test rate limiter (variable unused but needed to populate registry)
    await get_rate_limiter("test-model", rate=5.0, capacity=10)

    # Update metrics
    await update_rate_limiter_metrics()

    # Verify metrics are updated
    registry = get_registry()

    tokens_metric = registry.get_metric("fluidmcp_replicate_rate_limiter_tokens")
    assert ("test-model",) in tokens_metric.samples
    assert tokens_metric.samples[("test-model",)] == 10.0  # Full capacity initially

    utilization_metric = registry.get_metric("fluidmcp_replicate_rate_limiter_utilization")
    assert ("test-model",) in utilization_metric.samples
    assert utilization_metric.samples[("test-model",)] == 0.0  # 0% used initially

    capacity_metric = registry.get_metric("fluidmcp_replicate_rate_limiter_capacity")
    assert ("test-model",) in capacity_metric.samples
    assert capacity_metric.samples[("test-model",)] == 10.0

    rate_metric = registry.get_metric("fluidmcp_replicate_rate_limiter_rate")
    assert ("test-model",) in rate_metric.samples
    assert rate_metric.samples[("test-model",)] == 5.0

    # Clean up
    await clear_rate_limiters()


@pytest.mark.asyncio
async def test_metrics_render_prometheus_format():
    """Test that metrics can be rendered in Prometheus format."""
    from fluidmcp.cli.services.rate_limiter import get_rate_limiter, clear_rate_limiters

    # Clear and setup test data
    await clear_rate_limiters()
    # Create limiter (variable unused but needed to populate registry)
    await get_rate_limiter("test-model-prom", rate=10.0, capacity=20)

    # Update metrics
    await update_rate_limiter_metrics()

    # Render all metrics
    registry = get_registry()
    prometheus_output = registry.render_all()

    # Verify Prometheus format
    assert "fluidmcp_replicate_rate_limiter_tokens" in prometheus_output
    assert 'model_id="test-model-prom"' in prometheus_output
    assert "# TYPE fluidmcp_replicate_rate_limiter_tokens gauge" in prometheus_output

    # Clean up
    await clear_rate_limiters()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
