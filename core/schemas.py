"""Pydantic schemas (DTOs) for Xyn Seed v0.0 API"""
from datetime import datetime
from typing import Optional, Dict, Any, List
from uuid import UUID
from pydantic import BaseModel, Field


# Health Schemas
class HealthResponse(BaseModel):
    """Health check response."""
    status: str
    version: str
    uptime_seconds: int
    now: datetime


# Event Schemas
class EventResource(BaseModel):
    """Event resource reference."""
    type: str
    id: str


class Event(BaseModel):
    """Event response model."""
    event_id: UUID = Field(alias="id")
    event_name: str
    occurred_at: datetime
    env_id: str
    actor: str
    correlation_id: Optional[str] = None
    run_id: Optional[UUID] = None
    step_id: Optional[UUID] = None
    resource: Optional[EventResource] = None
    data: Dict[str, Any] = Field(default_factory=dict)

    class Config:
        from_attributes = True
        populate_by_name = True

    @classmethod
    def from_orm_model(cls, event):
        """Convert ORM model to schema."""
        resource = None
        if event.resource_type and event.resource_id:
            resource = EventResource(type=event.resource_type, id=event.resource_id)

        return cls(
            id=event.id,
            event_name=event.event_name,
            occurred_at=event.occurred_at,
            env_id=event.env_id,
            actor=event.actor,
            correlation_id=event.correlation_id,
            run_id=event.run_id,
            step_id=event.step_id,
            resource=resource,
            data=event.data or {}
        )


class EventListResponse(BaseModel):
    """Event list response with pagination."""
    items: List[Event]
    next_cursor: Optional[str] = None


class EmitEventRequest(BaseModel):
    """Request to emit a new event."""
    event_name: str
    resource: Optional[EventResource] = None
    data: Dict[str, Any] = Field(default_factory=dict)
    run_id: Optional[UUID] = None
    step_id: Optional[UUID] = None


# Run Schemas
class RunCreateRequest(BaseModel):
    """Request to create a new run."""
    name: str
    blueprint_ref: Optional[str] = None
    inputs: Dict[str, Any] = Field(default_factory=dict)
    priority: int = 0


class Run(BaseModel):
    """Run response model."""
    run_id: UUID = Field(alias="id")
    name: str
    status: str
    created_at: datetime
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    actor: str
    correlation_id: str
    inputs: Dict[str, Any] = Field(default_factory=dict)
    outputs: Optional[Dict[str, Any]] = None
    error: Optional[Dict[str, Any]] = None

    class Config:
        from_attributes = True
        populate_by_name = True

    @classmethod
    def from_orm_model(cls, run):
        """Convert ORM model to schema."""
        return cls(
            id=run.id,
            name=run.name,
            status=run.status.value,
            created_at=run.created_at,
            started_at=run.started_at,
            completed_at=run.completed_at,
            actor=run.actor,
            correlation_id=run.correlation_id,
            inputs=run.inputs or {},
            outputs=run.outputs,
            error=run.error
        )


class RunListResponse(BaseModel):
    """Run list response with pagination."""
    items: List[Run]
    next_cursor: Optional[str] = None


# Step Schemas
class Step(BaseModel):
    """Step response model."""
    step_id: UUID = Field(alias="id")
    run_id: UUID
    name: str
    status: str
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    logs_artifact_id: Optional[UUID] = None
    inputs: Optional[Dict[str, Any]] = None
    outputs: Optional[Dict[str, Any]] = None
    error: Optional[Dict[str, Any]] = None

    class Config:
        from_attributes = True
        populate_by_name = True

    @classmethod
    def from_orm_model(cls, step):
        """Convert ORM model to schema."""
        return cls(
            id=step.id,
            run_id=step.run_id,
            name=step.name,
            status=step.status.value,
            started_at=step.started_at,
            completed_at=step.completed_at,
            logs_artifact_id=step.logs_artifact_id,
            inputs=step.inputs,
            outputs=step.outputs,
            error=step.error
        )


# Artifact Schemas
class ArtifactCreateRequest(BaseModel):
    """Request to create an artifact."""
    name: str
    kind: str  # log, report, bundle, file
    content_type: str
    byte_length: Optional[int] = None
    run_id: Optional[UUID] = None
    step_id: Optional[UUID] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class Artifact(BaseModel):
    """Artifact response model."""
    artifact_id: UUID = Field(alias="id")
    name: str
    kind: str
    content_type: str
    byte_length: Optional[int] = None
    created_at: datetime
    created_by: str
    run_id: Optional[UUID] = None
    step_id: Optional[UUID] = None
    sha256: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)

    class Config:
        from_attributes = True
        populate_by_name = True

    @classmethod
    def from_orm_model(cls, artifact):
        """Convert ORM model to schema."""
        return cls(
            id=artifact.id,
            name=artifact.name,
            kind=artifact.kind,
            content_type=artifact.content_type,
            byte_length=artifact.byte_length,
            created_at=artifact.created_at,
            created_by=artifact.created_by,
            run_id=artifact.run_id,
            step_id=artifact.step_id,
            sha256=artifact.sha256,
            metadata=artifact.extra_metadata or {}
        )


class ArtifactListResponse(BaseModel):
    """Artifact list response with pagination."""
    items: List[Artifact]
    next_cursor: Optional[str] = None


# Draft Schemas
class Draft(BaseModel):
    """Draft response model."""
    draft_id: UUID = Field(alias="id")
    name: str
    kind: str
    status: str
    created_at: datetime
    updated_at: datetime
    content: Dict[str, Any] = Field(default_factory=dict)

    class Config:
        from_attributes = True
        populate_by_name = True

    @classmethod
    def from_orm_model(cls, draft):
        """Convert ORM model to schema."""
        return cls(
            id=draft.id,
            name=draft.name,
            kind=draft.kind,
            status=draft.status.value,
            created_at=draft.created_at,
            updated_at=draft.updated_at,
            content=draft.definition or {}
        )


# Error Schema
class ErrorDetail(BaseModel):
    """Error detail."""
    code: str
    message: str
    details: Optional[Dict[str, Any]] = None


class ErrorResponse(BaseModel):
    """Standard error response."""
    error: ErrorDetail
    correlation_id: Optional[str] = None
