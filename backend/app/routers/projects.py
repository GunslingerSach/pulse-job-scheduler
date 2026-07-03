import secrets

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app import models, schemas
from app.database import get_db
from app.core.security import get_current_user

router = APIRouter(prefix="/api/v1/projects", tags=["projects"])


@router.post("", response_model=schemas.ProjectOut, status_code=201)
def create_project(payload: schemas.ProjectCreate, db: Session = Depends(get_db),
                    user: models.User = Depends(get_current_user)):
    membership = (
        db.query(models.OrganizationMember)
        .filter(models.OrganizationMember.organization_id == payload.organization_id,
                models.OrganizationMember.user_id == user.id)
        .first()
    )
    if not membership:
        raise HTTPException(status_code=403, detail="Not a member of this organization")

    project = models.Project(organization_id=payload.organization_id, name=payload.name,
                              description=payload.description, api_key=secrets.token_hex(24))
    db.add(project)
    db.commit()
    db.refresh(project)
    return project


@router.get("", response_model=list[schemas.ProjectOut])
def list_projects(db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    org_ids = [m.organization_id for m in user.memberships]
    return db.query(models.Project).filter(models.Project.organization_id.in_(org_ids)).all()


@router.get("/{project_id}", response_model=schemas.ProjectOut)
def get_project(project_id: str, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    from app.core.security import require_project_access
    return require_project_access(project_id, db, user)
