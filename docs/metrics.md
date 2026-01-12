# Metrics Collection

Production-ready Prometheus metrics for monitoring Xyn runtime health.

## Overview

The metrics collector is a background loop that periodically queries the database to update Prometheus gauges. It provides visibility into queue health, lease status, and worker behavior without interfering with run execution.

## Design Principles

1. **Ephemeral sessions**: Uses a fresh DB session per collection tick (like lease renewal pattern)
2. **Indexed queries**: All queries use existing indexes for cheap execution
3. **Low cardinality**: No high-cardinality labels (no `run_id`, `correlation_id`, etc.)
4. **Non-blocking**: Runs in background, doesn't interfere with workers

## Metrics Exposed

### Queue Health

**`xyn_queue_depth{status}`**
- Description: Count of runs by status
- Labels: `status` (QUEUED, RUNNING, COMPLETED, FAILED, CANCELLED)
- Use: Overall queue health and backlog monitoring

**`xyn_queue_ready_depth`**
- Description: Queued runs ready to execute (`run_at <= now()`)
- Use: Available work for workers to claim

**`xyn_queue_future_depth`**
- Description: Queued runs scheduled for future (`run_at > now()`)
- Use: Scheduled/delayed work

**`xyn_queue_oldest_ready_seconds`**
- Description: Age in seconds of oldest ready queued run
- Use: Queue latency and backlog pressure detection

### Lease Health

**`xyn_running_with_expired_lease`**
- Description: RUNNING runs with expired leases (should be ~0)
- Use: Detect crashed workers or lease renewal failures

**`xyn_running_with_active_lease`**
- Description: RUNNING runs with active leases
- Use: Current worker utilization

## Configuration

Environment variables:

```bash
# Metrics collector interval (default: 5 seconds)
METRICS_COLLECTOR_INTERVAL=5
```

## Endpoints

### `/metrics`

Prometheus scrape endpoint exposing all runtime metrics.

**Example:**
```bash
curl http://localhost:8000/metrics
```

**Output:**
```prometheus
# HELP xyn_queue_depth Run count by status
# TYPE xyn_queue_depth gauge
xyn_queue_depth{status="QUEUED"} 15.0
xyn_queue_depth{status="RUNNING"} 3.0
xyn_queue_depth{status="COMPLETED"} 142.0

# HELP xyn_queue_ready_depth Queued runs ready to execute (run_at <= now)
# TYPE xyn_queue_ready_depth gauge
xyn_queue_ready_depth 12.0

# HELP xyn_queue_future_depth Queued runs scheduled for the future (run_at > now)
# TYPE xyn_queue_future_depth gauge
xyn_queue_future_depth 3.0

# HELP xyn_queue_oldest_ready_seconds Age in seconds of oldest ready queued run
# TYPE xyn_queue_oldest_ready_seconds gauge
xyn_queue_oldest_ready_seconds 8.5

# HELP xyn_running_with_expired_lease RUNNING runs with expired leases (should be ~0)
# TYPE xyn_running_with_expired_lease gauge
xyn_running_with_expired_lease 0.0

# HELP xyn_running_with_active_lease RUNNING runs with active leases
# TYPE xyn_running_with_active_lease gauge
xyn_running_with_active_lease 3.0
```

## Prometheus Configuration

Add scrape config to `prometheus.yml`:

```yaml
scrape_configs:
  - job_name: 'xyn'
    static_configs:
      - targets: ['xyn-api:8000']
    scrape_interval: 15s
    metrics_path: /metrics
```

## Alerting Rules

Example Prometheus alerting rules:

```yaml
groups:
  - name: xyn_alerts
    interval: 30s
    rules:
      # Queue backlog
      - alert: XynQueueBacklog
        expr: xyn_queue_ready_depth > 100
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "Xyn queue has {{ $value }} ready runs"

      # Old runs waiting
      - alert: XynOldestRunWaiting
        expr: xyn_queue_oldest_ready_seconds > 300
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "Oldest queued run waiting {{ $value }}s"

      # Expired leases (crashed workers)
      - alert: XynExpiredLeases
        expr: xyn_running_with_expired_lease > 0
        for: 2m
        labels:
          severity: critical
        annotations:
          summary: "{{ $value }} runs with expired leases (crashed workers?)"

      # No active workers
      - alert: XynNoActiveWorkers
        expr: xyn_running_with_active_lease == 0 and xyn_queue_ready_depth > 0
        for: 5m
        labels:
          severity: critical
        annotations:
          summary: "No active workers but {{ $value }} runs waiting"
```

## Grafana Dashboard

Key panels for operations dashboard:

1. **Queue Depth by Status** (stacked area chart)
   - Query: `xyn_queue_depth`
   - Shows run distribution across statuses over time

2. **Ready vs Future Queue** (time series)
   - Query: `xyn_queue_ready_depth` and `xyn_queue_future_depth`
   - Shows immediately available vs scheduled work

3. **Queue Latency** (time series)
   - Query: `xyn_queue_oldest_ready_seconds`
   - Shows how long oldest run has been waiting

4. **Lease Health** (stat panels)
   - Query: `xyn_running_with_expired_lease` (should be 0)
   - Query: `xyn_running_with_active_lease` (worker utilization)

5. **Throughput** (rate)
   - Query: `rate(xyn_queue_depth{status="COMPLETED"}[5m])`
   - Shows run completion rate

## Architecture

### File Structure

```
core/observability/
├── __init__.py
├── metrics.py      # Prometheus gauge definitions
└── collector.py    # Background collection loop
```

### Integration Points

1. **Worker startup** (`core/worker.py`)
   - Metrics collector task started automatically
   - Runs alongside worker loop in background

2. **FastAPI app** (`core/main.py`)
   - `/metrics` endpoint exposes Prometheus data
   - Available on API and worker deployments

### SQL Queries

All queries use existing indexes for efficiency:

```sql
-- Queue depth by status (uses: ix_runs_status)
SELECT status::text, COUNT(*)::bigint
FROM runs
GROUP BY status;

-- Ready vs future (uses: ix_runs_status, ix_runs_run_at)
SELECT
  COUNT(*) FILTER (WHERE status='QUEUED'::runstatus AND run_at <= NOW()) AS ready,
  COUNT(*) FILTER (WHERE status='QUEUED'::runstatus AND run_at > NOW()) AS future
FROM runs;

-- Oldest ready age (uses: ix_runs_status, ix_runs_run_at, ix_runs_queued_at)
SELECT EXTRACT(EPOCH FROM (NOW() - MIN(queued_at)))::double precision
FROM runs
WHERE status='QUEUED'::runstatus AND run_at <= NOW();

-- Lease health (uses: ix_runs_status, ix_runs_lease_expires_at)
SELECT
  COUNT(*) FILTER (WHERE lease_expires_at < NOW()) AS expired,
  COUNT(*) FILTER (WHERE lease_expires_at >= NOW()) AS active
FROM runs
WHERE status='RUNNING'::runstatus AND lease_expires_at IS NOT NULL;
```

## Future Enhancements

### Worker Heartbeats (Phase 2)

Add worker health metrics:

```python
# core/observability/metrics.py
workers_alive = Gauge(
    "xyn_workers_alive",
    "Count of workers with recent heartbeat"
)

worker_heartbeat_age_seconds = Gauge(
    "xyn_worker_heartbeat_age_seconds",
    "Seconds since last heartbeat",
    ["worker_id"]
)
```

⚠ **Cardinality warning**: `worker_id` label creates one time series per worker. In Kubernetes with pod churn, this can accumulate. Consider:
- Using count-based aggregation (`workers_alive`) instead
- Enabling only in development
- Implementing metric cleanup for terminated workers

### Blueprint-Specific Metrics

Add per-blueprint execution metrics:

```python
blueprint_run_count = Counter(
    "xyn_blueprint_run_count",
    "Total runs by blueprint",
    ["blueprint_name", "status"]
)

blueprint_duration_seconds = Histogram(
    "xyn_blueprint_duration_seconds",
    "Blueprint execution duration",
    ["blueprint_name"]
)
```

## Troubleshooting

**Metrics not updating:**
- Check worker logs for "Starting metrics collector"
- Verify `METRICS_COLLECTOR_INTERVAL` is set correctly
- Check for DB connection errors in logs

**High cardinality warnings:**
- Ensure no `run_id` or `correlation_id` labels
- Limit worker_id metrics to development only
- Use aggregation instead of per-entity labels

**Slow queries:**
- All queries should use indexes
- Check `EXPLAIN ANALYZE` on each collector query
- Consider increasing `METRICS_COLLECTOR_INTERVAL`

## Verification

Test metrics implementation:

```bash
# Run verification script
python scripts/verify_metrics.py

# Manual test with running system
curl http://localhost:8000/metrics | grep xyn_
```
