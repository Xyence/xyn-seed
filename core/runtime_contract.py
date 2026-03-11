"""Epic C runtime execution payloads and worker contracts."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Literal, Optional, Protocol

from pydantic import BaseModel, Field, field_validator


AllowedRequestedOutput = Literal["patch", "log", "report", "code", "summary"]
WorkerStatusLiteral = Literal["idle", "busy", "offline"]
RunStatusLiteral = Literal["queued", "running", "completed", "failed", "blocked"]
StepStatusLiteral = Literal["queued", "running", "completed", "failed"]


class RunTargetPayload(BaseModel):
    repo: str
    branch: Optional[str] = None
    workspace_id: Optional[str] = None
    artifact_id: Optional[str] = None


class RunPromptPayload(BaseModel):
    title: str
    body: str


class RunContextAttachmentPayload(BaseModel):
    kind: str
    uri: str
    label: Optional[str] = None


class RunContextPayload(BaseModel):
    epic_id: Optional[str] = None
    attachments: List[RunContextAttachmentPayload] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class RunPolicyPayload(BaseModel):
    auto_continue: bool
    max_retries: int = Field(ge=0)
    require_human_review_on_failure: bool
    timeout_seconds: Optional[int] = Field(default=None, ge=1)


class RunPayloadV1(BaseModel):
    schema_version: Literal["v1"]
    run_id: str
    work_item_id: str
    worker_type: str
    target: RunTargetPayload
    prompt: RunPromptPayload
    context: RunContextPayload
    policy: RunPolicyPayload
    requested_outputs: List[AllowedRequestedOutput]

    @field_validator("requested_outputs")
    @classmethod
    def validate_requested_outputs(cls, value: List[str]) -> List[str]:
        if not value:
            raise ValueError("requested_outputs must not be empty")
        allowed = {"patch", "log", "report", "code", "summary"}
        unknown = [item for item in value if item not in allowed]
        if unknown:
            raise ValueError(f"unknown requested_outputs: {', '.join(unknown)}")
        return value


class WorkerInfoPayload(BaseModel):
    worker_id: str
    worker_type: str
    runtime_environment: str
    status: WorkerStatusLiteral
    last_heartbeat: datetime
    capabilities: List[str] = Field(default_factory=list)


class WorkerAcceptedRun(BaseModel):
    accepted: bool
    worker_id: str
    run_id: str
    snapshot_status: RunStatusLiteral = "running"
    message: Optional[str] = None


class WorkerArtifactDescriptor(BaseModel):
    artifact_type: AllowedRequestedOutput
    uri: str
    label: str
    metadata_json: Dict[str, Any] = Field(default_factory=dict)


class WorkerRunSnapshot(BaseModel):
    run_id: str
    status: RunStatusLiteral
    worker_id: Optional[str] = None
    heartbeat_at: Optional[datetime] = None
    summary: Optional[str] = None
    failure_reason: Optional[str] = None
    escalation_reason: Optional[str] = None


class RuntimeWorkerDriver(Protocol):
    worker_type: str
    capabilities: List[str]

    def can_accept(self, run_payload: RunPayloadV1) -> bool:
        ...

    def start_run(self, run_payload: RunPayloadV1) -> WorkerAcceptedRun:
        ...

    def cancel_run(self, run_id: str) -> None:
        ...

    def poll_run(self, run_id: str) -> WorkerRunSnapshot:
        ...

    def collect_artifacts(self, run_id: str) -> List[WorkerArtifactDescriptor]:
        ...


CODEX_LOCAL_CAPABILITIES = [
    "repo_modification",
    "code_generation",
    "patch_creation",
    "test_execution",
]
