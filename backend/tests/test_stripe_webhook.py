"""本地可重复的 Webhook 签名校验与 dotenv 覆盖行为验证（无需连接 Stripe）。"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import time

import stripe
from fastapi.testclient import TestClient


def _sign_stripe_webhook(payload: str, secret: str) -> str:
    """与 stripe._webhook.WebhookSignature 相同的 v1 签名规则。"""
    ts = int(time.time())
    signed_payload = f"{ts}.{payload}"
    sig = hmac.new(
        secret.encode("utf-8"),
        signed_payload.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return f"t={ts},v1={sig}"


def test_dotenv_override_true_overwrites_stale_os_env(tmp_path, monkeypatch) -> None:
    """runtime 证据：override=True 时 .env 覆盖本机已存在的同名变量。"""
    from dotenv import load_dotenv

    env_file = tmp_path / ".env"
    env_file.write_text("STRIPE_WEBHOOK_SECRET=whsec_from_dotenv\n", encoding="utf-8")
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", "whsec_from_os_stale")
    load_dotenv(env_file, override=True)
    assert os.environ["STRIPE_WEBHOOK_SECRET"] == "whsec_from_dotenv"


def test_stripe_webhook_accepts_locally_signed_payload() -> None:
    """本地生成合法 Stripe-Signature，应返回 200 + received（证明路由与密钥逻辑可用）。"""
    from app.main import app
    from app.settings import settings

    secret = "whsec_local_test_" + "a" * 48
    prev_wh = settings.stripe_webhook_secret
    prev_sk = settings.stripe_secret_key
    settings.stripe_webhook_secret = secret
    settings.stripe_secret_key = "sk_test_local_dummy"

    payload_dict = {
        "id": f"evt_test_py_{int(time.time() * 1000)}",
        "object": "event",
        "api_version": "2020-08-27",
        "type": "ping",
        "data": {"object": {"object": "ping", "id": "pong"}},
    }
    payload = json.dumps(payload_dict, separators=(",", ":"))
    sig_header = _sign_stripe_webhook(payload, secret)

    client = TestClient(app)
    try:
        r = client.post(
            "/api/stripe/webhook",
            content=payload.encode("utf-8"),
            headers={
                "stripe-signature": sig_header,
                "content-type": "application/json",
            },
        )
        assert r.status_code == 200, r.text
        assert r.json().get("received") is True
    finally:
        settings.stripe_webhook_secret = prev_wh
        settings.stripe_secret_key = prev_sk


def test_as_dict_prefers_to_dict_for_stripe_subscription() -> None:
    """stripe.Subscription.retrieve 返回 StripeObject：dict(sub) 会 KeyError: 0，须走 to_dict()。"""
    from app.webhook_routes import _as_dict, _extract_subscription_fields

    sub = stripe.Subscription.construct_from(
        {
            "id": "sub_test_conv",
            "object": "subscription",
            "status": "active",
            "customer": "cus_test",
            "current_period_end": 1700000000,
            "cancel_at_period_end": False,
            "items": {"object": "list", "data": [{"id": "si_x", "price": {"id": "price_test"}}]},
        },
        stripe.api_key,
    )
    d = _as_dict(sub)
    assert d["id"] == "sub_test_conv"
    fields = _extract_subscription_fields(d)
    assert fields["price_id"] == "price_test"
    assert fields["customer"] == "cus_test"
