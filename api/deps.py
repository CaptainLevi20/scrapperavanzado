from typing import Optional

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy.orm import Session

from core.db import repository
from core.db.models import User
from core.db.session import get_db
from core.security import hash_session_token


def require_session(
    authorization: Optional[str] = Header(None),
    db: Session = Depends(get_db),
) -> User:
    if authorization is None or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Sesión inválida")
    token = authorization.removeprefix("Bearer ")
    session = repository.get_valid_session_by_token_hash(db, hash_session_token(token))
    if session is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Sesión inválida o expirada")
    repository.touch_session(db, session.id)
    return db.get(User, session.user_id)
