#!/usr/bin/env python3
"""Test scenarios for orchestrator spawn/wait behavior."""
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import time
import json
from core.database import SessionLocal
from core.blueprints.runner import enqueue_run
from core import models


def enqueue_orchestrator(scenario_name, inputs):
    """Enqueue an orchestrator test run."""
    print(f"\n{'='*60}")
    print(f"SCENARIO: {scenario_name}")
    print(f"{'='*60}")
    print(f"Inputs: {json.dumps(inputs, indent=2)}")

    db = SessionLocal()
    try:
        run = enqueue_run(
            blueprint_ref="core.test.orchestrator@v1",
            inputs=inputs,
            db=db,
            actor="test-script"
        )
        run_id = str(run.id)
        print(f"Enqueued run: {run_id}")
        return run_id
    finally:
        db.close()


def wait_for_run(run_id, timeout=30):
    """Poll until run completes or times out."""
    start = time.time()
    import uuid

    db = SessionLocal()
    try:
        run_uuid = uuid.UUID(run_id)

        while time.time() - start < timeout:
            run = db.query(models.Run).filter(models.Run.id == run_uuid).first()
            if not run:
                print(f"ERROR: Run {run_id} not found")
                return None

            status = run.status.value

            if status in ["completed", "failed", "cancelled"]:
                print(f"\nRun {run_id} finished: {status}")
                if status == "completed":
                    print(f"Outputs: {json.dumps(run.outputs, indent=2)}")
                elif status == "failed":
                    print(f"Error: {json.dumps(run.error, indent=2)}")
                return {
                    "run_id": str(run.id),
                    "status": status,
                    "outputs": run.outputs,
                    "error": run.error
                }

            print(f"Status: {status} (elapsed: {int(time.time() - start)}s)")
            time.sleep(2)

        print(f"TIMEOUT waiting for run {run_id}")
        return None
    finally:
        db.close()


def scenario_1_parallel_all_success():
    """Scenario 1: parallel all success - 2 children sleep 300ms and 700ms."""
    inputs = {
        "mode": "all",
        "children": [
            {"ref": "core.test.sleep@v1", "inputs": {"ms": 300}, "child_key": "sleep-1"},
            {"ref": "core.test.sleep@v1", "inputs": {"ms": 700}, "child_key": "sleep-2"}
        ],
        "parallel": True
    }

    run_id = enqueue_orchestrator("Parallel All Success", inputs)
    if run_id:
        result = wait_for_run(run_id)
        if result and result["status"] == "completed":
            print("✅ PASS: Both children completed successfully")
        else:
            print("❌ FAIL: Expected completed status")


def scenario_2_one_child_fails():
    """Scenario 2: one child fails with policy=all - sleep-2 fails."""
    inputs = {
        "mode": "all",
        "children": [
            {"ref": "core.test.sleep@v1", "inputs": {"ms": 300}, "child_key": "sleep-1"},
            {"ref": "core.test.sleep@v1", "inputs": {"ms": 700}, "child_key": "sleep-2"}
        ],
        "fail_child_key": "sleep-2",
        "parallel": True
    }

    run_id = enqueue_orchestrator("One Child Fails (policy=all)", inputs)
    if run_id:
        result = wait_for_run(run_id)
        if result and result["status"] == "failed":
            print("✅ PASS: Parent failed when child failed (policy=all)")
        else:
            print("❌ FAIL: Expected failed status")


def scenario_3_policy_any():
    """Scenario 3: policy=any - one sleeps 100ms, one 2000ms."""
    inputs = {
        "mode": "any",
        "children": [
            {"ref": "core.test.sleep@v1", "inputs": {"ms": 100}, "child_key": "fast"},
            {"ref": "core.test.sleep@v1", "inputs": {"ms": 2000}, "child_key": "slow"}
        ],
        "parallel": True
    }

    run_id = enqueue_orchestrator("Policy Any (first wins)", inputs)
    if run_id:
        result = wait_for_run(run_id, timeout=15)
        if result and result["status"] == "completed":
            outputs = result.get("outputs", {})
            elapsed = outputs.get("elapsed_ms", 0)
            if elapsed < 1500:  # Should complete after fast child (~100ms), not slow (2000ms)
                print(f"✅ PASS: Completed after first child (elapsed: {elapsed}ms)")
            else:
                print(f"❌ FAIL: Took too long (elapsed: {elapsed}ms), should complete after fast child")
        else:
            print("❌ FAIL: Expected completed status")


def scenario_4_resume_test():
    """Scenario 4: resume test - verify idempotent spawning."""
    print("\n⚠️  Scenario 4 (Resume Test) requires manual worker restart")
    print("Steps:")
    print("1. Start orchestrator with long-running children")
    print("2. Kill worker mid-wait")
    print("3. Restart worker")
    print("4. Verify parent resumes without duplicate spawns")
    print("\nThis would be a manual/integration test, skipping for now.")


if __name__ == "__main__":
    print("Testing Orchestrator Spawn/Wait Behavior")
    print("=" * 60)

    try:
        scenario_1_parallel_all_success()
        time.sleep(2)

        scenario_2_one_child_fails()
        time.sleep(2)

        scenario_3_policy_any()
        time.sleep(2)

        scenario_4_resume_test()

        print("\n" + "=" * 60)
        print("Test suite completed")
        print("=" * 60)

    except KeyboardInterrupt:
        print("\nTests interrupted")
    except Exception as e:
        print(f"\nError running tests: {e}")
        import traceback
        traceback.print_exc()
