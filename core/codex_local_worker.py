"""codex_local worker implementation for Epic C."""

from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional

from sqlalchemy.orm import Session

from core import models
from core.codex_executor import (
    CliCodexExecutor,
    check_codex_availability,
    CodexExecutionError,
    CodexExecutionResult,
    CodexExecutor,
    CodexTimeoutError,
    LocalValidationRunner,
    ValidationResult,
    ValidationRunner,
)
from core.repo_resolver import RepoResolutionBlocked, RepoResolutionFailed, resolve_runtime_repo
from core.runtime_contract import CODEX_LOCAL_CAPABILITIES, RunPayloadV1, WorkerInfoPayload
from core.runtime_events import publish_runtime_event
from core.runtime_execution import (
    capture_run_artifact,
    complete_run,
    record_run_heartbeat,
    report_run_step,
)
from core.runtime_workers import mark_worker_idle, register_worker


INSPECT_STEP = ("inspect_repository", "Inspect repository")
PREPARE_STEP = ("prepare_context", "Prepare execution context")
EXECUTE_STEP = ("execute_codex", "Execute Codex task")
VALIDATE_STEP = ("validate_results", "Validate results")
FINALIZE_STEP = ("finalize_outputs", "Finalize outputs")


def register_codex_local_worker(db: Session, *, worker_id: Optional[str] = None) -> models.RuntimeWorker:
    resolved_id = worker_id or f"codex-local-{os.getpid()}"
    availability = check_codex_availability()
    return register_worker(
        db,
        WorkerInfoPayload(
            worker_id=resolved_id,
            worker_type="codex_local",
            runtime_environment="local_process",
            status="idle" if availability.available else "offline",
            last_heartbeat=datetime.utcnow(),
            capabilities=CODEX_LOCAL_CAPABILITIES,
        ),
    )


def execute_codex_local_run(
    db: Session,
    *,
    run_id,
    worker_id: str,
    executor: Optional[CodexExecutor] = None,
    validation_runner: Optional[ValidationRunner] = None,
) -> models.Run:
    run = db.query(models.Run).filter(models.Run.id == run_id).one()
    payload = RunPayloadV1.model_validate(run.prompt_payload or {})
    _ensure_assigned_run(run, worker_id)
    executor = executor or CliCodexExecutor()
    validation_runner = validation_runner or LocalValidationRunner()
    if isinstance(executor, CliCodexExecutor):
        availability = executor.availability()
        if not availability.available:
            return _handle_failure(
                db,
                run_id=run.id,
                worker_id=worker_id,
                summary=availability.reason or "codex unavailable",
                failure_reason="worker_crashed",
                log_text=availability.reason or "",
            )

    try:
        repo_path = _run_inspect_repository_step(db, run, worker_id, payload)
        execution_prompt = _run_prepare_context_step(db, run, worker_id, payload, repo_path)
        codex_result = _run_execute_codex_step(db, run, worker_id, payload, repo_path, execution_prompt, executor)
        validation_result = _run_validation_step(db, run, worker_id, payload, repo_path, validation_runner)
        _run_finalize_outputs_step(db, run, worker_id, payload, repo_path, codex_result, validation_result)
        db.commit()
        return run
    except _BlockedRun as blocked:
        db.rollback()
        return _mark_blocked(db, run_id=run.id, worker_id=worker_id, summary=blocked.summary, escalation_reason=blocked.escalation_reason)
    except _FailedRun as failed:
        db.rollback()
        return _handle_failure(
            db,
            run_id=run.id,
            worker_id=worker_id,
            summary=failed.summary,
            failure_reason=failed.failure_reason,
            log_text=failed.summary,
        )
    except CodexTimeoutError as exc:
        db.rollback()
        return _handle_failure(
            db,
            run_id=run.id,
            worker_id=worker_id,
            summary=str(exc),
            failure_reason="timeout_exceeded",
            log_text=str(exc),
        )
    except Exception as exc:
        db.rollback()
        return _handle_failure(
            db,
            run_id=run.id,
            worker_id=worker_id,
            summary=str(exc),
            failure_reason="unexpected_error",
            log_text=str(exc),
        )


def should_run_validation(payload: RunPayloadV1) -> bool:
    text = f"{payload.prompt.title} {payload.prompt.body}".lower()
    return (
        "report" in payload.requested_outputs
        or any(token in text for token in ("test", "tests", "validate", "validation"))
        or bool(payload.policy.auto_continue)
    )


def resolve_target_repo(payload: RunPayloadV1) -> Path:
    repo_ref = str(payload.target.repo or "").strip()
    try:
        return resolve_runtime_repo(repo_ref).path
    except RepoResolutionBlocked as exc:
        raise _BlockedRun(str(exc), str(exc.escalation_reason or "target_repo_ambiguous"))
    except RepoResolutionFailed as exc:
        raise _FailedRun(str(exc), str(exc.failure_reason or "repo_unreachable"))


def _ensure_assigned_run(run: models.Run, worker_id: str) -> None:
    if run.status != models.RunStatus.RUNNING or run.worker_id != worker_id:
        raise RuntimeError(f"run {run.id} is not assigned to worker {worker_id}")


def _run_inspect_repository_step(db: Session, run: models.Run, worker_id: str, payload: RunPayloadV1) -> Path:
    step = _start_step(db, run, worker_id, *INSPECT_STEP, sequence_no=1)
    try:
        repo_path = resolve_target_repo(payload)
        current_branch = _git_stdout(repo_path, ["git", "branch", "--show-current"]).strip()
        expected_branch = str(payload.target.branch or "").strip()
        if expected_branch and current_branch != expected_branch:
            raise _BlockedRun(
                f"Target branch '{expected_branch}' is not checked out in {repo_path.name} (current: {current_branch or 'detached'}).",
                "target_branch_mismatch",
            )
        dirty = _git_stdout(repo_path, ["git", "status", "--porcelain"]).strip()
        if dirty:
            raise _BlockedRun(
                f"Repository '{repo_path.name}' has uncommitted changes; refusing to capture an unsafe patch baseline.",
                "unsafe_repository_state",
            )
        _complete_step(db, run, worker_id, step, summary=f"Using repo {repo_path} on branch {current_branch or '<detached>'}.")
        return repo_path
    except _FailedRun:
        _fail_step(db, run, worker_id, step, "Repository resolution failed.")
        raise
    except Exception as exc:
        _fail_step(db, run, worker_id, step, str(exc))
        raise


def _run_prepare_context_step(
    db: Session,
    run: models.Run,
    worker_id: str,
    payload: RunPayloadV1,
    repo_path: Path,
) -> str:
    step = _start_step(db, run, worker_id, *PREPARE_STEP, sequence_no=2)
    try:
        attachments = payload.context.attachments or []
        attachment_lines = "\n".join(
            f"- {item.kind}: {item.uri}{f' ({item.label})' if item.label else ''}" for item in attachments
        )
        requested_outputs = ", ".join(payload.requested_outputs)
        execution_prompt = (
            f"{payload.prompt.title}\n\n"
            f"{payload.prompt.body}\n\n"
            f"Target repo: {repo_path}\n"
            f"Requested outputs: {requested_outputs}\n"
            f"Work item: {payload.work_item_id}\n"
            f"Attachments:\n{attachment_lines or '- none'}\n"
            f"Return a concise summary of changes and validation."
        )
        _complete_step(db, run, worker_id, step, summary="Execution context prepared.")
        return execution_prompt
    except Exception as exc:
        _fail_step(db, run, worker_id, step, str(exc))
        raise


def _run_execute_codex_step(
    db: Session,
    run: models.Run,
    worker_id: str,
    payload: RunPayloadV1,
    repo_path: Path,
    execution_prompt: str,
    executor: CodexExecutor,
) -> CodexExecutionResult:
    step = _start_step(db, run, worker_id, *EXECUTE_STEP, sequence_no=3)
    try:
        result = executor.execute(
            repo_path=repo_path,
            prompt_title=payload.prompt.title,
            prompt_body=execution_prompt,
            timeout_seconds=payload.policy.timeout_seconds,
        )
    except Exception as exc:
        _fail_step(db, run, worker_id, step, str(exc))
        raise
    _complete_step(db, run, worker_id, step, summary=result.summary_text or "Codex execution completed.")
    return result


def _run_validation_step(
    db: Session,
    run: models.Run,
    worker_id: str,
    payload: RunPayloadV1,
    repo_path: Path,
    validation_runner: ValidationRunner,
) -> ValidationResult:
    step = _start_step(db, run, worker_id, *VALIDATE_STEP, sequence_no=4)
    try:
        if not should_run_validation(payload):
            result = ValidationResult(success=True, summary="Validation skipped by policy.", log_text="", skipped=True)
        else:
            result = validation_runner.run(repo_path=repo_path, timeout_seconds=payload.policy.timeout_seconds)
    except Exception as exc:
        _fail_step(db, run, worker_id, step, str(exc))
        raise
    if not result.success:
        _fail_step(db, run, worker_id, step, result.summary)
        raise CodexExecutionError(result.summary)
    _complete_step(db, run, worker_id, step, summary=result.summary)
    return result


def _run_finalize_outputs_step(
    db: Session,
    run: models.Run,
    worker_id: str,
    payload: RunPayloadV1,
    repo_path: Path,
    codex_result: CodexExecutionResult,
    validation_result: ValidationResult,
) -> None:
    step = _start_step(db, run, worker_id, *FINALIZE_STEP, sequence_no=5)
    patch_diff = _git_stdout(repo_path, ["git", "diff", "--binary"])
    if "patch" in payload.requested_outputs or patch_diff.strip():
        capture_run_artifact(
            db,
            run_id=run.id,
            artifact_type="patch",
            label="patch.diff",
            file_name="patch.diff",
            content=patch_diff,
            metadata_json={"repo": str(repo_path)},
        )
    capture_run_artifact(
        db,
        run_id=run.id,
        artifact_type="log",
        label="build_logs.txt",
        file_name="build_logs.txt",
        content=codex_result.log_text,
        metadata_json={"repo": str(repo_path)},
    )
    capture_run_artifact(
        db,
        run_id=run.id,
        artifact_type="summary",
        label="final_summary.md",
        file_name="final_summary.md",
        content=codex_result.summary_text,
        metadata_json={"repo": str(repo_path)},
    )
    if validation_result.report_payload:
        capture_run_artifact(
            db,
            run_id=run.id,
            artifact_type="report",
            label="test_report.json",
            file_name="test_report.json",
            content=validation_result.report_payload,
            metadata_json={"repo": str(repo_path), "skipped": validation_result.skipped},
        )
    _complete_step(db, run, worker_id, step, summary="Artifacts captured.")
    complete_run(db, run.id, summary=codex_result.summary_text)


def _handle_failure(
    db: Session,
    *,
    run_id,
    worker_id: str,
    summary: str,
    failure_reason: str,
    log_text: Optional[str] = None,
) -> models.Run:
    run = db.query(models.Run).filter(models.Run.id == run_id).one()
    policy = dict(run.execution_policy or {})
    max_retries = int(policy.get("max_retries") or 0)
    require_review = bool(policy.get("require_human_review_on_failure"))
    current_attempt = max(int(run.attempt_count or 0), 1)
    publish_runtime_event(
        db,
        event_name="run.failed",
        run_id=run.id,
        actor=worker_id,
        correlation_id=run.correlation_id,
        data={
            "summary": summary,
            "failure_reason": failure_reason,
            "retry_eligible": current_attempt <= max_retries,
        },
    )
    capture_run_artifact(
        db,
        run_id=run.id,
        artifact_type="summary",
        label="final_summary.md",
        file_name="final_summary.md",
        content=summary,
        metadata_json={"failure_reason": failure_reason},
    )
    capture_run_artifact(
        db,
        run_id=run.id,
        artifact_type="log",
        label="build_logs.txt",
        file_name="build_logs.txt",
        content=log_text or summary,
        metadata_json={"failure_reason": failure_reason},
    )
    if current_attempt <= max_retries:
        run.status = models.RunStatus.QUEUED
        run.summary = summary
        run.failure_reason = failure_reason
        run.queued_at = datetime.utcnow()
        run.heartbeat_at = None
        run.locked_by = None
        run.locked_at = None
        run.lease_expires_at = None
        mark_worker_idle(db, worker_id)
        db.commit()
        return run
    run.status = models.RunStatus.FAILED
    run.completed_at = datetime.utcnow()
    run.summary = summary
    run.failure_reason = failure_reason
    if require_review:
        run.escalation_reason = "human_review_required_after_failure"
    mark_worker_idle(db, worker_id)
    db.commit()
    return run


def _mark_blocked(
    db: Session,
    *,
    run_id,
    worker_id: str,
    summary: str,
    escalation_reason: str,
) -> models.Run:
    run = db.query(models.Run).filter(models.Run.id == run_id).one()
    run.status = models.RunStatus.BLOCKED
    run.completed_at = models.datetime.utcnow()
    run.summary = summary
    run.escalation_reason = escalation_reason
    mark_worker_idle(db, worker_id)
    publish_runtime_event(
        db,
        event_name="run.blocked",
        run_id=run.id,
        actor=worker_id,
        correlation_id=run.correlation_id,
        data={"summary": summary, "escalation_reason": escalation_reason},
    )
    db.commit()
    return run


def _start_step(db: Session, run: models.Run, worker_id: str, step_key: str, label: str, *, sequence_no: int) -> models.Step:
    record_run_heartbeat(db, worker_id, run.id)
    step = report_run_step(
        db,
        run_id=run.id,
        step_key=step_key,
        label=label,
        status="running",
        sequence_no=sequence_no,
        summary="started",
    )
    db.commit()
    return step


def _complete_step(db: Session, run: models.Run, worker_id: str, step: models.Step, *, summary: str) -> None:
    record_run_heartbeat(db, worker_id, run.id)
    report_run_step(
        db,
        run_id=run.id,
        step_key=str(step.step_key or step.name),
        label=str(step.label or step.name),
        status="completed",
        sequence_no=int(step.idx),
        summary=summary,
    )
    db.commit()


def _fail_step(db: Session, run: models.Run, worker_id: str, step: models.Step, summary: str) -> None:
    record_run_heartbeat(db, worker_id, run.id)
    report_run_step(
        db,
        run_id=run.id,
        step_key=str(step.step_key or step.name),
        label=str(step.label or step.name),
        status="failed",
        sequence_no=int(step.idx),
        summary=summary,
    )
    db.commit()


def _git_stdout(repo_path: Path, cmd: list[str]) -> str:
    proc = subprocess.run(
        cmd,
        cwd=str(repo_path),
        text=True,
        capture_output=True,
        check=False,
    )
    if proc.returncode != 0:
        raise _BlockedRun((proc.stderr or proc.stdout or "git command failed").strip(), "unexpected_environment_state")
    return (proc.stdout or "").strip()


@dataclass
class _BlockedRun(Exception):
    summary: str
    escalation_reason: str


@dataclass
class _FailedRun(Exception):
    summary: str
    failure_reason: str
