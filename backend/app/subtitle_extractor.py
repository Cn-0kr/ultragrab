"""Download platform subtitles only (no media) via yt-dlp and parse to cues."""

from __future__ import annotations

import logging
import shutil
from pathlib import Path
from typing import List, Optional, Sequence, Tuple

from yt_dlp import YoutubeDL
from yt_dlp.utils import DownloadError, ExtractorError

from .schemas import SubtitleLanguage
from .settings import settings
from .srt_parser import TranscriptCue, parse_srt
from .task_store import TaskRecord, task_store
from .ytdlp_service import _yt_cookie_opts, validate_url

logger = logging.getLogger(__name__)

_PREFERENCE = ("zh-Hans", "zh-Hant", "zh-CN", "zh-TW", "zh", "en")


def resolve_subtitle_langs(
    subtitles: Sequence[SubtitleLanguage],
    requested: Optional[List[str]],
) -> List[str]:
    manual = [s.code for s in subtitles if not s.is_automatic]
    seen = set(manual)
    auto_extra = [s.code for s in subtitles if s.is_automatic and s.code not in seen]
    allowed_ordered = list(manual) + auto_extra
    if not allowed_ordered:
        return []

    if requested:
        wanted = [x.strip() for x in requested if x.strip()]
        cleaned = [c for c in wanted if c in allowed_ordered]
        if cleaned:
            return cleaned
        raise ValueError(
            "subtitle_langs must be a subset of languages returned by /api/parse for this task."
        )

    for pref in _PREFERENCE:
        if pref in allowed_ordered:
            return [pref]
    return [allowed_ordered[0]]


def _pick_srt_file(out_dir: Path, langs: Sequence[str]) -> Optional[Path]:
    paths = sorted(out_dir.glob("*.srt"))
    if not paths:
        return None
    for lang in langs:
        needle = f".{lang.lower()}.srt"
        for p in paths:
            if p.name.lower().endswith(needle) or f".{lang.lower()}." in p.name.lower():
                return p
    return paths[0]


def fetch_subtitles_to_cues(task_id: str, langs: List[str]) -> List[TranscriptCue]:
    """blocking: yt-dlp subtitle download + parse."""

    record = task_store.require(task_id)
    meta = record.metadata
    if meta is None or not meta.webpage_url:
        raise RuntimeError("task has no webpage_url")

    validate_url(meta.webpage_url)

    out_dir = settings.download_dir / task_id / "_ai_subs"
    out_dir.mkdir(parents=True, exist_ok=True)
    for stale in out_dir.glob("*"):
        try:
            if stale.is_file():
                stale.unlink(missing_ok=True)
            elif stale.is_dir():
                shutil.rmtree(stale, ignore_errors=True)
        except Exception:
            logger.debug("cleanup stale ignored %s", stale)

    ydl_opts = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "writesubtitles": True,
        "writeautomaticsub": True,
        "subtitleslangs": langs,
        "subtitlesformat": "srt",
        "outtmpl": str(out_dir / "%(title).100s [%(id)s].%(ext)s"),
        "noprogress": True,
        "nocheckcertificate": False,
        "retries": 2,
        "fragment_retries": 2,
        **_yt_cookie_opts(),
    }

    try:
        with YoutubeDL(ydl_opts) as ydl:
            ydl.download([meta.webpage_url])
    except (DownloadError, ExtractorError) as exc:
        logger.info("subtitle-only download failed: %s", exc)
        raise RuntimeError(str(exc) or "yt-dlp subtitle download failed") from exc

    path = _pick_srt_file(out_dir, langs)
    if path is None:
        return []

    raw = path.read_text(encoding="utf-8", errors="replace")
    cues = parse_srt(raw)
    return cues


def resolve_langs_for_task(task_id: str, subtitle_langs: Optional[List[str]]) -> List[str]:
    record: TaskRecord = task_store.require(task_id)
    langs = resolve_subtitle_langs(record.subtitles, subtitle_langs)
    if not langs:
        raise RuntimeError("no subtitles available for this video")
    return langs


def cues_from_task(task_id: str, subtitle_langs: Optional[List[str]]) -> Tuple[List[str], List[TranscriptCue]]:
    langs = resolve_langs_for_task(task_id, subtitle_langs)
    cues = fetch_subtitles_to_cues(task_id, langs)
    if not cues:
        raise RuntimeError("subtitle files were empty or missing")
    return langs, cues
