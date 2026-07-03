from datetime import datetime
from typing import Optional, Any

from pydantic import BaseModel, EmailStr, Field

from app.models import JobType, JobStatus, RetryStrategyType, WorkerStatus, UserRole


# ---- Auth ----

class UserCreate(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8)
    full_name: str
    organization_name: str


class UserOut(BaseModel):
    id: str
    email: str
    full_name: str
    created_at: datetime

    class Config:
        from_attributes = True


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


# ---- Projects ----

class ProjectCreate(BaseModel):
    organization_id: str
    name: str
    description: Optional[str] = None


class ProjectOut(BaseModel):
    id: str
    name: str
    description: Optional[str]
    api_key: str
    created_at: datetime

    class Config:
        from_attributes = True


# ---- Retry policy ----

class RetryPolicyCreate(BaseModel):
    name: str
    strategy: RetryStrategyType = RetryStrategyType.EXPONENTIAL
    max_retries: int = 3
    base_delay_seconds: int = 5
    max_delay_seconds: int = 3600
    multiplier: float = 2.0


class RetryPolicyOut(RetryPolicyCreate):
    id: str

    class Config:
        from_attributes = True


# ---- Queues ----

class QueueCreate(BaseModel):
    name: str
    priority: int = 0
    max_concurrency: int = 5
    retry_policy: Optional[RetryPolicyCreate] = None


class QueueUpdate(BaseModel):
    priority: Optional[int] = None
    max_concurrency: Optional[int] = None
    is_paused: Optional[bool] = None


class QueueOut(BaseModel):
    id: str
    project_id: str
    name: str
    priority: int
    max_concurrency: int
    is_paused: bool
    created_at: datetime

    class Config:
        from_attributes = True


class QueueStats(BaseModel):
    queue_id: str
    queued: int
    scheduled: int
    running: int
    completed: int
    failed: int
    dead_letter: int
    avg_duration_ms: Optional[float] = None
    throughput_last_hour: int = 0


# ---- Jobs ----

class JobCreate(BaseModel):
    name: str
    type: JobType = JobType.IMMEDIATE
    payload: dict[str, Any] = Field(default_factory=dict)
    priority: int = 0
    run_at: Optional[datetime] = None            # required for DELAYED / SCHEDULED
    cron_expression: Optional[str] = None         # required for RECURRING
    max_retries: Optional[int] = None             # overrides queue default
    idempotency_key: Optional[str] = None
    timeout_seconds: int = 300


class BatchJobCreate(BaseModel):
    name: str
    jobs: list[JobCreate]


class JobOut(BaseModel):
    id: str
    queue_id: str
    name: str
    type: JobType
    status: JobStatus
    priority: int
    payload: dict[str, Any]
    run_at: Optional[datetime]
    cron_expression: Optional[str]
    retry_count: int
    max_retries: int
    claimed_by_worker_id: Optional[str]
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class JobExecutionOut(BaseModel):
    id: str
    attempt_number: int
    status: JobStatus
    started_at: Optional[datetime]
    finished_at: Optional[datetime]
    duration_ms: Optional[int]
    error_message: Optional[str]
    worker_id: Optional[str]

    class Config:
        from_attributes = True


class JobLogOut(BaseModel):
    id: str
    level: str
    message: str
    created_at: datetime

    class Config:
        from_attributes = True


# ---- Workers ----

class WorkerRegister(BaseModel):
    name: str
    hostname: Optional[str] = None
    concurrency: int = 5
    queues_subscribed: Optional[list[str]] = None


class WorkerHeartbeatIn(BaseModel):
    active_jobs: int
    cpu_usage: Optional[float] = None
    memory_usage_mb: Optional[float] = None


class WorkerOut(BaseModel):
    id: str
    name: str
    hostname: Optional[str]
    status: WorkerStatus
    concurrency: int
    current_load: int
    last_heartbeat_at: Optional[datetime]
    started_at: datetime

    class Config:
        from_attributes = True


class ClaimRequest(BaseModel):
    worker_id: str
    queue_ids: Optional[list[str]] = None  # restrict claim to specific queues; else all subscribed
    max_jobs: int = 1


# ---- DLQ ----

class DeadLetterOut(BaseModel):
    id: str
    original_job_id: Optional[str]
    queue_id: str
    name: str
    payload: dict[str, Any]
    failure_reason: str
    total_attempts: int
    failed_at: datetime
    replayed: bool

    class Config:
        from_attributes = True


class Page(BaseModel):
    items: list
    total: int
    page: int
    page_size: int
