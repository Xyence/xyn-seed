"""SQLAlchemy database models for Xyn Seed v0.0"""
import uuid
from datetime import datetime
from sqlalchemy import Column, String, Integer, DateTime, JSON, ForeignKey, Text, Enum, BigInteger
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
import enum

from core.database import Base


class RunStatus(str, enum.Enum):
    """Run execution status."""
    CREATED = "created"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class StepStatus(str, enum.Enum):
    """Step execution status."""
    CREATED = "created"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


class DraftStatus(str, enum.Enum):
    """Draft status."""
    DRAFT = "draft"
    VALIDATED = "validated"
    PROMOTED = "promoted"


class Event(Base):
    """Event model - immutable input records."""
    __tablename__ = "events"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    event_name = Column(String(255), nullable=False, index=True)
    occurred_at = Column(DateTime, nullable=False, default=datetime.utcnow, index=True)
    env_id = Column(String(255), nullable=False, default="local-dev")
    actor = Column(String(255), nullable=False, default="system")
    correlation_id = Column(String(255), nullable=True, index=True)
    run_id = Column(UUID(as_uuid=True), ForeignKey("runs.id"), nullable=True, index=True)
    step_id = Column(UUID(as_uuid=True), ForeignKey("steps.id"), nullable=True)
    resource_type = Column(String(255), nullable=True)
    resource_id = Column(String(255), nullable=True)
    data = Column(JSON, nullable=False, default=dict)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    # Relationships
    run = relationship("Run", back_populates="events", foreign_keys=[run_id])
    step = relationship("Step", back_populates="events", foreign_keys=[step_id])


class Blueprint(Base):
    """Blueprint model - declarative workflow definitions."""
    __tablename__ = "blueprints"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(255), nullable=False, unique=True, index=True)
    version = Column(String(50), nullable=False)
    trigger_event_type = Column(String(255), nullable=True, index=True)
    definition = Column(JSON, nullable=False)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    runs = relationship("Run", back_populates="blueprint")


class Draft(Base):
    """Draft model - working versions of blueprints/packs."""
    __tablename__ = "drafts"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(255), nullable=False, index=True)
    kind = Column(String(50), nullable=False)  # blueprint, pack
    trigger_event_type = Column(String(255), nullable=True)
    definition = Column(JSON, nullable=False)
    status = Column(Enum(DraftStatus), nullable=False, default=DraftStatus.DRAFT, index=True)
    notes = Column(Text, nullable=True)
    source_run_id = Column(UUID(as_uuid=True), ForeignKey("runs.id"), nullable=True)
    revision = Column(Integer, nullable=False, default=1)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    source_run = relationship("Run", foreign_keys=[source_run_id])


class Run(Base):
    """Run model - execution instance of a blueprint."""
    __tablename__ = "runs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(255), nullable=False)
    blueprint_id = Column(UUID(as_uuid=True), ForeignKey("blueprints.id"), nullable=True, index=True)
    event_id = Column(UUID(as_uuid=True), ForeignKey("events.id"), nullable=True)
    status = Column(Enum(RunStatus), nullable=False, default=RunStatus.CREATED, index=True)
    actor = Column(String(255), nullable=False, default="system")
    correlation_id = Column(String(255), nullable=False, index=True)
    inputs = Column(JSON, nullable=False, default=dict)
    outputs = Column(JSON, nullable=True)
    error = Column(JSON, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow, index=True)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)

    # Relationships
    blueprint = relationship("Blueprint", back_populates="runs")
    trigger_event = relationship("Event", foreign_keys=[event_id])
    steps = relationship("Step", back_populates="run", cascade="all, delete-orphan")
    artifacts = relationship("Artifact", back_populates="run")
    events = relationship("Event", back_populates="run", foreign_keys=[Event.run_id])


class Step(Base):
    """Step model - atomic unit in a run."""
    __tablename__ = "steps"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    run_id = Column(UUID(as_uuid=True), ForeignKey("runs.id"), nullable=False, index=True)
    name = Column(String(255), nullable=False)
    idx = Column(Integer, nullable=False)
    kind = Column(String(50), nullable=False)  # agent_task, action_task, gate, transform
    status = Column(Enum(StepStatus), nullable=False, default=StepStatus.CREATED, index=True)
    inputs = Column(JSON, nullable=True)
    outputs = Column(JSON, nullable=True)
    error = Column(JSON, nullable=True)
    logs_artifact_id = Column(UUID(as_uuid=True), ForeignKey("artifacts.id"), nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)

    # Relationships
    run = relationship("Run", back_populates="steps")
    artifacts = relationship("Artifact", back_populates="step", foreign_keys="Artifact.step_id")
    logs_artifact = relationship("Artifact", foreign_keys=[logs_artifact_id], post_update=True)
    events = relationship("Event", back_populates="step", foreign_keys=[Event.step_id])


class Artifact(Base):
    """Artifact model - generated outputs."""
    __tablename__ = "artifacts"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(255), nullable=False)
    kind = Column(String(50), nullable=False)  # log, report, bundle, file
    content_type = Column(String(255), nullable=False)
    byte_length = Column(BigInteger, nullable=True)
    sha256 = Column(String(64), nullable=True)
    run_id = Column(UUID(as_uuid=True), ForeignKey("runs.id"), nullable=True, index=True)
    step_id = Column(UUID(as_uuid=True), ForeignKey("steps.id"), nullable=True, index=True)
    created_by = Column(String(255), nullable=False, default="system")
    extra_metadata = Column(JSON, nullable=False, default=dict)
    storage_path = Column(String(1024), nullable=True)  # LocalFS path
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow, index=True)

    # Relationships
    run = relationship("Run", back_populates="artifacts", foreign_keys=[run_id])
    step = relationship("Step", back_populates="artifacts", foreign_keys=[step_id])


class Node(Base):
    """Node model - deployed instance."""
    __tablename__ = "nodes"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(255), nullable=False, unique=True)
    parent_id = Column(UUID(as_uuid=True), ForeignKey("nodes.id"), nullable=True)
    version = Column(String(50), nullable=False)
    status = Column(String(50), nullable=False, default="active")
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Self-referential relationship
    parent = relationship("Node", remote_side=[id], backref="children")
