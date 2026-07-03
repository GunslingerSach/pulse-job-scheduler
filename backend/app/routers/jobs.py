import uuid
from datetime import datetime, timezone

from croniter import croniter
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app import models, schemas
from app.database import get_db
from app.core.security import get_current_user, require_project_access

router = APIRouter(prefix="/api/v1/projects/{project_id}/queues/{queue_id}/jobs", tags=["jobs"])


def _get_queue(project_id: str, queue_id: str, db: Session) -> models.Queue:
    queue = db.query(models.Queue).filter(models.Queue.id == queue_id, models.Queue.project_id == project_id).first()
    if not queue:
        raise HTTPException(status_code=404, detail="Queue not found")
    return queue


def _build_job(queue: models.Queue, payload: schemas.JobCreate) -> models.Job:
    if payload.type in (models.JobType.DELAYED, models.JobType.SCHEDULED) and not payload.run_at:
        raise HTTPException(status_code=422, detail=f"'{payload.type}' jobs require run_at")
    if payload.type == models.JobType.RECURRING and not payload.cron_expression:
        raise HTTPException(status_code=422, detail="RECURRING jobs require cron_expression")
    if payload.cron_expression and not croniter.is_valid(payload.cron_expression):
        raise HTTPException(status_code=422, detail="Invalid cron expression")

    initial_status = models.JobStatus.QUEUED
    run_at = payload.run_at
    if payload.type in (models.JobType.DELAYED, models.JobType.SCHEDULED):
        initial_status = models.JobStatus.SCHEDULED
    if payload.type == models.JobType.RECURRING:
        # The template row itself never runs; it just materializes SCHEDULED
        # child occurrences (see job_service._maybe_schedule_next_occurrence).
        run_at = croniter(payload.cron_expression, datetime.now(timezone.utc)).get_next(datetime)
        initial_status = models.JobStatus.SCHEDULED

    max_retries = payload.max_retries if payload.max_retries is not None else (
        queue.default_retry_policy.max_retries if queue.default_retry_policy else 0)

    job = models.Job(
        queue_id=queue.id, type=payload.type, name=payload.name, payload=payload.payload,
        status=initial_status, priority=payload.priority, run_at=run_at,
        cron_expression=payload.cron_expression if payload.type == models.JobType.RECURRING else None,
        is_recurring_template=(payload.type == models.JobType.RECURRING),
        retry_policy_id=queue.default_retry_policy_id, max_retries=max_retries,
        idempotency_key=payload.idempotency_key, timeout_seconds=payload.timeout_seconds,
    )
    if payload.type == models.JobType.RECURRING:
        job.parent_recurring_job_id = None  # the template itself; children reference it after insert
    return job


@router.post("", response_model=schemas.JobOut, status_code=201)
def create_job(project_id: str, queue_id: str, payload: schemas.JobCreate, db: Session = Depends(get_db),
               user: models.User = Depends(get_current_user)):
    require_project_access(project_id, db, user)
    queue = _get_queue(project_id, queue_id, db)

    if payload.idempotency_key:
        existing = db.query(models.Job).filter(models.Job.queue_id == queue_id,
                                                 models.Job.idempotency_key == payload.idempotency_key).first()
        if existing:
            return existing

    job = _build_job(queue, payload)
    db.add(job)
    db.commit()
    db.refresh(job)

    if job.type == models.JobType.RECURRING:
        job.parent_recurring_job_id = job.id  # template points to itself; children copy this pointer
        db.commit()
        db.refresh(job)
    return job


@router.post("/batch", response_model=list[schemas.JobOut], status_code=201)
def create_batch(project_id: str, queue_id: str, payload: schemas.BatchJobCreate, db: Session = Depends(get_db),
                  user: models.User = Depends(get_current_user)):
    require_project_access(project_id, db, user)
    queue = _get_queue(project_id, queue_id, db)
    batch_id = str(uuid.uuid4())
    created = []
    for job_payload in payload.jobs:
        job = _build_job(queue, job_payload)
        job.batch_id = batch_id
        db.add(job)
        created.append(job)
    db.commit()
    for job in created:
        db.refresh(job)
    return created


@router.get("", response_model=schemas.Page)
def list_jobs(project_id: str, queue_id: str, db: Session = Depends(get_db),
              user: models.User = Depends(get_current_user),
              status: models.JobStatus | None = None, job_type: models.JobType | None = None,
              page: int = Query(1, ge=1), page_size: int = Query(25, ge=1, le=200)):
    require_project_access(project_id, db, user)
    _get_queue(project_id, queue_id, db)

    q = db.query(models.Job).filter(models.Job.queue_id == queue_id)
    if status:
        q = q.filter(models.Job.status == status)
    if job_type:
        q = q.filter(models.Job.type == job_type)

    total = q.count()
    items = (q.order_by(models.Job.created_at.desc())
              .offset((page - 1) * page_size).limit(page_size).all())
    return schemas.Page(items=[schemas.JobOut.model_validate(j) for j in items], total=total,
                         page=page, page_size=page_size)


@router.get("/{job_id}", response_model=schemas.JobOut)
def get_job(project_id: str, queue_id: str, job_id: str, db: Session = Depends(get_db),
            user: models.User = Depends(get_current_user)):
    require_project_access(project_id, db, user)
    job = db.query(models.Job).filter(models.Job.id == job_id, models.Job.queue_id == queue_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@router.get("/{job_id}/executions", response_model=list[schemas.JobExecutionOut])
def get_job_executions(project_id: str, queue_id: str, job_id: str, db: Session = Depends(get_db),
                        user: models.User = Depends(get_current_user)):
    require_project_access(project_id, db, user)
    return (db.query(models.JobExecution).filter(models.JobExecution.job_id == job_id)
            .order_by(models.JobExecution.attempt_number.asc()).all())


@router.get("/{job_id}/logs", response_model=list[schemas.JobLogOut])
def get_job_logs(project_id: str, queue_id: str, job_id: str, db: Session = Depends(get_db),
                  user: models.User = Depends(get_current_user)):
    require_project_access(project_id, db, user)
    return (db.query(models.JobLog).filter(models.JobLog.job_id == job_id)
            .order_by(models.JobLog.created_at.asc()).all())


@router.post("/{job_id}/cancel", response_model=schemas.JobOut)
def cancel_job(project_id: str, queue_id: str, job_id: str, db: Session = Depends(get_db),
               user: models.User = Depends(get_current_user)):
    require_project_access(project_id, db, user)
    job = db.query(models.Job).filter(models.Job.id == job_id, models.Job.queue_id == queue_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if job.status in (models.JobStatus.COMPLETED, models.JobStatus.DEAD_LETTER, models.JobStatus.CANCELLED):
        raise HTTPException(status_code=400, detail=f"Cannot cancel a job in status {job.status}")
    job.status = models.JobStatus.CANCELLED
    db.commit()
    db.refresh(job)
    return job


@router.post("/{job_id}/retry", response_model=schemas.JobOut)
def manual_retry(project_id: str, queue_id: str, job_id: str, db: Session = Depends(get_db),
                  user: models.User = Depends(get_current_user)):
    """Manually re-queue a FAILED/DEAD_LETTER job from the dashboard."""
    require_project_access(project_id, db, user)
    job = db.query(models.Job).filter(models.Job.id == job_id, models.Job.queue_id == queue_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    job.status = models.JobStatus.QUEUED
    job.claimed_by_worker_id = None
    job.run_at = None
    db.commit()
    db.refresh(job)
    return job
