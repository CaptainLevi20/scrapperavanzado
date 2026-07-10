from fastapi import Depends, Header, HTTPException, status
from sqlalchemy.orm import Session

from core.db import repository
from core.db.session import get_db
from core.security import hash_api_key


def require_api_key(
    x_api_key: str = Header(..., alias="X-API-Key"),
    db: Session = Depends(get_db),
):
    api_key = repository.get_active_api_key_by_hash(db, hash_api_key(x_api_key))
    if api_key is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="API key inválida")
    return api_key
