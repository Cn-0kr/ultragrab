"""AI feature configuration (DeepSeek + SiliconFlow ASR). Loaded separately from core settings."""

from __future__ import annotations

import os
from pathlib import Path

try:
    from dotenv import load_dotenv

    _ENV_FILE = Path(__file__).resolve().parent.parent / ".env"
    load_dotenv(_ENV_FILE, override=True)
except Exception:
    pass


# ---------------------------------------------------------------------------
# DeepSeek (text LLM)
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# SiliconFlow ASR (speech-to-text fallback)
# ---------------------------------------------------------------------------

def siliconflow_api_key() -> str:
    return (os.getenv("SILICONFLOW_API_KEY") or "").strip()


def siliconflow_api_base() -> str:
    return (os.getenv("SILICONFLOW_API_BASE") or "https://api.siliconflow.cn").rstrip("/")


def siliconflow_asr_model() -> str:
    return (os.getenv("SILICONFLOW_ASR_MODEL") or "FunAudioLLM/SenseVoiceSmall").strip()
