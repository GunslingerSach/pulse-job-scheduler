from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Header
from sqlalchemy.orm import Session

from app import models, schemas
from app.database import get_db
from app.services import job_service

router = APIRouter(prefix="/api/v1/workers", tags=["workers"])

# NOTE: worker endpoints authenticate via a project API key header (x-api-key)
# rather than a user JWT, since these calls are made by unattended worker
# processes, not logged-in dashboard users.

ApiKeyHeader = Header(..., alias="x-api-key")


def _authenticate_project(api_key: str, db: Session) -> models.Project:
    project = db.query(models.Project).filter(models.Project.api_key == api_key).first()
    if not project:
        raise HTTPException(status_code=401, detail="Invalid API key")
    return project


@router.post("/register", response_model=schemas.WorkerOut, status_code=201)
def register_worker(payload: schemas.WorkerRegister, db: Session = Depends(get_db), x_api_key: str = ApiKeyHeader):
    _authenticate_project(x_api_key, db)
    worker = models.Worker(name=payload.name, hostname=payload.hostname, concurrency=payload.concurrency,
                            queues_subscribed=payload.queues_subscribed, status=models.WorkerStatus.IDLE,
                            last_heartbeat_at=datetime.now(timezone.utc))
    db.add(worker)
    db.commit()
    db.refresh(worker)
    return worker


@router.post("/{worker_id}/heartbeat", response_model=schemas.WorkerOut)
def heartbeat(worker_id: str, payload: schemas.WorkerHeartbeatIn, db: Session = Depends(get_db),
              x_api_key: str = ApiKeyHeader):
    _authenticate_project(x_api_key, db)
    worker = db.query(models.Worker).filter(models.Worker.id == worker_id).first()
    if not worker:
        raise HTTPException(status_code=404, detail="Worker not found")
    worker.last_heartbeat_at = datetime.now(timezone.utc)
    worker.current_load = payload.active_jobs
    worker.status = models.WorkerStatus.ACTIVE if payload.active_jobs > 0 else models.WorkerStatus.IDLE
    db.add(models.WorkerHeartbeat(worker_id=worker.id, active_jobs=payload.active_jobs,
                                   cpu_usage=payload.cpu_usage, memory_usage_mb=payload.memory_usage_mb))
    db.commit()
    db.refresh(worker)
    return worker


@router.post("/{worker_id}/drain", response_model=schemas.WorkerOut)
def drain_worker(worker_id: str, db: Session = Depends(get_db), x_api_key: str = ApiKeyHeader):
    """Marks a worker as draining so the dashboard shows it's mid graceful-shutdown."""
    _authenticate_project(x_api_key, db)
    worker = db.query(models.Worker).filter(models.Worker.id == worker_id).first()
    if not worker:
        raise HTTPException(status_code=404, detail="Worker not found")
    worker.status = models.WorkerStatus.DRAINING
    db.commit()
    db.refresh(worker)
    return worker


@router.post("/{worker_id}/shutdown", response_model=schemas.WorkerOut)
def shutdown_worker(worker_id: str, db: Session = Depends(get_db), x_api_key: str = ApiKeyHeader):
    _authenticate_project(x_api_key, db)
    worker = db.query(models.Worker).filter(models.Worker.id == worker_id).first()
    if not worker:
        raise HTTPException(status_code=404, detail="Worker not found")
    worker.status = models.WorkerStatus.OFFLINE
    db.commit()
    db.refresh(worker)
    return worker


@router.get("", response_model=list[schemas.WorkerOut])
def list_workers(db: Session = Depends(get_db), x_api_key: str = ApiKeyHeader):
    _authenticate_project(x_api_key, db)
    return db.query(models.Worker).order_by(models.Worker.started_at.desc()).all()


@router.post("/{worker_id}/claim", response_model=list[schemas.JobOut])
def claim(worker_id: str, payload: schemas.ClaimRequest, db: Session = Depends(get_db),
          x_api_key: str = ApiKeyHeader):
    """Atomically claim up to `max_jobs` runnable jobs for this worker.
    See job_service.claim_jobs for the SELECT FOR UPDATE SKIP LOCKED logic."""
    _authenticate_project(x_api_key, db)
    worker = db.query(models.Worker).filter(models.Worker.id == worker_id).first()
    if not worker:
        raise HTTPException(status_code=404, detail="Worker not found")
    jobs = job_service.claim_jobs(db, worker, payload.queue_ids, payload.max_jobs)
    return jobs


@router.post("/{worker_id}/jobs/{job_id}/start", response_model=schemas.JobExecutionOut)
def start_job(worker_id: str, job_id: str, db: Session = Depends(get_db), x_api_key: str = ApiKeyHeader):
    _authenticate_project(x_api_key, db)
    worker = db.query(models.Worker).filter(models.Worker.id == worker_id).first()
    job = db.query(models.Job).filter(models.Job.id == job_id).first()
    if not worker or not job:
        raise HTTPException(status_code=404, detail="Worker or job not found")
    return job_service.start_execution(db, job, worker)


@router.post("/{worker_id}/jobs/{job_id}/complete", response_model=schemas.JobOut)
def complete_job(worker_id: str, job_id: str, execution_id: str, result: dict, db: Session = Depends(get_db),
                  x_api_key: str = ApiKeyHeader):
    _authenticate_project(x_api_key, db)
    job = db.query(models.Job).filter(models.Job.id == job_id).first()
    execution = db.query(models.JobExecution).filter(models.JobExecution.id == execution_id).first()
    if not job or not execution:
        raise HTTPException(status_code=404, detail="Job or execution not found")
    job_service.complete_execution(db, job, execution, result)
    db.refresh(job)
    return job


@router.post("/{worker_id}/jobs/{job_id}/fail", response_model=schemas.JobOut)
def fail_job(worker_id: str, job_id: str, execution_id: str, error_message: str, db: Session = Depends(get_db),
             x_api_key: str = ApiKeyHeader, stacktrace: str | None = None):
    _authenticate_project(x_api_key, db)
    job = db.query(models.Job).filter(models.Job.id == job_id).first()
    execution = db.query(models.JobExecution).filter(models.JobExecution.id == execution_id).first()
    if not job or not execution:
        raise HTTPException(status_code=404, detail="Job or execution not found")
    job_service.fail_execution(db, job, execution, error_message, stacktrace)
    db.refresh(job)
    return job
