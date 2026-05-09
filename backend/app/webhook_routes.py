"""Stripe Webhook receiver: signature verification + idempotent state sync."""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

import stripe
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse

from . import db
from .schemas import ErrorPayload
from .settings import settings

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/stripe", tags=["stripe"])


def _http_error(
    code: str,
    message: str,
    status_code: int = 400,
    hint: Optional[str] = None,
) -> HTTPException:
    payload = ErrorPayload(code=code, message=message, hint=hint).model_dump()
    return HTTPException(status_code=status_code, detail=payload)


@router.post("/webhook")
async def stripe_webhook(request: Request) -> JSONResponse:
    if not settings.stripe_webhook_secret or not settings.stripe_secret_key:
        raise _http_error(
            "webhook_disabled",
            "Webhook 未配置：缺少 STRIPE_WEBHOOK_SECRET 或 STRIPE_SECRET_KEY。",
            status_code=503,
        )
    stripe.api_key = settings.stripe_secret_key

    raw_body = await request.body()
    sig_header = request.headers.get("stripe-signature") or request.headers.get("Stripe-Signature")
    if not sig_header:
        raise _http_error("missing_signature", "Stripe-Signature header 缺失。", status_code=400)

    try:
        event = stripe.Webhook.construct_event(
            payload=raw_body,
            sig_header=sig_header,
            secret=settings.stripe_webhook_secret,
        )
    except ValueError as exc:
        raise _http_error("invalid_payload", f"Webhook 负载无法解析: {exc}", status_code=400) from exc
    except stripe.SignatureVerificationError as exc:  # type: ignore[attr-defined]
        logger.warning(
            "Stripe webhook signature failed (%s). Common fix: use the whsec_ from `stripe listen` "
            "(not Dashboard endpoint secret), save to backend/.env STRIPE_WEBHOOK_SECRET, restart uvicorn.",
            exc,
        )
        raise _http_error(
            "invalid_signature",
            "Webhook 签名校验失败。",
            status_code=400,
            hint=(
                "本地请运行 stripe listen --forward-to http://127.0.0.1:8000/api/stripe/webhook，"
                "将终端打印的 whsec_ 写入 STRIPE_WEBHOOK_SECRET 后重启后端；"
                "不要用 Dashboard 里生产/测试端点的签名密钥代替 CLI 输出的密钥。"
                "若已写入仍失败，检查系统/Anaconda 是否残留旧 STRIPE_WEBHOOK_SECRET（本应用已启用 .env override）。"
            ),
        ) from exc

    event_id = event.get("id") if isinstance(event, dict) else event["id"]
    event_type = event.get("type") if isinstance(event, dict) else event["type"]
    eid = str(event_id)

    if db.has_stripe_event(eid):
        return JSONResponse({"received": True, "deduplicated": True})

    obj = _event_data_object(event)

    try:
        _dispatch_event(str(event_type), obj)
    except Exception:
        logger.exception("webhook handler failed for event %s (%s)", event_id, event_type)
        raise _http_error("handler_error", "Webhook 处理失败，将由 Stripe 重试。", status_code=500)

    db.remember_event(eid, str(event_type))
    return JSONResponse({"received": True})


# ---------------------------------------------------------------------------
# Event dispatch
# ---------------------------------------------------------------------------

def _dispatch_event(event_type: str, obj: Dict[str, Any]) -> None:
    if event_type == "checkout.session.completed":
        _handle_checkout_completed(obj)
    elif event_type in {"customer.subscription.created", "customer.subscription.updated", "customer.subscription.deleted"}:
        _handle_subscription_change(obj)
    elif event_type in {
        "invoice.paid",
        "invoice.payment_failed",
        # 较新 API / CLI 可能投递的名称，与 invoice 对象处理一致
        "invoice.payment_succeeded",
    }:
        _handle_invoice_event(obj)
    else:
        logger.info("ignoring stripe event type=%s", event_type)


def _as_dict(obj: Any) -> Dict[str, Any]:
    """StripeObject 勿用 dict(obj)，会触发 KeyError；优先 to_dict()。"""
    if isinstance(obj, dict):
        return obj
    to_dict = getattr(obj, "to_dict", None)
    if callable(to_dict):
        return to_dict()  # type: ignore[no-any-return]
    try:
        return dict(obj)
    except Exception:
        raise


def _stripe_id(value: Any) -> Optional[str]:
    """Webhook 展开字段可能是 'sub_xxx' 或 {{'id': 'sub_xxx'}}。"""
    if value is None:
        return None
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        sid = value.get("id")
        return str(sid) if sid else None
    oid = getattr(value, "id", None)
    return str(oid) if oid else None


def _event_data_object(event: Any) -> Dict[str, Any]:
    if isinstance(event, dict):
        raw = (event.get("data") or {}).get("object")
    else:
        data = getattr(event, "data", None)
        raw = getattr(data, "object", None) if data is not None else None
    return _as_dict(raw)


def _resolve_user_id_from_session(obj: Dict[str, Any]) -> Optional[str]:
    """checkout.session.completed → user_id（来自 client_reference_id 或 metadata）。"""

    user_id = obj.get("client_reference_id")
    if user_id:
        return str(user_id)
    metadata = obj.get("metadata") or {}
    return metadata.get("user_id")


def _resolve_user_id_from_customer(customer_id: Optional[str]) -> Optional[str]:
    if not customer_id:
        return None
    user = db.get_user_by_customer_id(customer_id)
    return user.id if user else None


def _line_item_price_id(item: Dict[str, Any]) -> Optional[str]:
    """items[].price 可能是 price_xxx 字符串或 {{'id': ...}}（新 API 展开）。"""
    p = item.get("price")
    if p is None:
        return None
    if isinstance(p, str):
        return p
    if isinstance(p, dict):
        pid = p.get("id")
        return str(pid) if pid else None
    pid = getattr(p, "id", None)
    return str(pid) if pid else None


def _extract_subscription_fields(sub_obj: Dict[str, Any]) -> Dict[str, Any]:
    """Pull common fields out of a Stripe Subscription object."""

    items_raw = (sub_obj.get("items") or {}).get("data") or []
    price_id = None
    if items_raw:
        first = items_raw[0]
        first_d = _as_dict(first)
        price_id = _line_item_price_id(first_d)
    return {
        "id": sub_obj.get("id"),
        "status": sub_obj.get("status") or "unknown",
        "current_period_end": sub_obj.get("current_period_end"),
        "cancel_at_period_end": bool(sub_obj.get("cancel_at_period_end")),
        "price_id": price_id,
        "customer": _stripe_id(sub_obj.get("customer")),
    }


def _handle_checkout_completed(obj: Dict[str, Any]) -> None:
    user_id = _resolve_user_id_from_session(obj)
    customer_id = _stripe_id(obj.get("customer"))
    if not user_id:
        user_id = _resolve_user_id_from_customer(customer_id)
    if not user_id:
        logger.warning("checkout.session.completed without identifiable user (session=%s)", obj.get("id"))
        return
    if customer_id:
        user = db.get_user_by_id(user_id)
        if user and not user.stripe_customer_id:
            db.set_stripe_customer_id(user_id, customer_id)

    sub_id = _stripe_id(obj.get("subscription"))
    if not sub_id:
        return
    try:
        sub = stripe.Subscription.retrieve(sub_id)
    except Exception:
        logger.exception("failed to retrieve subscription %s", sub_id)
        return
    fields = _extract_subscription_fields(_as_dict(sub))
    db.upsert_subscription(
        user_id=user_id,
        stripe_subscription_id=str(fields["id"]),
        stripe_price_id=fields["price_id"],
        status=str(fields["status"]),
        current_period_end=fields["current_period_end"],
        cancel_at_period_end=fields["cancel_at_period_end"],
    )


def _handle_subscription_change(obj: Dict[str, Any]) -> None:
    fields = _extract_subscription_fields(obj)
    sub_id = fields["id"]
    if not sub_id:
        return
    customer_id = fields["customer"]
    user_id = _resolve_user_id_from_customer(customer_id)
    if user_id:
        db.upsert_subscription(
            user_id=user_id,
            stripe_subscription_id=str(sub_id),
            stripe_price_id=fields["price_id"],
            status=str(fields["status"]),
            current_period_end=fields["current_period_end"],
            cancel_at_period_end=fields["cancel_at_period_end"],
        )
    else:
        # 已存在的订阅记录：直接 update，不需要 user_id
        updated = db.update_subscription_by_stripe_id(
            stripe_subscription_id=str(sub_id),
            status=str(fields["status"]),
            current_period_end=fields["current_period_end"],
            cancel_at_period_end=fields["cancel_at_period_end"],
            stripe_price_id=fields["price_id"],
        )
        if not updated:
            logger.warning("subscription %s update missed: no user, no existing row", sub_id)


def _handle_invoice_event(obj: Dict[str, Any]) -> None:
    """invoice.paid / invoice.payment_failed 仅同步派生状态。

    最终 subscription 状态以 customer.subscription.updated 为准；这里只对 past_due
    等中间态做一次保险更新，便于前端立即看到。
    """

    sub_id = _stripe_id(obj.get("subscription"))
    if not sub_id:
        return
    try:
        sub = stripe.Subscription.retrieve(sub_id)
    except Exception:
        logger.exception("failed to retrieve subscription %s", sub_id)
        return
    fields = _extract_subscription_fields(_as_dict(sub))
    db.update_subscription_by_stripe_id(
        stripe_subscription_id=str(fields["id"]),
        status=str(fields["status"]),
        current_period_end=fields["current_period_end"],
        cancel_at_period_end=fields["cancel_at_period_end"],
        stripe_price_id=fields["price_id"],
    )
