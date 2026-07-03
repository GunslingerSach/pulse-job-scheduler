from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session

from app import models
from app.database import get_db
from app.core.security import get_current_user, require_project_access

router = APIRouter(prefix="/api/v1/projects/{project_id}/stats", tags=["stats"])


@router.get("/overview")
def overview(project_id: str, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    require_project_access(project_id, db, user)
    queue_ids = [q.id for q in db.query(models.Queue).filter(models.Queue.project_id == project_id).all()]

    def count(status):
        return db.query(func.count(models.Job.id)).filter(models.Job.queue_id.in_(queue_ids),
                                                            models.Job.status == status).scalar() if queue_ids else 0

    workers = db.query(models.Worker).all()
    active_workers = sum(1 for w in workers if w.status in (models.WorkerStatus.ACTIVE, models.WorkerStatus.IDLE))

    dlq_count = db.query(func.count(models.DeadLetterJob.id)).filter(
        models.DeadLetterJob.queue_id.in_(queue_ids)).scalar() if queue_ids else 0

    return {
        "queued": count(models.JobStatus.QUEUED),
        "scheduled": count(models.JobStatus.SCHEDULED),
        "running": count(models.JobStatus.RUNNING),
        "completed": count(models.JobStatus.COMPLETED),
        "dead_letter": dlq_count,
        "active_workers": active_workers,
        "total_workers": len(workers),
        "queue_count": len(queue_ids),
    }


@router.get("/throughput")
def throughput(project_id: str, hours: int = 24, db: Session = Depends(get_db),
               user: models.User = Depends(get_current_user)):
    """Completed + failed job counts bucketed by hour, for the dashboard chart."""
    require_project_access(project_id, db, user)
    queue_ids = [q.id for q in db.query(models.Queue).filter(models.Queue.project_id == project_id).all()]
    since = datetime.now(timezone.utc) - timedelta(hours=hours)

    if not queue_ids:
        return {"buckets": []}

    rows = (
        db.query(
            func.date_trunc('hour', models.JobExecution.finished_at).label("bucket"),
            models.JobExecution.status,
            func.count(models.JobExecution.id),
        )
        .join(models.Job, models.Job.id == models.JobExecution.job_id)
        .filter(models.Job.queue_id.in_(queue_ids), models.JobExecution.finished_at >= since)
        .group_by("bucket", models.JobExecution.status)
        .order_by("bucket")
        .all()
    )

    buckets: dict[str, dict] = {}
    for bucket, status, cnt in rows:
        key = bucket.isoformat()
        buckets.setdefault(key, {"timestamp": key, "completed": 0, "failed": 0})
        if status == models.JobStatus.COMPLETED:
            buckets[key]["completed"] = cnt
        elif status == models.JobStatus.FAILED:
            buckets[key]["failed"] = cnt

    return {"buckets": sorted(buckets.values(), key=lambda b: b["timestamp"])}
