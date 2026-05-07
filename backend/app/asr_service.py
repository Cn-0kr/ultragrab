"""ASR fallback: extract audio via yt-dlp, transcribe via SiliconFlow API.

Used when platform subtitles are unavailable (e.g. Bilibili need_login_subtitle).
"""

from __future__ import annotations

import logging
import re
import shutil
from pathlib import Path
from typing import List, Optional, Tuple

import httpx
from yt_dlp import YoutubeDL
from yt_dlp.utils import DownloadError, ExtractorError

from .ai_config import siliconflow_api_base, siliconflow_api_key, siliconflow_asr_model
from .settings import settings
from .srt_parser import TranscriptCue
from .task_store import task_store
from .ytdlp_service import _yt_cookie_opts, has_ffmpeg

logger = logging.getLogger(__name__)

_MAX_AUDIO_DURATION = 3600  # SiliconFlow limit: 1 hour
_MAX_AUDIO_BYTES = 50 * 1024 * 1024  # SiliconFlow limit: 50 MB


def is_asr_configured() -> bool:
    return bool(siliconflow_api_key())


def extract_audio(webpage_url: str, task_id: str) -> Path:
    """Download audio-only stream via yt-dlp, return path to mp3 file."""

    out_dir = settings.download_dir / task_id / "_asr_audio"
    out_dir.mkdir(parents=True, exist_ok=True)

    postprocessors = []
    if has_ffmpeg():
        postprocessors.append({
            "key": "FFmpegExtractAudio",
            "preferredcodec": "mp3",
            "preferredquality": "64",
        })

    ydl_opts = {
        "quiet": True,
        "no_warnings": True,
        "noprogress": True,
        "format": "bestaudio/best",
        "outtmpl": str(out_dir / "audio.%(ext)s"),
        "retries": 2,
        "fragment_retries": 2,
        "nocheckcertificate": False,
        "postprocessors": postprocessors,
        **_yt_cookie_opts(),
    }

    try:
        with YoutubeDL(ydl_opts) as ydl:
            ydl.download([webpage_url])
    except (DownloadError, ExtractorError) as exc:
        raise RuntimeError(f"音频提取失败: {exc}") from exc

    candidates = sorted(out_dir.glob("audio.*"), key=lambda p: p.stat().st_size, reverse=True)
    if not candidates:
        raise RuntimeError("yt-dlp 未生成音频文件")

    audio_path = candidates[0]
    if audio_path.stat().st_size > _MAX_AUDIO_BYTES:
        raise RuntimeError(
            f"音频文件 {audio_path.stat().st_size / 1024 / 1024:.1f} MB 超过 SiliconFlow 50 MB 限制"
        )
    return audio_path


async def transcribe_audio(audio_path: Path) -> str:
    """Upload audio to SiliconFlow ASR and return transcribed text."""

    url = f"{siliconflow_api_base()}/v1/audio/transcriptions"
    headers = {"Authorization": f"Bearer {siliconflow_api_key()}"}

    timeout = httpx.Timeout(60.0, read=300.0)
    async with httpx.AsyncClient(timeout=timeout) as client:
        with audio_path.open("rb") as f:
            files = {"file": ("audio.mp3", f, "audio/mpeg")}
            data = {"model": siliconflow_asr_model()}
            resp = await client.post(url, headers=headers, files=files, data=data)

        if resp.status_code >= 400:
            logger.warning("SiliconFlow ASR error %s: %s", resp.status_code, resp.text[:500])
            resp.raise_for_status()

        body = resp.json()
        text = body.get("text") or body.get("transcription") or ""
        if not text.strip():
            raise RuntimeError("ASR 返回空文本，音频中可能无可识别语音")
        return text.strip()


def _split_into_sentences(text: str) -> List[str]:
    """Split text into sentence-level segments for cue generation."""

    segments = re.split(r'(?<=[。！？.!?\n])\s*', text)
    result = []
    for seg in segments:
        seg = seg.strip()
        if seg:
            result.append(seg)
    if not result:
        result = [text.strip()]
    return result


def build_cues_from_text(text: str, duration_seconds: Optional[float]) -> List[TranscriptCue]:
    """Convert plain text to TranscriptCue list with estimated timestamps."""

    sentences = _split_into_sentences(text)
    total_chars = sum(len(s) for s in sentences)
    if total_chars == 0:
        return []

    total_ms = int((duration_seconds or 600) * 1000)

    cues: List[TranscriptCue] = []
    cursor_ms = 0
    for idx, sentence in enumerate(sentences, start=1):
        proportion = len(sentence) / total_chars
        span_ms = max(int(total_ms * proportion), 500)
        start_ms = cursor_ms
        end_ms = min(cursor_ms + span_ms, total_ms)
        cues.append(TranscriptCue(index=idx, start_ms=start_ms, end_ms=end_ms, text=sentence))
        cursor_ms = end_ms

    return cues


async def asr_for_task(task_id: str) -> Tuple[List[TranscriptCue], str]:
    """Full ASR pipeline: extract audio -> transcribe -> build cues.

    Returns (cues, plain_text). Cleans up temp audio afterwards.
    """

    record = task_store.require(task_id)
    meta = record.metadata
    if meta is None or not meta.webpage_url:
        raise RuntimeError("task has no webpage_url for ASR")

    duration = meta.duration
    if duration and duration > _MAX_AUDIO_DURATION:
        raise RuntimeError(
            f"视频时长 {int(duration // 60)} 分钟超过 ASR 上限（60 分钟），无法转写"
        )

    logger.info("ASR fallback for task %s: extracting audio from %s", task_id, meta.webpage_url)

    import asyncio
    audio_path = await asyncio.to_thread(extract_audio, meta.webpage_url, task_id)

    try:
        logger.info("ASR fallback for task %s: transcribing %s", task_id, audio_path.name)
        text = await transcribe_audio(audio_path)
    finally:
        _cleanup_asr_audio(task_id)

    cues = build_cues_from_text(text, duration)
    logger.info("ASR fallback for task %s: got %d chars, %d cues", task_id, len(text), len(cues))
    return cues, text


def _cleanup_asr_audio(task_id: str) -> None:
    asr_dir = settings.download_dir / task_id / "_asr_audio"
    if asr_dir.exists():
        shutil.rmtree(asr_dir, ignore_errors=True)
