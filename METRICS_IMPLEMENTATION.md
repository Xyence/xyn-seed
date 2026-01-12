# Metrics Collection - Implementation Summary

## What Was Implemented

Production-ready Prometheus metrics collector for monitoring Xyn runtime health.

## Files Created

### 1. `core/observability/metrics.py`
Prometheus gauge definitions for queue and lease health metrics:
- `xyn_queue_depth{status}` - Run count by status
- `xyn_queue_ready_depth` - Runs ready to execute now
- `xyn_queue_future_depth` - Scheduled future runs
- `xyn_queue_oldest_ready_seconds` - Age of oldest waiting run
- `xyn_running_with_expired_lease` - Runs with expired leases (should be ~0)
- `xyn_running_with_active_lease` - Runs with active leases

### 2. `core/observability/collector.py`
Background metrics collection loop:
- `metrics_collector_loop()` - Async loop for periodic collection
- `_collect_once()` - Single collection tick using ephemeral session
- 4 optimized SQL queries using existing indexes
- Error handling and logging

### 3. `scripts/verify_metrics.py`
Verification script to test metrics implementation:
- Import validation
- Collector execution test
- Metrics registry verification

### 4. `docs/metrics.md`
Comprehensive documentation:
- Metrics descriptions and use cases
- Prometheus configuration examples
- Grafana dashboard recommendations
- Alerting rules
- Troubleshooting guide

## Files Modified

### 1. `core/worker.py`
Added metrics collector startup in `worker_loop()`:
```python
# Start metrics collector
from core.observability.collector import metrics_collector_loop
metrics_interval = int(os.getenv("METRICS_COLLECTOR_INTERVAL", "5"))
asyncio.create_task(metrics_collector_loop(interval_seconds=metrics_interval))
```

### 2. `core/main.py`
Added `/metrics` endpoint:
```python
@app.get("/metrics")
async def metrics():
    """Prometheus metrics endpoint."""
    from prometheus_client import generate_latest, CONTENT_TYPE_LATEST
    from fastapi import Response
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
```

### 3. `requirements.txt`
Added prometheus-client dependency:
```
prometheus-client==0.19.0
```

## Design Principles

✓ **Ephemeral sessions**: Fresh DB session per tick (like lease renewal pattern)
✓ **Indexed queries**: All queries use existing indexes (ix_runs_status, ix_runs_run_at, etc.)
✓ **Low cardinality**: No run_id, correlation_id, or other high-cardinality labels
✓ **Non-blocking**: Runs in background without interfering with workers

## Metrics Overview

### Queue Health (80% of operational visibility)

| Metric | Purpose | Alert Threshold |
|--------|---------|-----------------|
| `xyn_queue_ready_depth` | Available work | > 100 for 5m |
| `xyn_queue_oldest_ready_seconds` | Queue latency | > 300s for 5m |
| `xyn_queue_depth{status}` | Overall health | Track trends |

### Lease Health (Worker crash detection)

| Metric | Purpose | Alert Threshold |
|--------|---------|-----------------|
| `xyn_running_with_expired_lease` | Crashed workers | > 0 for 2m (CRITICAL) |
| `xyn_running_with_active_lease` | Worker utilization | 0 with queue > 0 for 5m |

## SQL Queries (All Indexed)

```sql
-- 1) Queue depth by status (uses: ix_runs_status)
SELECT status::text, COUNT(*)::bigint FROM runs GROUP BY status;

-- 2) Ready vs future (uses: ix_runs_status, ix_runs_run_at)
SELECT
  COUNT(*) FILTER (WHERE status='QUEUED' AND run_at <= NOW()) AS ready,
  COUNT(*) FILTER (WHERE status='QUEUED' AND run_at > NOW()) AS future
FROM runs;

-- 3) Oldest ready age (uses: ix_runs_status, ix_runs_run_at, ix_runs_queued_at)
SELECT EXTRACT(EPOCH FROM (NOW() - MIN(queued_at)))
FROM runs WHERE status='QUEUED' AND run_at <= NOW();

-- 4) Lease health (uses: ix_runs_status, ix_runs_lease_expires_at)
SELECT
  COUNT(*) FILTER (WHERE lease_expires_at < NOW()) AS expired,
  COUNT(*) FILTER (WHERE lease_expires_at >= NOW()) AS active
FROM runs WHERE status='RUNNING' AND lease_expires_at IS NOT NULL;
```

## Configuration

```bash
# Worker deployment with metrics collector
METRICS_COLLECTOR_INTERVAL=5  # Default: 5 seconds
```

## Usage

### 1. Install dependencies
```bash
pip install -r requirements.txt
```

### 2. Start worker (metrics collector auto-starts)
```bash
python -m core.worker
```

### 3. Check metrics endpoint
```bash
curl http://localhost:8000/metrics
```

### 4. Configure Prometheus scraping
```yaml
scrape_configs:
  - job_name: 'xyn'
    static_configs:
      - targets: ['xyn-api:8000']
    scrape_interval: 15s
```

## Recommended Alerts

```yaml
# Queue backlog
- alert: XynQueueBacklog
  expr: xyn_queue_ready_depth > 100
  for: 5m

# Old runs waiting
- alert: XynOldestRunWaiting
  expr: xyn_queue_oldest_ready_seconds > 300
  for: 5m

# Expired leases (CRITICAL)
- alert: XynExpiredLeases
  expr: xyn_running_with_expired_lease > 0
  for: 2m
  labels:
    severity: critical

# No workers available
- alert: XynNoActiveWorkers
  expr: xyn_running_with_active_lease == 0 and xyn_queue_ready_depth > 0
  for: 5m
  labels:
    severity: critical
```

## Next Steps (Future Enhancements)

### Phase 2: Worker Heartbeats
Add worker health tracking with heartbeat table:
- `xyn_workers_alive` - Count of healthy workers
- ⚠ Avoid per-worker labels (high cardinality in K8s)

### Phase 3: Blueprint Metrics
Add execution metrics per blueprint:
- `xyn_blueprint_run_count{blueprint, status}` - Runs by blueprint
- `xyn_blueprint_duration_seconds{blueprint}` - Execution time histogram

## Verification

Run verification script:
```bash
python scripts/verify_metrics.py
```

Or manually test:
```bash
# Start worker
python -m core.worker

# In another terminal, check metrics
curl http://localhost:8000/metrics | grep xyn_
```

## Architecture

```
┌─────────────────────────────────────────────────┐
│ Worker Process                                   │
│                                                  │
│  ┌─────────────┐         ┌──────────────────┐  │
│  │ worker_loop │         │ metrics_collector │  │
│  │             │         │ (background task)│  │
│  │ - claim     │         │                  │  │
│  │ - execute   │         │ - ephemeral DB   │  │
│  │ - renew     │         │ - 4 SQL queries  │  │
│  └─────────────┘         │ - update gauges  │  │
│                          └──────────────────┘  │
└─────────────────────────────────────────────────┘
                     │
                     │ Updates Prometheus registry
                     ▼
         ┌───────────────────────┐
         │ /metrics endpoint     │
         │ (Prometheus scrapes)  │
         └───────────────────────┘
```

## Testing

Metrics collector will:
1. Start automatically when worker starts
2. Log: "Starting metrics collector (interval=5s)"
3. Run queries every 5 seconds (configurable)
4. Update Prometheus gauges
5. Handle errors gracefully (logs exception, continues)

Check worker logs for:
```
Starting metrics collector (interval=5s)
```

Access metrics:
```bash
curl localhost:8000/metrics | grep xyn_
```

Expected output:
```
xyn_queue_depth{status="QUEUED"} 15.0
xyn_queue_ready_depth 12.0
xyn_queue_oldest_ready_seconds 8.5
xyn_running_with_expired_lease 0.0
xyn_running_with_active_lease 3.0
```

## Complete ✓

All components implemented and ready for production use.
