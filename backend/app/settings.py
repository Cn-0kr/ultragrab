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
    load_dotenv(_ENV_FILE)
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

    def ensure_dirs(self) -> None:
        self.download_dir.mkdir(parents=True, exist_ok=True)


settings = Settings()
settings.ensure_dirs()
