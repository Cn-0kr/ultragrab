"""Password hashing + JWT helpers for auth flows."""

from __future__ import annotations

import time
from typing import Optional

import jwt
from passlib.context import CryptContext

from .settings import settings


_pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

_JWT_ALG = "HS256"


def hash_password(password: str) -> str:
    return _pwd_context.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return _pwd_context.verify(password, password_hash)
    except Exception:
        return False


def issue_token(user_id: str, email: str) -> str:
    if not settings.jwt_secret:
        raise RuntimeError("JWT_SECRET is not configured")
    now = int(time.time())
    payload = {
        "sub": user_id,
        "email": email,
        "iat": now,
        "exp": now + settings.jwt_expires_seconds,
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=_JWT_ALG)


def decode_token(token: str) -> Optional[dict]:
    if not settings.jwt_secret:
        return None
    try:
        return jwt.decode(token, settings.jwt_secret, algorithms=[_JWT_ALG])
    except jwt.PyJWTError:
        return None
