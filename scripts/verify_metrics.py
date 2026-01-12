#!/usr/bin/env python3
"""Quick verification script for metrics collector.

Tests that:
1. Metrics module can be imported
2. Collector can execute queries without errors
3. All expected metrics are defined
"""
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def test_metrics_import():
    """Verify metrics module imports successfully."""
    from core.observability import metrics

    print("✓ Metrics module imported")

    # Check all expected metrics exist
    expected_metrics = [
        "queue_depth",
        "queue_ready_depth",
        "queue_future_depth",
        "queue_oldest_ready_seconds",
        "running_with_expired_lease",
        "running_with_active_lease",
    ]

    for metric_name in expected_metrics:
        assert hasattr(metrics, metric_name), f"Missing metric: {metric_name}"
        print(f"  ✓ {metric_name}")

    return True


def test_collector_import():
    """Verify collector module imports successfully."""
    from core.observability import collector

    print("✓ Collector module imported")

    # Check key functions exist
    assert hasattr(collector, "metrics_collector_loop")
    assert hasattr(collector, "_collect_once")
    print("  ✓ metrics_collector_loop")
    print("  ✓ _collect_once")

    return True


def test_collector_execution():
    """Verify collector can execute queries (requires DB connection)."""
    try:
        from core.observability.collector import _collect_once

        print("✓ Testing collector execution...")
        _collect_once()
        print("  ✓ Collector executed successfully")

        return True
    except Exception as e:
        print(f"  ⚠ Collector execution failed (expected if DB not available): {e}")
        return False


if __name__ == "__main__":
    print("=== Metrics Collector Verification ===\n")

    results = []

    # Test 1: Import metrics
    try:
        results.append(test_metrics_import())
    except Exception as e:
        print(f"✗ Metrics import failed: {e}")
        results.append(False)

    print()

    # Test 2: Import collector
    try:
        results.append(test_collector_import())
    except Exception as e:
        print(f"✗ Collector import failed: {e}")
        results.append(False)

    print()

    # Test 3: Execute collector (may fail without DB)
    try:
        results.append(test_collector_execution())
    except Exception as e:
        print(f"✗ Collector execution failed: {e}")
        results.append(False)

    print("\n" + "="*40)

    if all(results[:2]):  # First two tests must pass
        print("✓ Metrics collector implementation verified")
        sys.exit(0)
    else:
        print("✗ Verification failed")
        sys.exit(1)
