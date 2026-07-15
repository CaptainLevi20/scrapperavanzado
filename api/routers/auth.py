import secrets
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy.orm import Session

from api.deps import require_session
from api.schemas import (
    AuthResponse,
    ChangePasswordRequest,
    LoginRequest,
    MeResponse,
    RegisterRequest,
)
from core.config import get_settings
from core.db import repository
from core.db.models import User
from core.db.session import get_db
from core.security import hash_password, hash_session_token, verify_password

router = APIRouter(prefix="/auth")


def _issue_session(db: Session, user_id: int) -> str:
    raw_token = secrets.token_urlsafe(32)
    repository.create_session(db, user_id=user_id, token_hash=hash_session_token(raw_token))
    return raw_token


@router.post("/register", response_model=AuthResponse)
def register(payload: RegisterRequest, db: Session = Depends(get_db)):
    settings = get_settings()
    if payload.invite_code != settings.registration_code:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Código de invitación inválido")
    if repository.get_user_by_username(db, payload.username) is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Ese nombre de usuario ya está en uso")

    user = repository.create_user(db, username=payload.username, password_hash=hash_password(payload.password))
    token = _issue_session(db, user.id)
    return {"token": token, "username": user.username}


@router.post("/login", response_model=AuthResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)):
    user = repository.get_user_by_username(db, payload.username)
    if user is None or not user.active or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Usuario o contraseña incorrectos")

    repository.touch_user_last_login(db, user.id)
    token = _issue_session(db, user.id)
    return {"token": token, "username": user.username}


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(
    authorization: Optional[str] = Header(None),
    db: Session = Depends(get_db),
    _user: User = Depends(require_session),
):
    token = (authorization or "").removeprefix("Bearer ")
    repository.delete_session(db, hash_session_token(token))


@router.post("/change-password", status_code=status.HTTP_204_NO_CONTENT)
def change_password(
    payload: ChangePasswordRequest,
    db: Session = Depends(get_db),
    user: User = Depends(require_session),
):
    if not verify_password(payload.current_password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="La contraseña actual no es correcta")
    repository.update_user_password(db, user.id, hash_password(payload.new_password))


@router.get("/me", response_model=MeResponse)
def me(user: User = Depends(require_session)):
    return {"username": user.username}
