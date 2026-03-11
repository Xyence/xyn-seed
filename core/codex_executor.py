"""Local Codex execution and validation adapters for Epic C."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional, Protocol


class CodexExecutionError(RuntimeError):
    """Codex execution failed."""


class CodexTimeoutError(CodexExecutionError):
    """Codex execution exceeded the configured timeout."""


@dataclass
class CodexExecutionResult:
    summary_text: str
    log_text: str
    exit_code: int


@dataclass
class ValidationResult:
    success: bool
    summary: str
    log_text: str
    report_payload: Optional[dict[str, Any]] = None
    skipped: bool = False


@dataclass
class CodexAvailability:
    available: bool
    binary: str
    reason: Optional[str] = None


class CodexExecutor(Protocol):
    def execute(
        self,
        *,
        repo_path: Path,
        prompt_title: str,
        prompt_body: str,
        timeout_seconds: Optional[int],
    ) -> CodexExecutionResult:
        ...


class ValidationRunner(Protocol):
    def run(
        self,
        *,
        repo_path: Path,
        timeout_seconds: Optional[int],
    ) -> ValidationResult:
        ...


class CliCodexExecutor:
    """Shell adapter around the installed Codex CLI."""

    def __init__(self, binary: Optional[str] = None):
        self.binary = binary or os.getenv("XYN_CODEX_BINARY") or shutil.which("codex") or "codex"

    def availability(self) -> CodexAvailability:
        return check_codex_availability(self.binary)

    def execute(
        self,
        *,
        repo_path: Path,
        prompt_title: str,
        prompt_body: str,
        timeout_seconds: Optional[int],
    ) -> CodexExecutionResult:
        with tempfile.NamedTemporaryFile("w+", suffix=".txt", delete=False) as summary_file:
            summary_path = Path(summary_file.name)
        prompt = f"{prompt_title.strip()}\n\n{prompt_body.strip()}".strip()
        cmd = [
            self.binary,
            "-a",
            "never",
            "-s",
            "workspace-write",
            "exec",
            "-C",
            str(repo_path),
            "--json",
            "--output-last-message",
            str(summary_path),
        ]
        try:
            proc = subprocess.run(
                cmd,
                input=prompt,
                text=True,
                capture_output=True,
                check=False,
                timeout=timeout_seconds,
            )
        except subprocess.TimeoutExpired as exc:
            stdout = exc.stdout or ""
            stderr = exc.stderr or ""
            raise CodexTimeoutError(f"Codex execution timed out after {timeout_seconds}s.\n{stdout}\n{stderr}".strip())
        finally:
            summary_text = summary_path.read_text(encoding="utf-8").strip() if summary_path.exists() else ""
            try:
                summary_path.unlink(missing_ok=True)
            except TypeError:
                if summary_path.exists():
                    summary_path.unlink()
        log_text = "\n".join(part for part in [(proc.stdout or "").strip(), (proc.stderr or "").strip()] if part).strip()
        if proc.returncode != 0:
            raise CodexExecutionError(summary_text or log_text or f"Codex exited with status {proc.returncode}")
        return CodexExecutionResult(
            summary_text=summary_text or "Codex execution completed.",
            log_text=log_text,
            exit_code=proc.returncode,
        )


def check_codex_availability(binary: Optional[str] = None) -> CodexAvailability:
    resolved = binary or os.getenv("XYN_CODEX_BINARY") or shutil.which("codex") or "codex"
    binary_path = shutil.which(resolved) if os.path.sep not in resolved else resolved
    if not binary_path:
        return CodexAvailability(available=False, binary=resolved, reason="codex executable not found in PATH")
    try:
        proc = subprocess.run(
            [binary_path, "--help"],
            text=True,
            capture_output=True,
            check=False,
            timeout=5,
        )
    except subprocess.TimeoutExpired:
        return CodexAvailability(available=False, binary=binary_path, reason="codex --help timed out")
    except OSError as exc:
        return CodexAvailability(available=False, binary=binary_path, reason=str(exc))
    if proc.returncode != 0:
        output = "\n".join(part for part in [(proc.stdout or "").strip(), (proc.stderr or "").strip()] if part).strip()
        return CodexAvailability(
            available=False,
            binary=binary_path,
            reason=output or f"codex --help exited with status {proc.returncode}",
        )
    return CodexAvailability(available=True, binary=binary_path)


class LocalValidationRunner:
    """Best-effort deterministic validation runner for local repos."""

    def run(
        self,
        *,
        repo_path: Path,
        timeout_seconds: Optional[int],
    ) -> ValidationResult:
        cmd = self._resolve_command(repo_path)
        if not cmd:
            return ValidationResult(
                success=True,
                summary="Validation skipped: no deterministic test command available.",
                log_text="",
                skipped=True,
            )
        try:
            proc = subprocess.run(
                cmd,
                cwd=str(repo_path),
                text=True,
                capture_output=True,
                check=False,
                timeout=timeout_seconds,
            )
        except subprocess.TimeoutExpired:
            return ValidationResult(
                success=False,
                summary=f"Validation timed out after {timeout_seconds}s.",
                log_text="",
                report_payload={"command": cmd, "timed_out": True},
            )
        log_text = "\n".join(part for part in [(proc.stdout or "").strip(), (proc.stderr or "").strip()] if part).strip()
        return ValidationResult(
            success=proc.returncode == 0,
            summary="Validation succeeded." if proc.returncode == 0 else f"Validation failed with exit code {proc.returncode}.",
            log_text=log_text,
            report_payload={"command": cmd, "exit_code": proc.returncode},
        )

    def _resolve_command(self, repo_path: Path) -> list[str] | None:
        if (repo_path / "pytest.ini").exists() or (repo_path / "pyproject.toml").exists():
            return ["python", "-m", "pytest", "-q"]
        if (repo_path / "manage.py").exists():
            return ["python", "manage.py", "test"]
        if (repo_path / "core" / "tests").exists() or (repo_path / "tests").exists():
            return ["python", "-m", "unittest"]
        package_json = repo_path / "package.json"
        if package_json.exists():
            try:
                payload = json.loads(package_json.read_text(encoding="utf-8"))
            except Exception:
                payload = {}
            scripts = payload.get("scripts") if isinstance(payload, dict) else {}
            if isinstance(scripts, dict) and scripts.get("test"):
                return ["npm", "test", "--", "--runInBand"]
        return None
