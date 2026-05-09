"""SQLite billing store: users / subscriptions / stripe_events.

The billing DB is intentionally separate from the in-memory task store. It only
holds account + subscription state — no video metadata leaks here.
"""

from __future__ import annotations

import sqlite3
import threading
import time
import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator, Optional

from .settings import settings


_SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id TEXT PRIMARY KEY,
    email TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    stripe_customer_id TEXT,
    created_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS subscriptions (
    user_id TEXT NOT NULL,
    stripe_subscription_id TEXT PRIMARY KEY,
    stripe_price_id TEXT,
    status TEXT NOT NULL,
    current_period_end INTEGER,
    cancel_at_period_end INTEGER NOT NULL DEFAULT 0,
    updated_at INTEGER NOT NULL,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_subscriptions_user_id ON subscriptions(user_id);
CREATE INDEX IF NOT EXISTS idx_subscriptions_status ON subscriptions(status);

CREATE TABLE IF NOT EXISTS stripe_events (
    event_id TEXT PRIMARY KEY,
    type TEXT NOT NULL,
    received_at INTEGER NOT NULL
);
"""


@dataclass
class UserRow:
    id: str
    email: str
    password_hash: str
    stripe_customer_id: Optional[str]
    created_at: int


@dataclass
class SubscriptionRow:
    user_id: str
    stripe_subscription_id: str
    stripe_price_id: Optional[str]
    status: str
    current_period_end: Optional[int]
    cancel_at_period_end: int
    updated_at: int


_ACTIVE_STATUSES = {"active", "trialing"}

_lock = threading.RLock()
_initialized = False


def _path() -> Path:
    return settings.billing_db_path


def _ensure_initialized() -> None:
    global _initialized
    if _initialized:
        return
    with _lock:
        if _initialized:
            return
        path = _path()
        path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(str(path)) as conn:
            conn.executescript(_SCHEMA)
            conn.commit()
        _initialized = True


@contextmanager
def connect() -> Iterator[sqlite3.Connection]:
    _ensure_initialized()
    conn = sqlite3.connect(str(_path()))
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("PRAGMA foreign_keys = ON")
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


# ---- users ----------------------------------------------------------------

def create_user(email: str, password_hash: str) -> UserRow:
    user_id = str(uuid.uuid4())
    now = int(time.time())
    with connect() as conn:
        conn.execute(
            "INSERT INTO users (id, email, password_hash, stripe_customer_id, created_at) VALUES (?, ?, ?, NULL, ?)",
            (user_id, email.lower(), password_hash, now),
        )
    return UserRow(id=user_id, email=email.lower(), password_hash=password_hash, stripe_customer_id=None, created_at=now)


def get_user_by_email(email: str) -> Optional[UserRow]:
    with connect() as conn:
        row = conn.execute(
            "SELECT id, email, password_hash, stripe_customer_id, created_at FROM users WHERE email = ?",
            (email.lower(),),
        ).fetchone()
    return _row_to_user(row)


def get_user_by_id(user_id: str) -> Optional[UserRow]:
    with connect() as conn:
        row = conn.execute(
            "SELECT id, email, password_hash, stripe_customer_id, created_at FROM users WHERE id = ?",
            (user_id,),
        ).fetchone()
    return _row_to_user(row)


def set_stripe_customer_id(user_id: str, customer_id: str) -> None:
    with connect() as conn:
        conn.execute(
            "UPDATE users SET stripe_customer_id = ? WHERE id = ?",
            (customer_id, user_id),
        )


def get_user_by_customer_id(customer_id: str) -> Optional[UserRow]:
    with connect() as conn:
        row = conn.execute(
            "SELECT id, email, password_hash, stripe_customer_id, created_at FROM users WHERE stripe_customer_id = ?",
            (customer_id,),
        ).fetchone()
    return _row_to_user(row)


def _row_to_user(row: Optional[sqlite3.Row]) -> Optional[UserRow]:
    if row is None:
        return None
    return UserRow(
        id=row["id"],
        email=row["email"],
        password_hash=row["password_hash"],
        stripe_customer_id=row["stripe_customer_id"],
        created_at=row["created_at"],
    )


# ---- subscriptions --------------------------------------------------------

def upsert_subscription(
    user_id: str,
    stripe_subscription_id: str,
    stripe_price_id: Optional[str],
    status: str,
    current_period_end: Optional[int],
    cancel_at_period_end: bool,
) -> None:
    now = int(time.time())
    with connect() as conn:
        conn.execute(
            """
            INSERT INTO subscriptions (
                user_id, stripe_subscription_id, stripe_price_id, status,
                current_period_end, cancel_at_period_end, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(stripe_subscription_id) DO UPDATE SET
                stripe_price_id = excluded.stripe_price_id,
                status = excluded.status,
                current_period_end = excluded.current_period_end,
                cancel_at_period_end = excluded.cancel_at_period_end,
                updated_at = excluded.updated_at
            """,
            (
                user_id,
                stripe_subscription_id,
                stripe_price_id,
                status,
                current_period_end,
                1 if cancel_at_period_end else 0,
                now,
            ),
        )


def update_subscription_by_stripe_id(
    stripe_subscription_id: str,
    status: str,
    current_period_end: Optional[int],
    cancel_at_period_end: bool,
    stripe_price_id: Optional[str] = None,
) -> bool:
    now = int(time.time())
    with connect() as conn:
        cur = conn.execute(
            """
            UPDATE subscriptions
               SET status = ?,
                   current_period_end = ?,
                   cancel_at_period_end = ?,
                   stripe_price_id = COALESCE(?, stripe_price_id),
                   updated_at = ?
             WHERE stripe_subscription_id = ?
            """,
            (status, current_period_end, 1 if cancel_at_period_end else 0, stripe_price_id, now, stripe_subscription_id),
        )
        return cur.rowcount > 0


def get_active_subscription(user_id: str) -> Optional[SubscriptionRow]:
    placeholders = ",".join(["?"] * len(_ACTIVE_STATUSES))
    with connect() as conn:
        row = conn.execute(
            f"""
            SELECT user_id, stripe_subscription_id, stripe_price_id, status,
                   current_period_end, cancel_at_period_end, updated_at
              FROM subscriptions
             WHERE user_id = ? AND status IN ({placeholders})
             ORDER BY updated_at DESC
             LIMIT 1
            """,
            (user_id, *_ACTIVE_STATUSES),
        ).fetchone()
    return _row_to_subscription(row)


def get_latest_subscription(user_id: str) -> Optional[SubscriptionRow]:
    with connect() as conn:
        row = conn.execute(
            """
            SELECT user_id, stripe_subscription_id, stripe_price_id, status,
                   current_period_end, cancel_at_period_end, updated_at
              FROM subscriptions
             WHERE user_id = ?
             ORDER BY updated_at DESC
             LIMIT 1
            """,
            (user_id,),
        ).fetchone()
    return _row_to_subscription(row)


def _row_to_subscription(row: Optional[sqlite3.Row]) -> Optional[SubscriptionRow]:
    if row is None:
        return None
    return SubscriptionRow(
        user_id=row["user_id"],
        stripe_subscription_id=row["stripe_subscription_id"],
        stripe_price_id=row["stripe_price_id"],
        status=row["status"],
        current_period_end=row["current_period_end"],
        cancel_at_period_end=row["cancel_at_period_end"],
        updated_at=row["updated_at"],
    )


# ---- stripe events (idempotency) -----------------------------------------

def has_stripe_event(event_id: str) -> bool:
    """是否已成功处理过该事件（用于幂等，须在业务成功后调用 remember_event）。"""

    _ensure_initialized()
    with connect() as conn:
        row = conn.execute(
            "SELECT 1 FROM stripe_events WHERE event_id = ? LIMIT 1",
            (event_id,),
        ).fetchone()
    return row is not None


def remember_event(event_id: str, event_type: str) -> None:
    """业务处理成功后写入，保证失败重试不会因 dedupe 而跳过处理。"""

    now = int(time.time())
    with connect() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO stripe_events (event_id, type, received_at) VALUES (?, ?, ?)",
            (event_id, event_type, now),
        )
