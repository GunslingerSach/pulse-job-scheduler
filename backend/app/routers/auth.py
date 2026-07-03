import secrets

from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from app import models, schemas
from app.database import get_db
from app.core.security import hash_password, verify_password, create_access_token, get_current_user

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


@router.post("/register", response_model=schemas.Token, status_code=201)
def register(payload: schemas.UserCreate, db: Session = Depends(get_db)):
    if db.query(models.User).filter(models.User.email == payload.email).first():
        raise HTTPException(status_code=400, detail="Email already registered")

    user = models.User(email=payload.email, hashed_password=hash_password(payload.password),
                        full_name=payload.full_name)
    db.add(user)
    db.flush()

    org = models.Organization(name=payload.organization_name, owner_id=user.id)
    db.add(org)
    db.flush()

    membership = models.OrganizationMember(organization_id=org.id, user_id=user.id, role=models.UserRole.ADMIN)
    db.add(membership)

    default_project = models.Project(organization_id=org.id, name="Default Project",
                                      api_key=secrets.token_hex(24))
    db.add(default_project)
    db.commit()

    token = create_access_token(subject=user.id)
    return schemas.Token(access_token=token)


@router.post("/login", response_model=schemas.Token)
def login(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.email == form_data.username).first()
    if not user or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Incorrect email or password")
    token = create_access_token(subject=user.id)
    return schemas.Token(access_token=token)


@router.get("/me", response_model=schemas.UserOut)
def me(current_user: models.User = Depends(get_current_user)):
    return current_user
