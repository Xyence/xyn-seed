"""Prometheus metrics for Xyn runtime observability.

Design principles:
- Low-cardinality labels only (no run_id, correlation_id)
- Gauges updated periodically from DB queries
- No metrics collection in hot paths (claim, execute, etc.)
"""
from prometheus_client import Gauge

# Queue health metrics
queue_depth = Gauge(
    "xyn_queue_depth",
    "Run count by status",
    ["status"]
)

queue_ready_depth = Gauge(
    "xyn_queue_ready_depth",
    "Queued runs ready to execute (run_at <= now)"
)

queue_future_depth = Gauge(
    "xyn_queue_future_depth",
    "Queued runs scheduled for the future (run_at > now)"
)

queue_oldest_ready_seconds = Gauge(
    "xyn_queue_oldest_ready_seconds",
    "Age in seconds of oldest ready queued run"
)

# Lease health metrics
running_with_expired_lease = Gauge(
    "xyn_running_with_expired_lease",
    "RUNNING runs with expired leases (should be ~0)"
)

running_with_active_lease = Gauge(
    "xyn_running_with_active_lease",
    "RUNNING runs with active leases"
)
