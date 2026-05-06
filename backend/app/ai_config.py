"""AI feature configuration (DeepSeek). Loaded separately from core settings."""

from __future__ import annotations

import os
from pathlib import Path

try:
    from dotenv import load_dotenv

    _ENV_FILE = Path(__file__).resolve().parent.parent / ".env"
    load_dotenv(_ENV_FILE)
except Exception:
    pass


def deepseek_api_key() -> str:
    return (os.getenv("DEEPSEEK_API_KEY") or "").strip()


def deepseek_api_base() -> str:
    return (os.getenv("DEEPSEEK_API_BASE") or "https://api.deepseek.com").rstrip("/")


def deepseek_model() -> str:
    return (os.getenv("DEEPSEEK_MODEL") or "deepseek-chat").strip()


def ai_max_transcript_chars() -> int:
    raw = os.getenv("AI_MAX_TRANSCRIPT_CHARS", "120000")
    try:
        return max(8000, int(raw))
    except ValueError:
        return 120000
