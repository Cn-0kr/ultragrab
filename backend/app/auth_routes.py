"""Authentication routes: register / login / me."""

from __future__ import annotations

import logging
import sqlite3
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request

from . import db
from .billing_schemas import LoginRequest, MeResponse, RegisterRequest, SubscriptionView, TokenResponse
from .schemas import ErrorPayload
from .security import decode_token, hash_password, issue_token, verify_password
from .settings import settings

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/auth", tags=["auth"])


def _http_error(code: str, message: str, status_code: int = 400, hint: Optional[str] = None) -> HTTPException:
    payload = ErrorPayload(code=code, message=message, hint=hint).model_dump()
    return HTTPException(status_code=status_code, detail=payload)


def _require_jwt_configured() -> None:
    if not settings.jwt_secret:
        raise _http_error(
            "auth_disabled",
            "认证服务未配置：服务端缺少 JWT_SECRET。",
            status_code=503,
            hint="复制 backend/.env.example 中的 JWT_SECRET 到 .env 后重启。",
        )


def get_current_user(request: Request) -> db.UserRow:
    """FastAPI dependency: extract Bearer token, return UserRow."""

    _require_jwt_configured()
    auth = request.headers.get("authorization") or request.headers.get("Authorization")
    if not auth or not auth.lower().startswith("bearer "):
        raise _http_error("unauthorized", "缺少 Authorization Bearer token。", status_code=401)
    token = auth.split(None, 1)[1].strip()
    payload = decode_token(token)
    if not payload or "sub" not in payload:
        raise _http_error("invalid_token", "Token 无效或已过期，请重新登录。", status_code=401)
    user = db.get_user_by_id(str(payload["sub"]))
    if user is None:
        raise _http_error("invalid_token", "Token 对应的用户已不存在。", status_code=401)
    return user


@router.post("/register", response_model=TokenResponse)
async def register(payload: RegisterRequest) -> TokenResponse:
    _require_jwt_configured()
    email = payload.email.lower()
    existing = db.get_user_by_email(email)
    if existing is not None:
        raise _http_error("email_taken", "该邮箱已注册，请直接登录。", status_code=409)
    try:
        user = db.create_user(email=email, password_hash=hash_password(payload.password))
    except sqlite3.IntegrityError:
        # Race: parallel register on the same email.
        raise _http_error("email_taken", "该邮箱已注册，请直接登录。", status_code=409)
    token = issue_token(user.id, user.email)
    return TokenResponse(access_token=token, expires_in=settings.jwt_expires_seconds)


@router.post("/login", response_model=TokenResponse)
async def login(payload: LoginRequest) -> TokenResponse:
    _require_jwt_configured()
    user = db.get_user_by_email(payload.email.lower())
    if user is None or not verify_password(payload.password, user.password_hash):
        raise _http_error("invalid_credentials", "邮箱或密码不正确。", status_code=401)
    token = issue_token(user.id, user.email)
    return TokenResponse(access_token=token, expires_in=settings.jwt_expires_seconds)


@router.get("/me", response_model=MeResponse)
async def me(user: db.UserRow = Depends(get_current_user)) -> MeResponse:
    sub = db.get_active_subscription(user.id) or db.get_latest_subscription(user.id)
    sub_view: Optional[SubscriptionView] = None
    has_active = False
    if sub is not None:
        sub_view = SubscriptionView(
            status=sub.status,
            current_period_end=sub.current_period_end,
            cancel_at_period_end=bool(sub.cancel_at_period_end),
            stripe_price_id=sub.stripe_price_id,
        )
        has_active = sub.status in {"active", "trialing"}
    return MeResponse(
        id=user.id,
        email=user.email,
        has_active_subscription=has_active,
        subscription=sub_view,
    )
