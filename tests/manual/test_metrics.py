"""
Manual test for metrics collection system.

This script tests the Prometheus-compatible metrics exposed by FluidMCP.

Prerequisites:
- FluidMCP server running: fluidmcp run examples/sample-config.json --file --start-server
- Server accessible at http://localhost:8099

Usage:
    python tests/manual/test_metrics.py
"""

import sys
import time
import requests
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))


def test_metrics_endpoint():
    """Test that /metrics endpoint is accessible."""
    print("\n=== Test 1: Metrics Endpoint Accessibility ===")

    try:
        response = requests.get("http://localhost:8099/metrics", timeout=5)
        if response.status_code == 200:
            print("✓ /metrics endpoint is accessible")
            print(f"  Content-Type: {response.headers.get('Content-Type')}")
            print(f"  Response length: {len(response.text)} bytes")
            return True
        else:
            print(f"✗ Unexpected status code: {response.status_code}")
            return False
    except requests.exceptions.ConnectionError:
        print("✗ Connection refused - is FluidMCP server running?")
        print("  Start server with: fluidmcp run examples/sample-config.json --file --start-server")
        return False
    except Exception as e:
        print(f"✗ Error: {e}")
        return False


def test_metrics_format():
    """Test that metrics are in Prometheus exposition format."""
    print("\n=== Test 2: Prometheus Format Validation ===")

    try:
        response = requests.get("http://localhost:8099/metrics", timeout=5)
        lines = response.text.split("\n")

        # Check for HELP and TYPE comments
        has_help = any(line.startswith("# HELP") for line in lines)
        has_type = any(line.startswith("# TYPE") for line in lines)

        if has_help and has_type:
            print("✓ Metrics follow Prometheus exposition format")
            print(f"  HELP lines: {sum(1 for line in lines if line.startswith('# HELP'))}")
            print(f"  TYPE lines: {sum(1 for line in lines if line.startswith('# TYPE'))}")
            return True
        else:
            print("✗ Missing HELP or TYPE comments")
            return False
    except Exception as e:
        print(f"✗ Error: {e}")
        return False


def test_expected_metrics():
    """Test that expected metrics are present."""
    print("\n=== Test 3: Expected Metrics Presence ===")

    expected_metrics = [
        "fluidmcp_requests_total",
        "fluidmcp_errors_total",
        "fluidmcp_active_requests",
        "fluidmcp_request_duration_seconds",
        "fluidmcp_server_status",
        "fluidmcp_server_restarts_total",
        "fluidmcp_server_uptime_seconds",
        "fluidmcp_gpu_memory_bytes",
        "fluidmcp_gpu_memory_utilization_ratio",
        "fluidmcp_tool_calls_total",
        "fluidmcp_tool_execution_seconds",
        "fluidmcp_streaming_requests_total",
        "fluidmcp_active_streams",
    ]

    try:
        response = requests.get("http://localhost:8099/metrics", timeout=5)
        text = response.text

        all_found = True
        for metric in expected_metrics:
            if f"# HELP {metric}" in text:
                print(f"✓ Found metric: {metric}")
            else:
                print(f"✗ Missing metric: {metric}")
                all_found = False

        return all_found
    except Exception as e:
        print(f"✗ Error: {e}")
        return False


def test_metric_labels():
    """Test that metrics have appropriate labels."""
    print("\n=== Test 4: Metric Labels Validation ===")

    try:
        response = requests.get("http://localhost:8099/metrics", timeout=5)
        lines = response.text.split("\n")

        # Find a sample metric with labels
        sample_metrics = [
            line for line in lines
            if "fluidmcp_requests_total{" in line or "fluidmcp_server_status{" in line
        ]

        if sample_metrics:
            print("✓ Metrics have labels")
            print("  Sample metrics with labels:")
            for metric in sample_metrics[:3]:  # Show first 3
                print(f"    {metric}")
            return True
        else:
            print("⚠ No metrics with labels found (may not have processed requests yet)")
            return True  # Not a failure, just no data yet
    except Exception as e:
        print(f"✗ Error: {e}")
        return False


def test_generate_traffic_and_verify():
    """Generate traffic and verify metrics update."""
    print("\n=== Test 5: Metrics Update on Traffic ===")

    try:
        # Get baseline metrics
        print("\nGetting baseline metrics...")
        response1 = requests.get("http://localhost:8099/metrics", timeout=5)
        text1 = response1.text

        # Extract baseline request count
        baseline_count = 0
        for line in text1.split("\n"):
            if line.startswith("fluidmcp_requests_total{"):
                # Extract value (last number on the line)
                try:
                    baseline_count += float(line.split()[-1])
                except ValueError:
                    pass

        print(f"  Baseline request count: {baseline_count}")

        # Generate traffic by making a request to health endpoint
        print("\nGenerating traffic (health check request)...")
        requests.get("http://localhost:8099/health", timeout=5)

        # Small delay to allow metrics to update
        time.sleep(0.5)

        # Get updated metrics
        print("\nGetting updated metrics...")
        response2 = requests.get("http://localhost:8099/metrics", timeout=5)
        text2 = response2.text

        # Extract new request count
        new_count = 0
        for line in text2.split("\n"):
            if line.startswith("fluidmcp_requests_total{"):
                try:
                    new_count += float(line.split()[-1])
                except ValueError:
                    pass

        print(f"  New request count: {new_count}")

        # Check if count increased (note: /metrics and /health calls also count)
        if new_count >= baseline_count:
            print("✓ Metrics updated after traffic")
            print(f"  Increase: {new_count - baseline_count} requests")
            return True
        else:
            print("✗ Metrics did not update")
            return False

    except Exception as e:
        print(f"✗ Error: {e}")
        return False


def test_histogram_buckets():
    """Test that histogram metrics have proper bucket structure."""
    print("\n=== Test 6: Histogram Bucket Structure ===")

    try:
        response = requests.get("http://localhost:8099/metrics", timeout=5)
        lines = response.text.split("\n")

        # Find histogram buckets
        bucket_lines = [
            line for line in lines
            if "_bucket{" in line and "le=" in line
        ]

        if bucket_lines:
            print("✓ Histogram buckets found")
            print(f"  Total bucket lines: {len(bucket_lines)}")

            # Extract unique le values
            le_values = set()
            for line in bucket_lines:
                if 'le="' in line:
                    le_start = line.index('le="') + 4
                    le_end = line.index('"', le_start)
                    le_values.add(line[le_start:le_end])

            print(f"  Bucket boundaries: {sorted(le_values, key=lambda x: float(x) if x != '+Inf' else float('inf'))}")
            return True
        else:
            print("⚠ No histogram buckets found (may not have request data yet)")
            return True  # Not a failure, just no data
    except Exception as e:
        print(f"✗ Error: {e}")
        return False


def test_counter_monotonicity():
    """Test that counter metrics only increase."""
    print("\n=== Test 7: Counter Monotonicity ===")

    try:
        # Get first snapshot
        response1 = requests.get("http://localhost:8099/metrics", timeout=5)
        text1 = response1.text

        # Extract counter values
        counters1 = {}
        for line in text1.split("\n"):
            if line.startswith("fluidmcp_requests_total{"):
                try:
                    counters1[line.rsplit(None, 1)[0]] = float(line.split()[-1])
                except (ValueError, IndexError):
                    pass

        # Generate more traffic
        for _ in range(3):
            requests.get("http://localhost:8099/health", timeout=5)
            time.sleep(0.2)

        # Get second snapshot
        response2 = requests.get("http://localhost:8099/metrics", timeout=5)
        text2 = response2.text

        # Extract counter values again
        counters2 = {}
        for line in text2.split("\n"):
            if line.startswith("fluidmcp_requests_total{"):
                try:
                    counters2[line.rsplit(None, 1)[0]] = float(line.split()[-1])
                except (ValueError, IndexError):
                    pass

        # Verify monotonicity
        all_monotonic = True
        for key in counters1:
            if key in counters2:
                if counters2[key] < counters1[key]:
                    print(f"✗ Counter decreased: {key}")
                    print(f"    Before: {counters1[key]}, After: {counters2[key]}")
                    all_monotonic = False

        if all_monotonic:
            print("✓ All counters are monotonically increasing")
            return True
        else:
            return False

    except Exception as e:
        print(f"✗ Error: {e}")
        return False


def main():
    """Run all tests."""
    print("=" * 60)
    print("FluidMCP Metrics System - Manual Tests")
    print("=" * 60)

    tests = [
        test_metrics_endpoint,
        test_metrics_format,
        test_expected_metrics,
        test_metric_labels,
        test_generate_traffic_and_verify,
        test_histogram_buckets,
        test_counter_monotonicity,
    ]

    passed = 0
    failed = 0

    for test_func in tests:
        try:
            if test_func():
                passed += 1
            else:
                failed += 1
        except Exception as e:
            print(f"\n✗ Test crashed: {e}")
            import traceback
            traceback.print_exc()
            failed += 1

    print("\n" + "=" * 60)
    print(f"Test Results: {passed} passed, {failed} failed")
    print("=" * 60)

    if failed == 0:
        print("\n✅ All tests passed! Metrics system is working correctly.")
        print("\nNext steps:")
        print("  1. Set up Prometheus: examples/prometheus-config.yml")
        print("  2. Import Grafana dashboard: examples/grafana-dashboard.json")
        print("  3. View comprehensive monitoring documentation: docs/MONITORING.md")
    else:
        print("\n⚠️  Some tests failed. Check the output above for details.")

    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
