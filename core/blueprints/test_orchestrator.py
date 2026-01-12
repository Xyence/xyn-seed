"""Test orchestrator blueprints for validating DAG execution."""
import asyncio
import time
from typing import Dict, Any
from core.blueprints.registry import register_blueprint
from core.blueprints.runner import RunContext


@register_blueprint("core.test.sleep@v1")
async def test_sleep(ctx: RunContext, inputs: Dict[str, Any]) -> Dict[str, Any]:
    """Sleep for specified milliseconds, optionally fail.

    Inputs:
        ms: Milliseconds to sleep (default: 100)
        fail: Whether to raise exception after sleep (default: False)

    Returns:
        slept_ms: Actual milliseconds slept
        timestamp: Completion timestamp
    """
    ms = inputs.get("ms", 100)
    fail = inputs.get("fail", False)

    with ctx.step(f"Sleeping for {ms}ms", kind="agent_task"):
        await asyncio.sleep(ms / 1000.0)
        ctx.emit_progress(f"Slept for {ms}ms")

        if fail:
            raise Exception(f"Intentional failure after {ms}ms sleep")

    return {
        "slept_ms": ms,
        "timestamp": time.time(),
        "failed": False
    }


@register_blueprint("core.test.echo@v1")
async def test_echo(ctx: RunContext, inputs: Dict[str, Any]) -> Dict[str, Any]:
    """Echo inputs as outputs (useful for validating JSON payload behavior).

    Returns:
        All inputs echoed back plus metadata
    """
    with ctx.step("Echoing inputs", kind="agent_task"):
        ctx.emit_progress("Echoing inputs back")

    return {
        "echo": inputs,
        "timestamp": time.time()
    }


@register_blueprint("core.test.orchestrator@v1")
async def test_orchestrator(ctx: RunContext, inputs: Dict[str, Any]) -> Dict[str, Any]:
    """Test orchestrator for validating spawn/wait behavior.

    Inputs:
        mode: Wait policy - "all" or "any" (default: "all")
        children: List of child specs:
            [{"ref": "blueprint@v1", "inputs": {...}, "child_key": "key"}]
        fail_child_key: Optional child_key to force failure (default: None)
        parallel: True = spawn all then wait, False = sequential (default: True)

    Returns:
        child_run_ids: List of spawned child run IDs
        completed: List of completed child run IDs
        failed: List of failed child run IDs
        policy: Wait policy used
        elapsed_ms: Elapsed time in milliseconds
    """
    mode = inputs.get("mode", "all")
    children_specs = inputs.get("children", [])
    fail_child_key = inputs.get("fail_child_key")
    parallel = inputs.get("parallel", True)

    start_time = time.time()
    child_run_ids = []

    if parallel:
        # Parallel mode: spawn all children, then wait
        with ctx.step(f"Spawning {len(children_specs)} children in parallel", kind="agent_task"):
            for spec in children_specs:
                ref = spec["ref"]
                child_inputs = spec.get("inputs", {})
                child_key = spec.get("child_key")

                # Poison this child if requested
                if child_key == fail_child_key:
                    child_inputs["fail"] = True

                child_id = ctx.spawn_run(ref, child_inputs, child_key=child_key)
                child_run_ids.append(child_id)
                ctx.emit_progress(f"Spawned {child_key}: {child_id}")

        # Wait for all/any
        with ctx.step(f"Waiting for children (policy={mode})", kind="agent_task"):
            result = await ctx.wait_runs(child_run_ids, policy=mode)
    else:
        # Sequential mode: spawn and wait for each child
        for i, spec in enumerate(children_specs):
            ref = spec["ref"]
            child_inputs = spec.get("inputs", {})
            child_key = spec.get("child_key")

            # Poison this child if requested
            if child_key == fail_child_key:
                child_inputs["fail"] = True

            with ctx.step(f"Sequential step {i+1}: {child_key}", kind="agent_task"):
                child_id = ctx.spawn_run(ref, child_inputs, child_key=child_key)
                child_run_ids.append(child_id)
                ctx.emit_progress(f"Spawned {child_key}: {child_id}")

                # Wait for this child before proceeding
                result = await ctx.wait_runs([child_id], policy="all")
                ctx.emit_progress(f"Completed {child_key}")

        # Final result aggregation for sequential
        result = {
            "completed": [str(id) for id in child_run_ids],
            "failed": [],
            "policy_met": True
        }

    elapsed_ms = int((time.time() - start_time) * 1000)

    return {
        "child_run_ids": [str(id) for id in child_run_ids],
        "completed": result.get("completed", []),
        "failed": result.get("failed", []),
        "policy": mode,
        "elapsed_ms": elapsed_ms,
        "parallel": parallel
    }
