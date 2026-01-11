# Xyn Seed v0.0 - Smoke Test Guide

This document provides a quick smoke test suite to verify that Xyn Seed v0.0 is working correctly.

## Prerequisites

1. Xyn Seed platform is running via `./xynctl start`
2. Platform should be accessible at `http://localhost:8000`

## Smoke Tests

### 1. Health Check (API)

Verify the API is responding:

```bash
curl http://localhost:8000/api/v1/health
```

**Expected output:**
```json
{
  "status": "ok",
  "version": "0.0.1",
  "uptime_seconds": <number>,
  "now": "<timestamp>"
}
```

**URL to click:** http://localhost:8000/api/v1/health

---

### 2. View Event Console (UI)

Open the event console in your browser:

**URL to click:** http://localhost:8000/ui/events

**Expected:** You should see the Event Console page, initially empty or with system events.

---

### 3. Create a Run (UI)

Navigate to the run creation page:

**URL to click:** http://localhost:8000/ui/runs/new

Then:
1. Enter a run name (e.g., "Test Run 1")
2. Leave inputs as `{}`
3. Do NOT check "Simulate failure"
4. Click "Create & Execute Run"

**Expected:** You should be redirected to a run detail page showing:
- Run status: "completed" (green badge)
- 2 steps: "Initialize" and "Process"
- Both steps should show "completed" status
- Events section showing run lifecycle events

---

### 4. Create a Run via API

Create a run programmatically:

```bash
curl -X POST http://localhost:8000/api/v1/runs \
  -H "Content-Type: application/json" \
  -d '{
    "name": "API Test Run",
    "inputs": {"test_key": "test_value"}
  }'
```

**Expected output:**
```json
{
  "run_id": "<uuid>",
  "name": "API Test Run",
  "status": "created",
  "actor": "user",
  ...
}
```

Copy the `run_id` from the response for the next test.

---

### 5. View Run Details (UI)

Using the run_id from step 4, view the run:

**URL to click:** http://localhost:8000/ui/runs/`<run_id>`

Replace `<run_id>` with the actual UUID from step 4.

**Expected:** Run detail page showing status, steps, and events.

---

### 6. List All Runs (API)

Retrieve all runs:

```bash
curl http://localhost:8000/api/v1/runs
```

**Expected output:**
```json
{
  "items": [
    {
      "run_id": "<uuid>",
      "name": "...",
      "status": "...",
      ...
    },
    ...
  ],
  "next_cursor": null
}
```

---

### 7. Emit a Failure Event (UI)

Create a run that simulates failure:

**URL to click:** http://localhost:8000/ui/runs/new

Then:
1. Enter a run name (e.g., "Failure Test")
2. Leave inputs as `{}`
3. **CHECK** "Simulate failure"
4. Click "Create & Execute Run"

**Expected:** You should see:
- Run status: "failed" (red badge)
- Step 1 "Initialize": completed
- Step 2 "Process (will fail)": failed (red badge)
- Error message in the run error section
- Event console shows `xyn.run.failed` event

---

### 8. View Event Console After Activity (UI)

Return to the event console:

**URL to click:** http://localhost:8000/ui/events

**Expected:** You should now see multiple events including:
- `xyn.run.created`
- `xyn.run.started`
- `xyn.run.completed`
- `xyn.run.failed` (from the failure test)
- `xyn.step.started`
- `xyn.step.completed`
- `xyn.step.failed`

---

### 9. Filter Events by Type (UI)

On the events page, use the dropdown to filter by event type:

**URL to click:** http://localhost:8000/ui/events?event_name=xyn.run.failed

**Expected:** Only failure events should be displayed.

---

### 10. View All Runs (UI)

View the runs list page:

**URL to click:** http://localhost:8000/ui/runs

**Expected:** You should see all the runs you created, with their statuses clearly indicated by color-coded badges.

---

## Quick Test Script

Run all API tests at once:

```bash
#!/bin/bash

echo "=== Xyn Seed v0.0 Smoke Tests ==="
echo

echo "1. Health Check..."
curl -s http://localhost:8000/api/v1/health | jq .
echo

echo "2. Create Run (Success)..."
RUN_ID=$(curl -s -X POST http://localhost:8000/api/v1/runs \
  -H "Content-Type: application/json" \
  -d '{"name": "Smoke Test Success", "inputs": {}}' | jq -r '.run_id')
echo "Created run: $RUN_ID"
echo

echo "3. Wait for run to complete..."
sleep 2
echo

echo "4. Get Run Details..."
curl -s http://localhost:8000/api/v1/runs/$RUN_ID | jq .
echo

echo "5. List Events..."
curl -s http://localhost:8000/api/v1/events?limit=10 | jq '.items | length'
echo "events found"
echo

echo "6. List All Runs..."
curl -s http://localhost:8000/api/v1/runs?limit=10 | jq '.items | length'
echo "runs found"
echo

echo "=== Smoke Tests Complete ==="
echo
echo "Visit http://localhost:8000/ui/events to see the event console"
echo "Visit http://localhost:8000/ui/runs to see all runs"
```

Save this as `smoke_test.sh`, make it executable (`chmod +x smoke_test.sh`), and run it:

```bash
./smoke_test.sh
```

---

## Summary of URLs to Click

1. **Health Check:** http://localhost:8000/api/v1/health
2. **Event Console:** http://localhost:8000/ui/events
3. **Runs List:** http://localhost:8000/ui/runs
4. **Create New Run:** http://localhost:8000/ui/runs/new
5. **Artifacts Browser:** http://localhost:8000/ui/artifacts
6. **Root (redirects to events):** http://localhost:8000/

---

## Troubleshooting

If tests fail:

1. **Check services are running:**
   ```bash
   docker compose ps
   ```
   All services should show "Up" status.

2. **Check logs:**
   ```bash
   ./xynctl logs core
   ```

3. **Restart platform:**
   ```bash
   ./xynctl stop
   ./xynctl start
   ```

4. **Verify database:**
   ```bash
   docker compose exec postgres psql -U xyn -d xyn -c "\dt"
   ```
   You should see tables: events, runs, steps, artifacts, blueprints, drafts, nodes.
