import json
import shutil
import subprocess
import tempfile
import time
import uuid
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest import mock

from core import models
from core.codex_executor import CodexExecutionResult, ValidationResult
from core.database import SessionLocal
from core.runtime_contract import RunPayloadV1
from core.runtime_execution import create_runtime_run
from core.runtime_loop import start_runtime_worker_loop, stop_runtime_worker_loop


class _LoopFakeCodexExecutor:
    def execute(self, *, repo_path: Path, prompt_title: str, prompt_body: str, timeout_seconds):
        (repo_path / "runtime_loop.txt").write_text("runtime loop update\n", encoding="utf-8")
        return CodexExecutionResult(summary_text="loop completed", log_text="loop log", exit_code=0)


class _LoopFakeValidationRunner:
    def run(self, *, repo_path: Path, timeout_seconds):
        return ValidationResult(success=True, summary="Validation succeeded.", log_text="", report_payload={"tests": 1})


class RuntimeWorkerLoopTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fixture_path = Path(__file__).resolve().parent / "fixtures" / "run_payload_v1.json"
        cls.fixture = json.loads(fixture_path.read_text(encoding="utf-8"))

    def setUp(self):
        self.db = SessionLocal()
        self.run_ids = []
        self.worker_ids = []
        self.tempdirs = []
        self.handles = []
        self.preexisting_workers = {
            row.worker_id: {
                "status": row.status,
                "active_run_id": row.active_run_id,
                "last_heartbeat": row.last_heartbeat,
            }
            for row in self.db.query(models.RuntimeWorker).all()
        }
        if self.preexisting_workers:
            self.db.query(models.RuntimeWorker).update(
                {
                    models.RuntimeWorker.status: models.RuntimeWorkerStatus.OFFLINE,
                    models.RuntimeWorker.active_run_id: None,
                },
                synchronize_session=False,
            )
            self.db.commit()

    def tearDown(self):
        for handle in self.handles:
            stop_runtime_worker_loop(handle)
        if self.run_ids:
            self.db.query(models.RuntimeWorker).filter(models.RuntimeWorker.active_run_id.in_(self.run_ids)).update(
                {models.RuntimeWorker.active_run_id: None},
                synchronize_session=False,
            )
        if self.worker_ids:
            self.db.query(models.RuntimeWorker).filter(models.RuntimeWorker.worker_id.in_(self.worker_ids)).delete(synchronize_session=False)
        if self.run_ids:
            self.db.query(models.Event).filter(models.Event.run_id.in_(self.run_ids)).delete(synchronize_session=False)
            self.db.query(models.Artifact).filter(models.Artifact.run_id.in_(self.run_ids)).delete(synchronize_session=False)
            self.db.query(models.Step).filter(models.Step.run_id.in_(self.run_ids)).delete(synchronize_session=False)
            self.db.query(models.Run).filter(models.Run.id.in_(self.run_ids)).delete(synchronize_session=False)
        for worker_id, state in self.preexisting_workers.items():
            self.db.query(models.RuntimeWorker).filter(models.RuntimeWorker.worker_id == worker_id).update(
                {
                    models.RuntimeWorker.status: state["status"],
                    models.RuntimeWorker.active_run_id: state["active_run_id"],
                    models.RuntimeWorker.last_heartbeat: state["last_heartbeat"],
                },
                synchronize_session=False,
            )
        self.db.commit()
        self.db.close()
        runtime_root = Path(".xyn/workspace/runtime_runs").resolve()
        for run_id in self.run_ids:
            shutil.rmtree(runtime_root / str(run_id), ignore_errors=True)
        for tmpdir in self.tempdirs:
            shutil.rmtree(tmpdir, ignore_errors=True)

    def _temp_repo(self) -> Path:
        tmpdir = tempfile.mkdtemp(prefix="runtime-loop-")
        self.tempdirs.append(tmpdir)
        repo_path = Path(tmpdir)
        subprocess.run(["git", "init", "-b", "main"], cwd=tmpdir, check=True, capture_output=True, text=True)
        subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=tmpdir, check=True)
        subprocess.run(["git", "config", "user.name", "Test User"], cwd=tmpdir, check=True)
        (repo_path / "README.md").write_text("initial\n", encoding="utf-8")
        subprocess.run(["git", "add", "README.md"], cwd=tmpdir, check=True)
        subprocess.run(["git", "commit", "-m", "initial"], cwd=tmpdir, check=True, capture_output=True, text=True)
        return repo_path

    def _payload(self, repo_path: str) -> RunPayloadV1:
        payload = dict(self.fixture)
        payload["run_id"] = str(uuid.uuid4())
        payload["work_item_id"] = f"wi-{uuid.uuid4()}"
        payload["target"] = dict(payload["target"])
        payload["target"]["repo"] = repo_path
        payload["target"]["branch"] = "main"
        return RunPayloadV1.model_validate(payload)

    def test_background_loop_picks_up_and_executes_queued_run(self):
        repo = self._temp_repo()
        run = create_runtime_run(self.db, self._payload(str(repo)))
        run.priority = -1000
        self.run_ids.append(run.id)
        self.db.commit()

        handle = start_runtime_worker_loop(
            worker_id=f"loop-worker-{uuid.uuid4()}",
            poll_interval_seconds=0.1,
            executor_factory=lambda: _LoopFakeCodexExecutor(),
            validation_runner_factory=lambda: _LoopFakeValidationRunner(),
        )
        self.handles.append(handle)
        self.worker_ids.append(handle.worker_id)

        deadline = time.time() + 5
        while time.time() < deadline:
            self.db.expire_all()
            refreshed = self.db.query(models.Run).filter(models.Run.id == run.id).one()
            if refreshed.status == models.RunStatus.COMPLETED:
                break
            time.sleep(0.1)
        self.db.refresh(run)
        self.assertEqual(run.status, models.RunStatus.COMPLETED)
        self.assertEqual(run.worker_id, handle.worker_id)
        event_names = [event.event_name for event in self.db.query(models.Event).filter(models.Event.run_id == run.id).all()]
        self.assertIn("run.completed", event_names)

    def test_background_loop_monitors_stale_running_runs(self):
        run = create_runtime_run(self.db, self._payload("/tmp/does-not-matter"))
        run.status = models.RunStatus.RUNNING
        run.worker_id = "missing-worker"
        run.started_at = datetime.utcnow() - timedelta(minutes=2)
        run.heartbeat_at = datetime.utcnow() - timedelta(minutes=2)
        run.execution_policy = {"max_retries": 0, "require_human_review_on_failure": False}
        self.run_ids.append(run.id)
        self.db.commit()

        handle = start_runtime_worker_loop(
            worker_id=f"loop-worker-{uuid.uuid4()}",
            poll_interval_seconds=0.1,
            executor_factory=lambda: _LoopFakeCodexExecutor(),
            validation_runner_factory=lambda: _LoopFakeValidationRunner(),
        )
        self.handles.append(handle)
        self.worker_ids.append(handle.worker_id)

        deadline = time.time() + 3
        while time.time() < deadline:
            self.db.expire_all()
            refreshed = self.db.query(models.Run).filter(models.Run.id == run.id).one()
            if refreshed.status == models.RunStatus.FAILED:
                break
            time.sleep(0.1)
        self.db.refresh(run)
        self.assertEqual(run.status, models.RunStatus.FAILED)
        self.assertEqual(run.failure_reason, "worker_unresponsive")

    def test_background_loop_stays_stable_when_codex_missing(self):
        handle = None
        with mock.patch("core.codex_local_worker.check_codex_availability") as availability:
            availability.return_value.available = False
            availability.return_value.reason = "codex executable not found"
            handle = start_runtime_worker_loop(
                worker_id=f"loop-worker-{uuid.uuid4()}",
                poll_interval_seconds=0.1,
            )
            self.handles.append(handle)
            self.worker_ids.append(handle.worker_id)
            time.sleep(0.25)
        worker = self.db.query(models.RuntimeWorker).filter(models.RuntimeWorker.worker_id == handle.worker_id).one()
        self.assertEqual(worker.status, models.RuntimeWorkerStatus.OFFLINE)


if __name__ == "__main__":
    unittest.main()
