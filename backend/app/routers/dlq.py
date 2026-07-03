from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app import models, schemas
from app.database import get_db
from app.core.security import get_current_user, require_project_access
from app.services import job_service

router = APIRouter(prefix="/api/v1/projects/{project_id}/dead-letter", tags=["dead-letter-queue"])


@router.get("", response_model=list[schemas.DeadLetterOut])
def list_dead_letters(project_id: str, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    require_project_access(project_id, db, user)
    queue_ids = [q.id for q in db.query(models.Queue).filter(models.Queue.project_id == project_id).all()]
    return (db.query(models.DeadLetterJob).filter(models.DeadLetterJob.queue_id.in_(queue_ids))
            .order_by(models.DeadLetterJob.failed_at.desc()).all())


@router.post("/{dlq_id}/replay", response_model=schemas.JobOut)
def replay(project_id: str, dlq_id: str, db: Session = Depends(get_db),
           user: models.User = Depends(get_current_user)):
    require_project_access(project_id, db, user)
    entry = db.query(models.DeadLetterJob).filter(models.DeadLetterJob.id == dlq_id).first()
    if not entry:
        raise HTTPException(status_code=404, detail="Dead letter entry not found")
    if entry.replayed:
        raise HTTPException(status_code=400, detail="Already replayed")
    return job_service.replay_dead_letter(db, entry)
