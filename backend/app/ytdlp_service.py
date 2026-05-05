"""yt-dlp wrapper.

Policy: we wrap yt-dlp, we do not modify it. The rest of the app never imports
yt_dlp directly; everything goes through this module.
"""

from __future__ import annotations

import ipaddress
import logging
import re
import shutil
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse

import httpx
from yt_dlp import YoutubeDL
from yt_dlp.utils import DownloadError, ExtractorError

from . import douyin_service
from .schemas import (
    ErrorPayload,
    FormatOption,
    ParseResult,
    SubtitleLanguage,
    VideoMetadata,
)
from .task_store import FormatRecord, TaskRecord, task_store

logger = logging.getLogger(__name__)


_ALLOWED_SCHEMES = {"http", "https"}
_FILENAME_SANITIZE = re.compile(r"[\\/:*?\"<>|\r\n\t]+")


def has_ffmpeg() -> bool:
    return shutil.which("ffmpeg") is not None


def validate_url(url: str) -> None:
    """Reject anything that could obviously reach local/private networks or weird schemes.

    We intentionally do NOT do DNS resolution: end users often run behind proxies
    (Clash, etc.) that rewrite DNS answers into reserved ranges like 198.18.0.0/15.
    Doing getaddrinfo here would false-positive legitimate public hostnames.
    yt-dlp will fail properly if the URL truly cannot be reached.
    """

    parsed = urlparse(url)
    if parsed.scheme.lower() not in _ALLOWED_SCHEMES:
        raise ClientError("invalid_url", f"Only http/https URLs are allowed (got {parsed.scheme}).")
    host = parsed.hostname
    if not host:
        raise ClientError("invalid_url", "URL is missing a hostname.")
    host_lower = host.lower().strip("[]")
    if host_lower in {"localhost", "localhost.localdomain", "0.0.0.0"}:
        raise ClientError("invalid_url", "Loopback hosts are not allowed.")
    try:
        ip = ipaddress.ip_address(host_lower)
    except ValueError:
        return
    if _ip_is_private(ip):
        raise ClientError("invalid_url", "Private / loopback IP literals are not allowed.")


def _ip_is_private(ip: "ipaddress._BaseAddress") -> bool:
    return (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_unspecified
    )


class ClientError(Exception):
    def __init__(self, code: str, message: str, hint: Optional[str] = None) -> None:
        super().__init__(message)
        self.payload = ErrorPayload(code=code, message=message, hint=hint)


def _translate_ytdlp_error(err: Exception) -> ErrorPayload:
    message = str(err)
    lowered = message.lower()
    if "unsupported url" in lowered or "no suitable extractor" in lowered:
        return ErrorPayload(
            code="unsupported_site",
            message="This platform is not supported by yt-dlp.",
            hint="Try another URL; 1800+ sites are supported but not every subdomain.",
        )
    if "geo" in lowered and "restrict" in lowered:
        return ErrorPayload(
            code="geo_blocked",
            message="The content appears geo-restricted.",
            hint="Try a VPN / proxy or use another source URL.",
        )
    if "sign in" in lowered or "login" in lowered or "members-only" in lowered:
        return ErrorPayload(
            code="need_login",
            message="This video requires the viewer to be signed in.",
            hint="MVP does not support authenticated downloads.",
        )
    if "http error 403" in lowered or "expired" in lowered or "url has been expired" in lowered:
        return ErrorPayload(
            code="expired_url",
            message="The direct URL has expired.",
            hint="Parse again, or use server download mode.",
        )
    return ErrorPayload(code="parse_failed", message=message or "yt-dlp failed to process the URL.")


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------


def parse_url(url: str) -> Tuple[TaskRecord, ParseResult]:
    validate_url(url)

    try:
        share_for_dy = douyin_service.extract_first_url(url)
    except ValueError:
        share_for_dy = url.strip()
    if douyin_service.is_douyin_url(share_for_dy):
        try:
            meta, fmt_options, fmt_records, subs = douyin_service.parse_douyin(url)
        except ValueError as exc:
            raise ClientError("parse_failed", str(exc) or "抖音链接解析失败。") from exc
        except Exception as exc:
            logger.exception("Douyin parse failure for %s", url)
            raise ClientError("parse_failed", str(exc) or "抖音解析出错。") from exc
        task_id = uuid.uuid4().hex
        record = task_store.create(task_id)
        record.metadata = meta
        record.formats = fmt_records
        record.subtitles = subs
        record.status = "ready"
        record.touch()
        return record, ParseResult(
            task_id=task_id,
            metadata=meta,
            formats=fmt_options,
            subtitles=subs,
        )

    ydl_opts: Dict[str, Any] = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "noprogress": True,
        "nocheckcertificate": False,
        "extract_flat": False,
    }

    try:
        with YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
    except (DownloadError, ExtractorError) as exc:
        raise ClientError(
            _translate_ytdlp_error(exc).code,
            _translate_ytdlp_error(exc).message,
            _translate_ytdlp_error(exc).hint,
        ) from exc
    except Exception as exc:  # defensive
        logger.exception("Unexpected parse failure for %s", url)
        raise ClientError("parse_failed", str(exc) or "Unexpected parse failure.") from exc

    if info is None:
        raise ClientError("parse_failed", "yt-dlp returned no information for the URL.")

    if info.get("_type") == "playlist":
        entries = info.get("entries") or []
        first = next((e for e in entries if isinstance(e, dict)), None)
        if not first:
            raise ClientError("parse_failed", "Playlist has no resolvable entries.")
        info = first

    task_id = uuid.uuid4().hex
    record = task_store.create(task_id)

    metadata = _build_metadata(info)
    formats, format_records = _collect_formats(info)
    subtitles = _collect_subtitles(info)

    record.metadata = metadata
    record.formats = format_records
    record.subtitles = subtitles
    record.status = "ready"
    record.touch()

    return record, ParseResult(
        task_id=task_id,
        metadata=metadata,
        formats=formats,
        subtitles=subtitles,
    )


def _build_metadata(info: Dict[str, Any]) -> VideoMetadata:
    return VideoMetadata(
        title=info.get("title"),
        thumbnail=info.get("thumbnail"),
        duration=info.get("duration"),
        uploader=info.get("uploader") or info.get("channel"),
        webpage_url=info.get("webpage_url"),
        extractor=info.get("extractor_key") or info.get("extractor"),
    )


def _collect_formats(info: Dict[str, Any]) -> Tuple[List[FormatOption], Dict[str, FormatRecord]]:
    raw_formats: List[Dict[str, Any]] = info.get("formats") or []
    if not raw_formats and info.get("url"):
        raw_formats = [info]

    options: List[FormatOption] = []
    records: Dict[str, FormatRecord] = {}
    for f in raw_formats:
        format_id = f.get("format_id") or f.get("format")
        if not format_id:
            continue
        vcodec = f.get("vcodec") or "none"
        acodec = f.get("acodec") or "none"
        has_video = vcodec != "none"
        has_audio = acodec != "none"
        if not has_video and not has_audio:
            continue

        filesize = f.get("filesize") or f.get("filesize_approx")
        height = f.get("height")
        fps = f.get("fps")
        tbr = f.get("tbr")
        ext = f.get("ext") or "unknown"

        if has_video and has_audio:
            kind = "progressive"
        elif has_video:
            kind = "video_only"
        else:
            kind = "audio_only"

        label = _format_label(height, ext, kind, tbr, fps)

        option = FormatOption(
            format_id=str(format_id),
            ext=ext,
            label=label,
            height=height,
            fps=fps,
            tbr=tbr,
            vcodec=None if vcodec == "none" else vcodec,
            acodec=None if acodec == "none" else acodec,
            has_video=has_video,
            has_audio=has_audio,
            filesize=filesize,
            kind=kind,
        )
        options.append(option)
        records[str(format_id)] = FormatRecord(
            option=option,
            url=f.get("url"),
            http_headers=dict(f.get("http_headers") or {}),
        )

    options.sort(key=_format_sort_key, reverse=True)
    _mark_recommended(options)

    if not records:
        raise ClientError(
            "parse_failed",
            "No usable media formats were returned by the extractor.",
        )

    # Synthesised "best" format for server mode that asks yt-dlp to merge.
    best_id = "best_merge"
    best_option = FormatOption(
        format_id=best_id,
        ext="mp4",
        label="Auto (best video + best audio, merged)",
        has_video=True,
        has_audio=True,
        is_recommended=True,
        kind="progressive",
    )
    options.insert(0, best_option)
    records[best_id] = FormatRecord(option=best_option, url=None, http_headers={})

    return options, records


def _format_label(
    height: Optional[int],
    ext: str,
    kind: str,
    tbr: Optional[float],
    fps: Optional[float],
) -> str:
    parts: List[str] = []
    if height:
        parts.append(f"{height}p")
    elif kind == "audio_only":
        parts.append("Audio")
    else:
        parts.append("Unknown")
    if fps and fps > 30:
        parts.append(f"{int(fps)}fps")
    parts.append(ext.upper())
    if kind == "video_only":
        parts.append("video only")
    if kind == "audio_only" and tbr:
        parts.append(f"{int(tbr)}kbps")
    return " · ".join(parts)


def _format_sort_key(option: FormatOption) -> Tuple[int, int, int, float]:
    kind_priority = {"progressive": 2, "video_only": 1, "audio_only": 0}[option.kind]
    return (
        kind_priority,
        option.height or 0,
        int(option.fps or 0),
        option.tbr or 0.0,
    )


def _mark_recommended(options: List[FormatOption]) -> None:
    for option in options:
        if option.kind == "progressive" and option.has_video and option.has_audio:
            option.is_recommended = True
            return
    if options:
        options[0].is_recommended = True


def _collect_subtitles(info: Dict[str, Any]) -> List[SubtitleLanguage]:
    subs: Dict[str, SubtitleLanguage] = {}
    for code, entries in (info.get("subtitles") or {}).items():
        name = None
        if entries and isinstance(entries, list):
            name = entries[0].get("name")
        subs[code] = SubtitleLanguage(code=code, name=name, is_automatic=False)
    for code, entries in (info.get("automatic_captions") or {}).items():
        if code in subs:
            continue
        name = None
        if entries and isinstance(entries, list):
            name = entries[0].get("name")
        subs[code] = SubtitleLanguage(code=code, name=name, is_automatic=True)
    return sorted(subs.values(), key=lambda s: (s.is_automatic, s.code))


# ---------------------------------------------------------------------------
# Server-mode download
# ---------------------------------------------------------------------------


def _douyin_resolve_format_record(record: TaskRecord, format_id: str) -> FormatRecord:
    if format_id not in record.formats:
        raise ClientError("invalid_format", f"Unknown format_id '{format_id}' for this task.")
    fmt_rec = record.formats[format_id]
    if fmt_rec.url:
        return fmt_rec
    alt_id = "douyin_video" if format_id == "best_merge" else None
    if alt_id and record.formats.get(alt_id) and record.formats[alt_id].url:
        return record.formats[alt_id]
    refreshed = _refresh_direct_url(record, format_id)
    if not refreshed.url:
        raise ClientError("parse_failed", "无法获取抖音直链。")
    return refreshed


def _douyin_server_download(
    task_id: str,
    format_id: str,
    download_dir: Path,
) -> Path:
    record = task_store.require(task_id)
    fmt_rec = _douyin_resolve_format_record(record, format_id)
    media_url = fmt_rec.url
    if not media_url:
        raise ClientError("parse_failed", "抖音直链为空。")
    headers = dict(fmt_rec.http_headers or {})

    meta = record.metadata
    base_name = (meta.title if meta else None) or "douyin"
    out_name = _safe_filename(f"{base_name[:100]}.mp4")

    target_dir = download_dir / task_id
    target_dir.mkdir(parents=True, exist_ok=True)
    out_path = target_dir / out_name

    task_store.update(
        task_id,
        status="downloading",
        mode="server",
        progress=0.0,
    )

    try:
        timeout = httpx.Timeout(30.0, read=180.0)
        with httpx.Client(timeout=timeout, follow_redirects=True) as client:
            with client.stream("GET", media_url, headers=headers) as resp:
                resp.raise_for_status()
                total = int(resp.headers.get("Content-Length") or 0)
                downloaded = 0
                with out_path.open("wb") as f:
                    for chunk in resp.iter_bytes(chunk_size=256 * 1024):
                        if not chunk:
                            continue
                        f.write(chunk)
                        downloaded += len(chunk)
                        if total > 0:
                            task_store.update(
                                task_id,
                                progress=max(0.0, min(downloaded / total, 0.999)),
                            )
    except httpx.HTTPError as exc:
        payload = ErrorPayload(
            code="parse_failed",
            message=str(exc) or "抖音视频下载失败。",
            hint="可稍后重试，或改用浏览器「复制链接」后的新地址重新解析。",
        )
        task_store.set_error(task_id, payload)
        raise ClientError(payload.code, payload.message, payload.hint) from exc
    except Exception as exc:
        logger.exception("Douyin download failure for task %s", task_id)
        payload = ErrorPayload(code="internal", message=str(exc) or "抖音下载失败。")
        task_store.set_error(task_id, payload)
        raise ClientError(payload.code, payload.message) from exc

    task_store.update(
        task_id,
        status="done",
        progress=1.0,
        file_path=out_path,
        file_name=out_name,
        download_url=f"/api/files/{task_id}",
        mode="server",
    )
    return out_path


def server_download(
    task_id: str,
    format_id: str,
    download_dir: Path,
    subtitle_langs: Optional[List[str]] = None,
) -> Path:
    record = task_store.require(task_id)
    if not record.metadata or record.metadata.webpage_url is None:
        raise ClientError("task_not_found", "Task has no parsed metadata to download from.")

    if record.metadata.extractor == "douyin":
        return _douyin_server_download(task_id, format_id, download_dir)

    target_dir = download_dir / task_id
    target_dir.mkdir(parents=True, exist_ok=True)

    format_selector = _build_format_selector(record, format_id)

    ydl_opts: Dict[str, Any] = {
        "quiet": True,
        "no_warnings": True,
        "noprogress": False,
        "outtmpl": str(target_dir / "%(title).100s [%(id)s].%(ext)s"),
        "format": format_selector,
        "retries": 3,
        "fragment_retries": 3,
        "nocheckcertificate": False,
        "restrictfilenames": True,
        "progress_hooks": [_make_progress_hook(task_id)],
    }

    if has_ffmpeg():
        ydl_opts["merge_output_format"] = "mp4"
    else:
        # Fallback: refuse to require merging.
        if format_selector.startswith("bestvideo"):
            ydl_opts["format"] = "best[ext=mp4]/best"

    if subtitle_langs:
        ydl_opts.update(
            {
                "writesubtitles": True,
                "writeautomaticsub": True,
                "subtitleslangs": subtitle_langs,
                "subtitlesformat": "srt",
            }
        )
        if has_ffmpeg():
            ydl_opts.setdefault("postprocessors", []).append(
                {"key": "FFmpegEmbedSubtitle", "already_have_subtitle": False}
            )

    url = record.metadata.webpage_url

    task_store.update(
        task_id,
        status="downloading",
        mode="server",
        progress=0.0,
    )

    try:
        with YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            filename = ydl.prepare_filename(info)
    except (DownloadError, ExtractorError) as exc:
        payload = _translate_ytdlp_error(exc)
        task_store.set_error(task_id, payload)
        raise ClientError(payload.code, payload.message, payload.hint) from exc
    except Exception as exc:
        logger.exception("Unexpected download failure for task %s", task_id)
        payload = ErrorPayload(code="internal", message=str(exc) or "Unexpected download failure.")
        task_store.set_error(task_id, payload)
        raise ClientError(payload.code, payload.message) from exc

    result_path = Path(filename)
    if not result_path.exists():
        merged_guess = result_path.with_suffix(".mp4")
        if merged_guess.exists():
            result_path = merged_guess
        else:
            candidates = list(target_dir.glob("*"))
            if not candidates:
                payload = ErrorPayload(
                    code="internal",
                    message="Download completed but no output file was found.",
                )
                task_store.set_error(task_id, payload)
                raise ClientError(payload.code, payload.message)
            result_path = max(candidates, key=lambda p: p.stat().st_size)

    task_store.update(
        task_id,
        status="done",
        progress=1.0,
        file_path=result_path,
        file_name=_safe_filename(result_path.name),
        download_url=f"/api/files/{task_id}",
        mode="server",
    )
    return result_path


def _build_format_selector(record: TaskRecord, format_id: str) -> str:
    if format_id == "best_merge":
        return "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best"
    if format_id not in record.formats:
        raise ClientError("invalid_format", f"Unknown format_id '{format_id}' for this task.")
    fmt = record.formats[format_id].option
    if fmt.kind == "video_only":
        return f"{format_id}+bestaudio/best"
    if fmt.kind == "audio_only":
        return f"{format_id}/bestaudio"
    return format_id


def _make_progress_hook(task_id: str):
    def hook(status: Dict[str, Any]) -> None:
        phase = status.get("status")
        if phase == "downloading":
            total = status.get("total_bytes") or status.get("total_bytes_estimate") or 0
            downloaded = status.get("downloaded_bytes") or 0
            progress = (downloaded / total) if total else 0.0
            task_store.update(
                task_id,
                status="downloading",
                progress=max(0.0, min(progress, 0.999)),
                speed=_format_speed(status.get("speed")),
                eta=int(status["eta"]) if status.get("eta") is not None else None,
            )
        elif phase == "finished":
            task_store.update(task_id, progress=1.0, speed=None, eta=0)

    return hook


def _format_speed(speed: Optional[float]) -> Optional[str]:
    if speed is None:
        return None
    units = ["B/s", "KiB/s", "MiB/s", "GiB/s"]
    value = float(speed)
    idx = 0
    while value >= 1024 and idx < len(units) - 1:
        value /= 1024
        idx += 1
    return f"{value:.1f}{units[idx]}"


def _safe_filename(name: str) -> str:
    cleaned = _FILENAME_SANITIZE.sub("_", name).strip()
    return cleaned[:200] or "download"


# ---------------------------------------------------------------------------
# Direct-link (proxy / redirect) mode
# ---------------------------------------------------------------------------


def prepare_direct_link(
    task_id: str,
    format_id: str,
) -> Tuple[str, Dict[str, str]]:
    record = task_store.require(task_id)
    if format_id == "best_merge":
        if not (record.metadata and record.metadata.extractor == "douyin"):
            raise ClientError(
                "invalid_format",
                "Auto-merge format requires server mode.",
                hint="Switch to server mode or pick a progressive format.",
            )
        fmt_record = record.formats.get("best_merge")
        if fmt_record is None:
            raise ClientError("invalid_format", "Unknown format_id 'best_merge' for this task.")
        if not fmt_record.url:
            fmt_record = _refresh_direct_url(record, format_id)
        url = fmt_record.url
        if not url:
            raise ClientError("expired_url", "Could not resolve a fresh direct URL for that format.")
        return url, dict(fmt_record.http_headers or {})

    if format_id not in record.formats:
        raise ClientError("invalid_format", f"Unknown format_id '{format_id}' for this task.")

    fmt_record = record.formats[format_id]
    if not fmt_record.url:
        fmt_record = _refresh_direct_url(record, format_id)

    url = fmt_record.url
    if not url:
        raise ClientError("expired_url", "Could not resolve a fresh direct URL for that format.")
    return url, dict(fmt_record.http_headers or {})


def _refresh_direct_url(record: TaskRecord, format_id: str) -> FormatRecord:
    if not record.metadata or not record.metadata.webpage_url:
        raise ClientError("task_not_found", "Task is missing the original page URL.")

    if record.metadata.extractor == "douyin":
        play_url, hdrs = douyin_service.refresh_play_url(record.metadata.webpage_url)
        for fid in ("douyin_video", "best_merge"):
            fr = record.formats.get(fid)
            if fr:
                fr.url = play_url
                fr.http_headers = dict(hdrs)
        record.touch()
        if format_id not in record.formats:
            raise ClientError("invalid_format", f"Unknown format_id '{format_id}' for this task.")
        return record.formats[format_id]

    ydl_opts = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "format": format_id,
    }
    try:
        with YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(record.metadata.webpage_url, download=False)
    except (DownloadError, ExtractorError) as exc:
        payload = _translate_ytdlp_error(exc)
        raise ClientError(payload.code, payload.message, payload.hint) from exc

    formats = info.get("formats") or ([info] if info.get("url") else [])
    for f in formats:
        if str(f.get("format_id")) == format_id and f.get("url"):
            record.formats[format_id].url = f["url"]
            record.formats[format_id].http_headers = dict(f.get("http_headers") or {})
            record.touch()
            return record.formats[format_id]
    raise ClientError("expired_url", "Could not resolve a fresh direct URL for that format.")


def build_proxy_url(task_id: str, format_id: str) -> str:
    return f"/api/proxy?task_id={task_id}&format_id={format_id}"


def build_redirect_url(task_id: str, format_id: str) -> str:
    return f"/api/redirect?task_id={task_id}&format_id={format_id}"


def cleanup_task_files(record: TaskRecord) -> None:
    if record.file_path:
        parent = record.file_path.parent
        if parent.exists():
            shutil.rmtree(parent, ignore_errors=True)


def sweep_orphan_downloads(download_dir: Path, retention: int) -> None:
    if not download_dir.exists():
        return
    cutoff = time.time() - retention
    for child in download_dir.iterdir():
        try:
            if child.is_dir() and child.stat().st_mtime < cutoff and not task_store.get(child.name):
                shutil.rmtree(child, ignore_errors=True)
        except Exception:
            pass
