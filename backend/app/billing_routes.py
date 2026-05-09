"""Stripe Checkout endpoint: creates Customer (if needed) + Subscription Session."""

from __future__ import annotations

import logging
from typing import Optional

import stripe
from fastapi import APIRouter, Depends, HTTPException

from . import db
from .auth_routes import get_current_user
from .billing_schemas import CheckoutResponse
from .schemas import ErrorPayload
from .settings import settings

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/billing", tags=["billing"])


def _http_error(code: str, message: str, status_code: int = 400, hint: Optional[str] = None) -> HTTPException:
    payload = ErrorPayload(code=code, message=message, hint=hint).model_dump()
    return HTTPException(status_code=status_code, detail=payload)


def _require_stripe_configured() -> None:
    missing = []
    if not settings.stripe_secret_key:
        missing.append("STRIPE_SECRET_KEY")
    if not settings.stripe_price_pro_monthly:
        missing.append("STRIPE_PRICE_PRO_MONTHLY")
    if missing:
        raise _http_error(
            "billing_disabled",
            "支付服务未配置：服务端缺少 " + ", ".join(missing) + "。",
            status_code=503,
            hint="复制 backend/.env.example 中相关变量到 .env 后重启。",
        )


@router.post("/checkout", response_model=CheckoutResponse)
async def create_checkout_session(user: db.UserRow = Depends(get_current_user)) -> CheckoutResponse:
    _require_stripe_configured()
    stripe.api_key = settings.stripe_secret_key

    # 已有活跃订阅 → 直接拒绝重复购买（避免被收两次月费）
    active = db.get_active_subscription(user.id)
    if active is not None:
        raise _http_error(
            "already_subscribed",
            "您已有活跃订阅，无需重复购买。",
            status_code=409,
            hint="如需调整支付方式或取消订阅，请使用账户管理入口。",
        )

    # 复用或新建 Stripe Customer
    customer_id = user.stripe_customer_id
    if not customer_id:
        try:
            customer = stripe.Customer.create(
                email=user.email,
                metadata={"app_user_id": user.id},
            )
        except stripe.StripeError as exc:  # type: ignore[attr-defined]
            logger.exception("stripe.Customer.create failed")
            raise _http_error(
                "stripe_error",
                f"Stripe 创建 Customer 失败：{exc.user_message or str(exc)}",
                status_code=502,
            ) from exc
        customer_id = customer.id
        db.set_stripe_customer_id(user.id, customer_id)

    origin = settings.public_frontend_origin.rstrip("/")
    success_url = f"{origin}/billing/success?session_id={{CHECKOUT_SESSION_ID}}"
    cancel_url = f"{origin}/#pricing"

    try:
        session = stripe.checkout.Session.create(
            mode="subscription",
            line_items=[{"price": settings.stripe_price_pro_monthly, "quantity": 1}],
            customer=customer_id,
            client_reference_id=user.id,
            metadata={"user_id": user.id},
            success_url=success_url,
            cancel_url=cancel_url,
            allow_promotion_codes=True,
        )
    except stripe.StripeError as exc:  # type: ignore[attr-defined]
        logger.exception("stripe.checkout.Session.create failed")
        raise _http_error(
            "stripe_error",
            f"Stripe 创建结账会话失败：{exc.user_message or str(exc)}",
            status_code=502,
        ) from exc

    if not session.url:
        raise _http_error(
            "stripe_error",
            "Stripe 未返回结账 URL，请稍后重试。",
            status_code=502,
        )
    return CheckoutResponse(url=session.url)
