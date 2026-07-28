import secrets
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
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
from core.rate_limit import check_rate_limit
from core.security import hash_password, hash_session_token, verify_password

router = APIRouter(prefix="/auth")

REGISTER_RATE_LIMIT = 5
REGISTER_RATE_LIMIT_WINDOW_SECONDS = 300


def _issue_session(db: Session, user_id: int) -> str:
    raw_token = secrets.token_urlsafe(32)
    repository.create_session(db, user_id=user_id, token_hash=hash_session_token(raw_token))
    return raw_token


@router.post("/register", response_model=AuthResponse)
def register(payload: RegisterRequest, request: Request, db: Session = Depends(get_db)):
    settings = get_settings()
    # The invite code has no purpose left once it's still the value shipped in
    # the source code — that's not "a secret nobody entered yet", it's public.
    # Refusing here (rather than failing to start the whole app) keeps every
    # other route working if this was never configured.
    if settings.registration_code == "changeme":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="El registro está deshabilitado: falta configurar el código de invitación en el servidor.",
        )
    client_ip = request.client.host if request.client else "unknown"
    if not check_rate_limit(f"register:{client_ip}", REGISTER_RATE_LIMIT, REGISTER_RATE_LIMIT_WINDOW_SECONDS):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Demasiados intentos de registro. Espera unos minutos e intenta de nuevo.",
        )
    # Constant-time comparison: a plain `!=` leaks how many leading characters
    # matched through response-timing differences, letting an attacker recover
    # the invite code one character at a time instead of having to guess it
    # whole. This code is meant to be shared/guessable in spirit (colleagues
    # typing it in), so the real protection is (1) not being the public
    # "changeme" default and (2) the rate limit above, not this alone.
    if not secrets.compare_digest(payload.invite_code, settings.registration_code):
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
    authorization: Optional[str] = Header(None),
    db: Session = Depends(get_db),
    user: User = Depends(require_session),
):
    if not verify_password(payload.current_password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="La contraseña actual no es correcta")
    repository.update_user_password(db, user.id, hash_password(payload.new_password))
    # Kick out anyone else using this account under the old password — a stolen
    # session is exactly what changing your password is meant to react to. The
    # request's own token is excluded so the person changing it isn't logged out
    # of their own current session.
    current_token = (authorization or "").removeprefix("Bearer ")
    repository.delete_sessions_for_user(db, user.id, except_token_hash=hash_session_token(current_token))


@router.get("/me", response_model=MeResponse)
def me(user: User = Depends(require_session)):
    return {"username": user.username}
