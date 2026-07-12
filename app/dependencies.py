from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import User, UserRole
from app.security import decode_access_token

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login", auto_error=False)


def get_current_user(
    token: str | None = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> User:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if token is None:
        raise credentials_exception

    payload = decode_access_token(token)
    if payload is None or "sub" not in payload:
        raise credentials_exception

    user = db.get(User, payload["sub"])
    if user is None or not user.is_active:
        raise credentials_exception
    return user


def require_recruiter(current_user: User = Depends(get_current_user)) -> User:
    if current_user.role != UserRole.RECRUITER:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This action requires recruiter/HR privileges",
        )
    return current_user


def require_candidate(current_user: User = Depends(get_current_user)) -> User:
    if current_user.role != UserRole.CANDIDATE:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This action requires a candidate account",
        )
    return current_user


def get_optional_user(
    token: str | None = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> User | None:
    """Used on public endpoints that behave differently for authenticated recruiters (e.g. job listing)."""
    if token is None:
        return None
    payload = decode_access_token(token)
    if payload is None or "sub" not in payload:
        return None
    return db.get(User, payload["sub"])
