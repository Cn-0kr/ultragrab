"""Centralised runtime configuration.

Values are read from environment variables (and optionally a local `.env` file).
The module exposes a single `settings` singleton used across the app.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

try:
    from dotenv import load_dotenv

    _ENV_FILE = Path(__file__).resolve().parent.parent / ".env"
    # 覆盖已存在的环境变量，避免本机/Anaconda 里残留的旧 STRIPE_WEBHOOK_SECRET 与 stripe listen 的 whsec 不一致。
    # 生产请依赖部署平台注入密钥；勿在镜像中放入含真实密钥的 .env。
    load_dotenv(_ENV_FILE, override=True)
except Exception:
    pass


def _env_int(key: str, default: int) -> int:
    raw = os.getenv(key)
    if raw is None or raw == "":
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _env_bool(key: str, default: bool) -> bool:
    raw = os.getenv(key)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _env_list(key: str, default: List[str]) -> List[str]:
    raw = os.getenv(key)
    if not raw:
        return default
    return [item.strip() for item in raw.split(",") if item.strip()]


def _env_stripe_value(key: str) -> str:
    """Strip whitespace/BOM and optional wrapping quotes (common .env paste issues)."""

    raw = (os.getenv(key) or "").strip()
    if raw.startswith("\ufeff"):
        raw = raw.lstrip("\ufeff").strip()
    if len(raw) >= 2 and raw[0] == raw[-1] and raw[0] in "\"'":
        raw = raw[1:-1].strip()
    return raw


@dataclass
class Settings:
    host: str = field(default_factory=lambda: os.getenv("HOST", "127.0.0.1"))
    port: int = field(default_factory=lambda: _env_int("PORT", 8000))

    download_dir: Path = field(
        default_factory=lambda: Path(os.getenv("DOWNLOAD_DIR", ".tmp_downloads")).resolve()
    )

    max_batch_urls: int = field(default_factory=lambda: _env_int("MAX_BATCH_URLS", 10))
    max_concurrent_downloads: int = field(
        default_factory=lambda: _env_int("MAX_CONCURRENT_DOWNLOADS", 3)
    )
    task_timeout: int = field(default_factory=lambda: _env_int("TASK_TIMEOUT", 600))
    file_retention: int = field(default_factory=lambda: _env_int("FILE_RETENTION", 3600))

    allow_redirect: bool = field(default_factory=lambda: _env_bool("ALLOW_REDIRECT", True))

    cors_origins: List[str] = field(
        default_factory=lambda: _env_list(
            "CORS_ORIGINS",
            [
                "http://localhost:5173",
                "http://127.0.0.1:5173",
            ],
        )
    )

    #: Netscape-format cookies.txt passed to yt-dlp (helps Bilibili CC when API requires login).
    ytdlp_cookie_file: Optional[str] = field(
        default_factory=lambda: (os.getenv("YTDLP_COOKIE_FILE") or "").strip() or None
    )

    # ---- Auth (JWT) ----
    jwt_secret: str = field(default_factory=lambda: (os.getenv("JWT_SECRET") or "").strip())
    jwt_expires_seconds: int = field(default_factory=lambda: _env_int("JWT_EXPIRES_SECONDS", 7 * 24 * 3600))

    # ---- Stripe ----
    stripe_secret_key: str = field(default_factory=lambda: _env_stripe_value("STRIPE_SECRET_KEY"))
    stripe_webhook_secret: str = field(default_factory=lambda: _env_stripe_value("STRIPE_WEBHOOK_SECRET"))
    stripe_price_pro_monthly: str = field(
        default_factory=lambda: (os.getenv("STRIPE_PRICE_PRO_MONTHLY") or "").strip()
    )
    public_frontend_origin: str = field(
        default_factory=lambda: (os.getenv("PUBLIC_FRONTEND_ORIGIN") or "http://127.0.0.1:5173").rstrip("/")
    )

    # ---- Billing DB ----
    billing_db_path: Path = field(
        default_factory=lambda: Path(
            os.getenv("BILLING_DB_PATH") or str(Path(__file__).resolve().parent.parent / "billing.db")
        ).resolve()
    )

    def ensure_dirs(self) -> None:
        self.download_dir.mkdir(parents=True, exist_ok=True)
        self.billing_db_path.parent.mkdir(parents=True, exist_ok=True)


settings = Settings()
settings.ensure_dirs()
