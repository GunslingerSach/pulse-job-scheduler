import enum
import uuid

from sqlalchemy import (
    Column, String, Integer, Boolean, DateTime, ForeignKey, Text, Enum,
    JSON, UniqueConstraint, Index, Float, func
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.database import Base


def gen_uuid():
    return str(uuid.uuid4())


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class UserRole(str, enum.Enum):
    ADMIN = "admin"
    MEMBER = "member"
    VIEWER = "viewer"


class JobType(str, enum.Enum):
    IMMEDIATE = "immediate"
    DELAYED = "delayed"
    SCHEDULED = "scheduled"
    RECURRING = "recurring"
    BATCH = "batch"


class JobStatus(str, enum.Enum):
    QUEUED = "queued"
    SCHEDULED = "scheduled"      # waiting for run_at, not yet eligible to be claimed
    CLAIMED = "claimed"          # picked up by a worker, not yet running
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"            # terminal failure of a single attempt, may retry
    RETRYING = "retrying"        # scheduled for a retry attempt
    DEAD_LETTER = "dead_letter"  # exhausted retries, moved to DLQ
    CANCELLED = "cancelled"
    PAUSED = "paused"


class RetryStrategyType(str, enum.Enum):
    FIXED = "fixed"
    LINEAR = "linear"
    EXPONENTIAL = "exponential"
    NONE = "none"


class WorkerStatus(str, enum.Enum):
    ACTIVE = "active"
    IDLE = "idle"
    DRAINING = "draining"   # graceful shutdown in progress
    OFFLINE = "offline"


class LogLevel(str, enum.Enum):
    DEBUG = "debug"
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


# ---------------------------------------------------------------------------
# Core identity / org structure
# ---------------------------------------------------------------------------

class User(Base):
    __tablename__ = "users"

    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    email = Column(String(255), unique=True, nullable=False, index=True)
    hashed_password = Column(String(255), nullable=False)
    full_name = Column(String(255), nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    memberships = relationship("OrganizationMember", back_populates="user", cascade="all, delete-orphan")


class Organization(Base):
    __tablename__ = "organizations"

    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    name = Column(String(255), nullable=False)
    owner_id = Column(UUID(as_uuid=False), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    projects = relationship("Project", back_populates="organization", cascade="all, delete-orphan")
    members = relationship("OrganizationMember", back_populates="organization", cascade="all, delete-orphan")


class OrganizationMember(Base):
    """Join table: which users belong to which orgs, with what role (RBAC)."""
    __tablename__ = "organization_members"
    __table_args__ = (UniqueConstraint("organization_id", "user_id", name="uq_org_member"),)

    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    organization_id = Column(UUID(as_uuid=False), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(UUID(as_uuid=False), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    role = Column(Enum(UserRole), default=UserRole.MEMBER, nullable=False)

    organization = relationship("Organization", back_populates="members")
    user = relationship("User", back_populates="memberships")


class Project(Base):
    __tablename__ = "projects"
    __table_args__ = (UniqueConstraint("organization_id", "name", name="uq_project_name_per_org"),)

    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    organization_id = Column(UUID(as_uuid=False), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    api_key = Column(String(64), unique=True, nullable=False, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    organization = relationship("Organization", back_populates="projects")
    queues = relationship("Queue", back_populates="project", cascade="all, delete-orphan")


# ---------------------------------------------------------------------------
# Queues & retry policy
# ---------------------------------------------------------------------------

class RetryPolicy(Base):
    """Reusable retry policy, attachable to a queue (default) or an individual job (override)."""
    __tablename__ = "retry_policies"

    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    name = Column(String(255), nullable=False)
    strategy = Column(Enum(RetryStrategyType), default=RetryStrategyType.EXPONENTIAL, nullable=False)
    max_retries = Column(Integer, default=3, nullable=False)
    base_delay_seconds = Column(Integer, default=5, nullable=False)
    max_delay_seconds = Column(Integer, default=3600, nullable=False)
    multiplier = Column(Float, default=2.0, nullable=False)  # used by exponential/linear

    def compute_delay(self, attempt: int) -> int:
        """attempt is 1-indexed (this will be the Nth retry)."""
        if self.strategy == RetryStrategyType.NONE:
            return 0
        if self.strategy == RetryStrategyType.FIXED:
            delay = self.base_delay_seconds
        elif self.strategy == RetryStrategyType.LINEAR:
            delay = self.base_delay_seconds * attempt
        else:  # EXPONENTIAL
            delay = self.base_delay_seconds * (self.multiplier ** (attempt - 1))
        return int(min(delay, self.max_delay_seconds))


class Queue(Base):
    __tablename__ = "queues"
    __table_args__ = (
        UniqueConstraint("project_id", "name", name="uq_queue_name_per_project"),
        Index("ix_queue_project_paused", "project_id", "is_paused"),
    )

    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    project_id = Column(UUID(as_uuid=False), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    name = Column(String(255), nullable=False)
    priority = Column(Integer, default=0, nullable=False)  # higher = served first
    max_concurrency = Column(Integer, default=5, nullable=False)  # max jobs RUNNING at once for this queue
    is_paused = Column(Boolean, default=False, nullable=False)
    default_retry_policy_id = Column(UUID(as_uuid=False), ForeignKey("retry_policies.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    project = relationship("Project", back_populates="queues")
    default_retry_policy = relationship("RetryPolicy")
    jobs = relationship("Job", back_populates="queue", cascade="all, delete-orphan")


# ---------------------------------------------------------------------------
# Jobs
# ---------------------------------------------------------------------------

class Job(Base):
    __tablename__ = "jobs"
    __table_args__ = (
        # This composite index is the single most important index in the schema:
        # it is exactly the WHERE/ORDER BY shape the worker's claim query uses.
        Index("ix_jobs_claim_scan", "queue_id", "status", "run_at", "priority"),
        Index("ix_jobs_batch", "batch_id"),
        UniqueConstraint("queue_id", "idempotency_key", name="uq_job_idempotency"),
    )

    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    queue_id = Column(UUID(as_uuid=False), ForeignKey("queues.id", ondelete="CASCADE"), nullable=False)
    type = Column(Enum(JobType), nullable=False, default=JobType.IMMEDIATE)
    name = Column(String(255), nullable=False)
    payload = Column(JSON, nullable=False, default=dict)
    status = Column(Enum(JobStatus), nullable=False, default=JobStatus.QUEUED, index=True)
    priority = Column(Integer, default=0, nullable=False)

    run_at = Column(DateTime(timezone=True), nullable=True)  # null => eligible immediately
    cron_expression = Column(String(120), nullable=True)     # set only for RECURRING template jobs
    is_recurring_template = Column(Boolean, default=False, nullable=False)
    parent_recurring_job_id = Column(UUID(as_uuid=False), ForeignKey("jobs.id", ondelete="SET NULL"), nullable=True)

    batch_id = Column(UUID(as_uuid=False), nullable=True)

    retry_policy_id = Column(UUID(as_uuid=False), ForeignKey("retry_policies.id", ondelete="SET NULL"), nullable=True)
    max_retries = Column(Integer, default=3, nullable=False)
    retry_count = Column(Integer, default=0, nullable=False)

    idempotency_key = Column(String(255), nullable=True)
    timeout_seconds = Column(Integer, default=300, nullable=False)

    claimed_by_worker_id = Column(UUID(as_uuid=False), ForeignKey("workers.id", ondelete="SET NULL"), nullable=True)
    claimed_at = Column(DateTime(timezone=True), nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    queue = relationship("Queue", back_populates="jobs")
    retry_policy = relationship("RetryPolicy")
    executions = relationship("JobExecution", back_populates="job", cascade="all, delete-orphan")
    logs = relationship("JobLog", back_populates="job", cascade="all, delete-orphan")


class JobExecution(Base):
    """One row per attempt. Jobs with retries have multiple execution rows."""
    __tablename__ = "job_executions"
    __table_args__ = (Index("ix_job_executions_job", "job_id", "attempt_number"),)

    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    job_id = Column(UUID(as_uuid=False), ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False)
    worker_id = Column(UUID(as_uuid=False), ForeignKey("workers.id", ondelete="SET NULL"), nullable=True)
    attempt_number = Column(Integer, nullable=False, default=1)
    status = Column(Enum(JobStatus), nullable=False)
    started_at = Column(DateTime(timezone=True), nullable=True)
    finished_at = Column(DateTime(timezone=True), nullable=True)
    duration_ms = Column(Integer, nullable=True)
    result = Column(JSON, nullable=True)
    error_message = Column(Text, nullable=True)
    error_stacktrace = Column(Text, nullable=True)

    job = relationship("Job", back_populates="executions")
    worker = relationship("Worker")


class JobLog(Base):
    __tablename__ = "job_logs"
    __table_args__ = (Index("ix_job_logs_job_created", "job_id", "created_at"),)

    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    job_id = Column(UUID(as_uuid=False), ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False)
    execution_id = Column(UUID(as_uuid=False), ForeignKey("job_executions.id", ondelete="CASCADE"), nullable=True)
    level = Column(Enum(LogLevel), default=LogLevel.INFO, nullable=False)
    message = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    job = relationship("Job", back_populates="logs")


class DeadLetterJob(Base):
    """Terminal record for jobs that exhausted their retry budget. Kept separately
    from `jobs` so the hot claim-scan index never has to skip over dead rows."""
    __tablename__ = "dead_letter_jobs"
    __table_args__ = (Index("ix_dlq_queue_failed_at", "queue_id", "failed_at"),)

    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    original_job_id = Column(UUID(as_uuid=False), ForeignKey("jobs.id", ondelete="SET NULL"), nullable=True)
    queue_id = Column(UUID(as_uuid=False), ForeignKey("queues.id", ondelete="CASCADE"), nullable=False)
    name = Column(String(255), nullable=False)
    payload = Column(JSON, nullable=False)
    failure_reason = Column(Text, nullable=False)
    total_attempts = Column(Integer, nullable=False)
    failed_at = Column(DateTime(timezone=True), server_default=func.now())
    replayed = Column(Boolean, default=False, nullable=False)


# ---------------------------------------------------------------------------
# Workers
# ---------------------------------------------------------------------------

class Worker(Base):
    __tablename__ = "workers"

    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    name = Column(String(255), nullable=False)
    hostname = Column(String(255), nullable=True)
    status = Column(Enum(WorkerStatus), default=WorkerStatus.IDLE, nullable=False, index=True)
    concurrency = Column(Integer, default=5, nullable=False)  # max jobs this worker process runs at once
    current_load = Column(Integer, default=0, nullable=False)
    queues_subscribed = Column(JSON, nullable=True)  # list of queue ids/names, null = all
    last_heartbeat_at = Column(DateTime(timezone=True), nullable=True, index=True)
    started_at = Column(DateTime(timezone=True), server_default=func.now())


class WorkerHeartbeat(Base):
    """Time-series heartbeat history, used for the worker health chart and to
    detect and reap workers that died without a graceful shutdown."""
    __tablename__ = "worker_heartbeats"
    __table_args__ = (Index("ix_heartbeats_worker_ts", "worker_id", "timestamp"),)

    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    worker_id = Column(UUID(as_uuid=False), ForeignKey("workers.id", ondelete="CASCADE"), nullable=False)
    timestamp = Column(DateTime(timezone=True), server_default=func.now())
    active_jobs = Column(Integer, default=0, nullable=False)
    cpu_usage = Column(Float, nullable=True)
    memory_usage_mb = Column(Float, nullable=True)
