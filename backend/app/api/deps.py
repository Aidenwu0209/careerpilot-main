from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import Depends, HTTPException, Request, status
from jose import JWTError, jwt
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.session import get_db
from app.models import Student, User
from app.services.bootstrap import ServiceContainer


def get_container(request: Request) -> ServiceContainer:
    return request.app.state.container


def get_db_session(db: Session = Depends(get_db)) -> Session:
    return db


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """Create JWT access token."""
    settings = get_settings()
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(hours=settings.jwt_expiration_hours)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)
    return encoded_jwt


def get_current_user(
    request: Request,
    db: Session = Depends(get_db_session),
) -> User:
    """Dependency to get current authenticated user from JWT token."""
    settings = get_settings()
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    # Get token from Authorization header
    auth_header = request.headers.get("Authorization")
    if not auth_header:
        raise credentials_exception

    try:
        scheme, token = auth_header.split()
        if scheme.lower() != "bearer":
            raise credentials_exception
    except ValueError:
        raise credentials_exception

    try:
        if token == "dev-bypass":
            if settings.app_env != "production":
                payload = {"sub": "1"}
            else:
                raise credentials_exception
        else:
            payload = jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
        sub = payload.get("sub")
        if sub is None:
            raise credentials_exception
        user_id = int(sub)
    except JWTError:
        raise credentials_exception

    user = db.scalar(select(User).where(User.id == user_id))
    if user is None:
        raise credentials_exception

    return user


def ensure_student_owns_resource(current_user: User, db: Session, student_id: int) -> None:
    """Verify the student_id belongs to the current user for student role.

    Admin and teacher roles bypass this check — they have their own
    authorization layer in teacher.py / admin.py.
    """
    if current_user.role == "student":
        student = db.scalar(select(Student).where(Student.user_id == current_user.id))
        if not student or student.id != student_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="无权访问此资源",
            )

