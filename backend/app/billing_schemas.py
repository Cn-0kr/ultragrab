"""Pydantic models specific to auth + billing routes."""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, EmailStr, Field


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=8, max_length=128)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=1, max_length=128)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int


class SubscriptionView(BaseModel):
    status: str
    current_period_end: Optional[int] = None
    cancel_at_period_end: bool = False
    stripe_price_id: Optional[str] = None


class MeResponse(BaseModel):
    id: str
    email: str
    has_active_subscription: bool
    subscription: Optional[SubscriptionView] = None


class CheckoutResponse(BaseModel):
    url: str
