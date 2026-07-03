"""
Core scheduling engine.

The single most important reliability property of this system is that two
workers must never both believe they own the same job. We get that guarantee
from Postgres row locking rather than from application-level mutexes, because
row locks survive worker crashes and work correctly across many worker
processes/machines without needing a separate coordination service.

Claim algorithm
----------------
    SELECT ... FROM jobs
    WHERE queue_id = ANY(:queues) AND status IN ('queued','retrying')
      AND (run_at IS NULL OR run_at <= now())
    ORDER BY priority DESC, created_at ASC
    FOR UPDATE SKIP LOCKED
    LIMIT :n

`FOR UPDATE` takes a row lock inside the transaction; `SKIP LOCKED` means a
second worker running the same query concurrently simply skips rows another
worker already has locked, instead of blocking on them. Combined with the
`ix_jobs_claim_scan` index (queue_id, status, run_at, priority) this scan
stays an index scan even under high queue depth. We commit immediately after
flipping status to CLAIMED, which releases the lock and makes the claim
durable.

Concurrency-limit enforcement (a queue's max_concurrency) is applied as a
COUNT(*) of currently RUNNING jobs for that queue *inside the same
transaction*, before claiming more, so a queue can never exceed its
configured concurrency even with many worker processes claiming in parallel.
"""

from datetime import datetime, timezone, timedelta
from typing import Optional

from sqlalchemy import select, func
from sqlalchemy.orm import Session

from app import models


def _now():
    return datetime.now(timezone.utc)


def claim_jobs(db: Session, worker: models.Worker, queue_ids: Optional[list[str]], max_jobs: int) -> list[models.Job]:
    claimed: list[models.Job] = []

    q = db.query(models.Queue).filter(models.Queue.is_paused.is_(False))
    if queue_ids:
        q = q.filter(models.Queue.id.in_(queue_ids))
    eligible_queues = {row.id: row for row in q.all()}
    if not eligible_queues:
        return claimed

    for queue_id, queue in eligible_queues.items():
        if len(claimed) >= max_jobs:
            break

        running_count = (
            db.query(func.count(models.Job.id))
            .filter(models.Job.queue_id == queue_id, models.Job.status == models.JobStatus.RUNNING)
            .scalar()
        )
        available_capacity = max(0, queue.max_concurrency - running_count)
        if available_capacity <= 0:
            continue

        take = min(available_capacity, max_jobs - len(claimed))

        candidates = (
            db.query(models.Job)
            .filter(
                models.Job.queue_id == queue_id,
                models.Job.status.in_([models.JobStatus.QUEUED, models.JobStatus.RETRYING]),
                (models.Job.run_at.is_(None)) | (models.Job.run_at <= _now()),
            )
            .order_by(models.Job.priority.desc(), models.Job.created_at.asc())
            .with_for_update(skip_locked=True)
            .limit(take)
            .all()
        )

        for job in candidates:
            job.status = models.JobStatus.CLAIMED
            job.claimed_by_worker_id = worker.id
            job.claimed_at = _now()
            claimed.append(job)

        if candidates:
            db.commit()  # release row locks as soon as the claim is durable

    for job in claimed:
        db.refresh(job)
    return claimed


def start_execution(db: Session, job: models.Job, worker: models.Worker) -> models.JobExecution:
    job.status = models.JobStatus.RUNNING
    execution = models.JobExecution(
        job_id=job.id,
        worker_id=worker.id,
        attempt_number=job.retry_count + 1,
        status=models.JobStatus.RUNNING,
        started_at=_now(),
    )
    db.add(execution)
    db.add(models.JobLog(job_id=job.id, level=models.LogLevel.INFO,
                          message=f"Started attempt {execution.attempt_number} on worker {worker.name}"))
    db.commit()
    db.refresh(execution)
    return execution


def complete_execution(db: Session, job: models.Job, execution: models.JobExecution, result: dict) -> None:
    execution.status = models.JobStatus.COMPLETED
    execution.finished_at = _now()
    execution.result = result
    if execution.started_at:
        execution.duration_ms = int((execution.finished_at - execution.started_at).total_seconds() * 1000)
    job.status = models.JobStatus.COMPLETED
    job.claimed_by_worker_id = None
    db.add(models.JobLog(job_id=job.id, level=models.LogLevel.INFO, message="Execution completed successfully"))
    db.commit()

    # Recurring template jobs re-enqueue their next occurrence on success.
    if job.parent_recurring_job_id:
        _maybe_schedule_next_occurrence(db, job.parent_recurring_job_id)


def fail_execution(db: Session, job: models.Job, execution: models.JobExecution, error_message: str,
                    stacktrace: Optional[str] = None) -> None:
    execution.status = models.JobStatus.FAILED
    execution.finished_at = _now()
    execution.error_message = error_message
    execution.error_stacktrace = stacktrace
    if execution.started_at:
        execution.duration_ms = int((execution.finished_at - execution.started_at).total_seconds() * 1000)
    db.add(models.JobLog(job_id=job.id, level=models.LogLevel.ERROR, message=f"Attempt failed: {error_message}"))

    job.retry_count += 1
    policy = job.retry_policy or (job.queue.default_retry_policy if job.queue else None)
    max_retries = job.max_retries if job.max_retries is not None else (policy.max_retries if policy else 0)

    if job.retry_count <= max_retries and policy:
        delay = policy.compute_delay(job.retry_count)
        job.status = models.JobStatus.RETRYING
        job.run_at = _now() + timedelta(seconds=delay)
        job.claimed_by_worker_id = None
        db.add(models.JobLog(job_id=job.id, level=models.LogLevel.WARNING,
                              message=f"Scheduling retry {job.retry_count}/{max_retries} in {delay}s"))
        db.commit()
    else:
        _move_to_dead_letter(db, job, error_message)


def _move_to_dead_letter(db: Session, job: models.Job, reason: str) -> None:
    dlq_entry = models.DeadLetterJob(
        original_job_id=job.id,
        queue_id=job.queue_id,
        name=job.name,
        payload=job.payload,
        failure_reason=reason,
        total_attempts=job.retry_count,
    )
    job.status = models.JobStatus.DEAD_LETTER
    job.claimed_by_worker_id = None
    db.add(dlq_entry)
    db.add(models.JobLog(job_id=job.id, level=models.LogLevel.ERROR,
                          message="Retries exhausted; moved to dead letter queue"))
    db.commit()


def replay_dead_letter(db: Session, dlq_entry: models.DeadLetterJob) -> models.Job:
    """Re-enqueue a DLQ entry as a fresh job with retry_count reset to 0."""
    new_job = models.Job(
        queue_id=dlq_entry.queue_id,
        type=models.JobType.IMMEDIATE,
        name=dlq_entry.name,
        payload=dlq_entry.payload,
        status=models.JobStatus.QUEUED,
        retry_count=0,
    )
    dlq_entry.replayed = True
    db.add(new_job)
    db.commit()
    db.refresh(new_job)
    return new_job


def _maybe_schedule_next_occurrence(db: Session, recurring_template_id: str) -> None:
    from croniter import croniter

    template = db.query(models.Job).filter(models.Job.id == recurring_template_id).first()
    if not template or not template.cron_expression:
        return
    next_run = croniter(template.cron_expression, _now()).get_next(datetime)
    occurrence = models.Job(
        queue_id=template.queue_id,
        type=models.JobType.SCHEDULED,
        name=template.name,
        payload=template.payload,
        status=models.JobStatus.SCHEDULED,
        priority=template.priority,
        run_at=next_run,
        retry_policy_id=template.retry_policy_id,
        max_retries=template.max_retries,
        parent_recurring_job_id=template.id,
        timeout_seconds=template.timeout_seconds,
    )
    db.add(occurrence)
    db.commit()


def promote_scheduled_jobs(db: Session) -> int:
    """Flip SCHEDULED jobs whose run_at has arrived to QUEUED so they become
    claimable. Called periodically by the scheduler loop (see
    services/scheduler_service.py)."""
    now = _now()
    result = (
        db.query(models.Job)
        .filter(models.Job.status == models.JobStatus.SCHEDULED, models.Job.run_at <= now)
        .update({models.Job.status: models.JobStatus.QUEUED}, synchronize_session=False)
    )
    db.commit()
    return result


def reap_stale_workers(db: Session, offline_threshold_seconds: int) -> list[str]:
    """Workers that stop heartbeating are marked OFFLINE, and any job they
    still hold CLAIMED/RUNNING is released back to the queue so it can be
    picked up by a healthy worker instead of being stuck forever."""
    cutoff = _now() - timedelta(seconds=offline_threshold_seconds)
    stale_workers = (
        db.query(models.Worker)
        .filter(models.Worker.status != models.WorkerStatus.OFFLINE, models.Worker.last_heartbeat_at < cutoff)
        .all()
    )
    reaped_ids = []
    for worker in stale_workers:
        worker.status = models.WorkerStatus.OFFLINE
        orphaned_jobs = (
            db.query(models.Job)
            .filter(
                models.Job.claimed_by_worker_id == worker.id,
                models.Job.status.in_([models.JobStatus.CLAIMED, models.JobStatus.RUNNING]),
            )
            .all()
        )
        for job in orphaned_jobs:
            job.status = models.JobStatus.QUEUED
            job.claimed_by_worker_id = None
            db.add(models.JobLog(job_id=job.id, level=models.LogLevel.WARNING,
                                  message=f"Worker {worker.name} went offline; job requeued"))
        reaped_ids.append(worker.id)
    db.commit()
    return reaped_ids
