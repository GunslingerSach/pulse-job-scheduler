from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from app import models, schemas
from app.database import get_db
from app.core.security import get_current_user, require_project_access

router = APIRouter(prefix="/api/v1/projects/{project_id}/queues", tags=["queues"])


@router.post("", response_model=schemas.QueueOut, status_code=201)
def create_queue(project_id: str, payload: schemas.QueueCreate, db: Session = Depends(get_db),
                  user: models.User = Depends(get_current_user)):
    require_project_access(project_id, db, user)
    if db.query(models.Queue).filter(models.Queue.project_id == project_id,
                                      models.Queue.name == payload.name).first():
        raise HTTPException(status_code=400, detail="Queue name already exists in this project")

    retry_policy_id = None
    if payload.retry_policy:
        rp = models.RetryPolicy(**payload.retry_policy.model_dump())
        db.add(rp)
        db.flush()
        retry_policy_id = rp.id

    queue = models.Queue(project_id=project_id, name=payload.name, priority=payload.priority,
                          max_concurrency=payload.max_concurrency, default_retry_policy_id=retry_policy_id)
    db.add(queue)
    db.commit()
    db.refresh(queue)
    return queue


@router.get("", response_model=list[schemas.QueueOut])
def list_queues(project_id: str, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    require_project_access(project_id, db, user)
    return db.query(models.Queue).filter(models.Queue.project_id == project_id).all()


@router.patch("/{queue_id}", response_model=schemas.QueueOut)
def update_queue(project_id: str, queue_id: str, payload: schemas.QueueUpdate, db: Session = Depends(get_db),
                  user: models.User = Depends(get_current_user)):
    require_project_access(project_id, db, user)
    queue = db.query(models.Queue).filter(models.Queue.id == queue_id, models.Queue.project_id == project_id).first()
    if not queue:
        raise HTTPException(status_code=404, detail="Queue not found")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(queue, field, value)
    db.commit()
    db.refresh(queue)
    return queue


@router.post("/{queue_id}/pause", response_model=schemas.QueueOut)
def pause_queue(project_id: str, queue_id: str, db: Session = Depends(get_db),
                 user: models.User = Depends(get_current_user)):
    require_project_access(project_id, db, user)
    queue = db.query(models.Queue).filter(models.Queue.id == queue_id, models.Queue.project_id == project_id).first()
    if not queue:
        raise HTTPException(status_code=404, detail="Queue not found")
    queue.is_paused = True
    db.commit()
    db.refresh(queue)
    return queue


@router.post("/{queue_id}/resume", response_model=schemas.QueueOut)
def resume_queue(project_id: str, queue_id: str, db: Session = Depends(get_db),
                  user: models.User = Depends(get_current_user)):
    require_project_access(project_id, db, user)
    queue = db.query(models.Queue).filter(models.Queue.id == queue_id, models.Queue.project_id == project_id).first()
    if not queue:
        raise HTTPException(status_code=404, detail="Queue not found")
    queue.is_paused = False
    db.commit()
    db.refresh(queue)
    return queue


@router.get("/{queue_id}/stats", response_model=schemas.QueueStats)
def queue_stats(project_id: str, queue_id: str, db: Session = Depends(get_db),
                 user: models.User = Depends(get_current_user)):
    require_project_access(project_id, db, user)
    queue = db.query(models.Queue).filter(models.Queue.id == queue_id, models.Queue.project_id == project_id).first()
    if not queue:
        raise HTTPException(status_code=404, detail="Queue not found")

    def count(status):
        return db.query(func.count(models.Job.id)).filter(models.Job.queue_id == queue_id,
                                                            models.Job.status == status).scalar()

    dlq_count = db.query(func.count(models.DeadLetterJob.id)).filter(
        models.DeadLetterJob.queue_id == queue_id).scalar()

    avg_duration = (
        db.query(func.avg(models.JobExecution.duration_ms))
        .join(models.Job, models.Job.id == models.JobExecution.job_id)
        .filter(models.Job.queue_id == queue_id, models.JobExecution.status == models.JobStatus.COMPLETED)
        .scalar()
    )

    one_hour_ago = datetime.now(timezone.utc) - timedelta(hours=1)
    throughput = (
        db.query(func.count(models.JobExecution.id))
        .join(models.Job, models.Job.id == models.JobExecution.job_id)
        .filter(models.Job.queue_id == queue_id, models.JobExecution.status == models.JobStatus.COMPLETED,
                models.JobExecution.finished_at >= one_hour_ago)
        .scalar()
    )

    return schemas.QueueStats(
        queue_id=queue_id,
        queued=count(models.JobStatus.QUEUED),
        scheduled=count(models.JobStatus.SCHEDULED),
        running=count(models.JobStatus.RUNNING),
        completed=count(models.JobStatus.COMPLETED),
        failed=count(models.JobStatus.FAILED),
        dead_letter=dlq_count,
        avg_duration_ms=float(avg_duration) if avg_duration else None,
        throughput_last_hour=throughput or 0,
    )
