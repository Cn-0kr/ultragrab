"""Bilibili subtitle fetcher with WBI signing and multi-source fallback.

Strategy (waterfall):
  1. View API         /x/web-interface/view          → data.subtitle.list
  2. Player WBI API   /x/player/wbi/v2 + WBI sign    → data.subtitle.subtitles
  3. AI Summary API   /x/web-interface/view/conclusion/get + WBI sign
                                                      → data.model_result.subtitle

Most public videos return AI subtitles (ai-zh, ai-en …) from source 2 without
any Cookie.  Source 3 is B站's own video-summary transcript, useful when 1 & 2
both come back empty.
"""

from __future__ import annotations

import logging
import re
import threading
import time
import urllib.parse
from functools import reduce
from hashlib import md5
from typing import Any, Dict, List, Optional, Tuple

import httpx

from .schemas import SubtitleLanguage

logger = logging.getLogger(__name__)

_BVID_RE = re.compile(r"(BV[0-9A-Za-z]{10})")

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/125.0.0.0 Safari/537.36"
    ),
    "Referer": "https://www.bilibili.com",
}

_TIMEOUT = httpx.Timeout(15.0)

# ---------------------------------------------------------------------------
# WBI signing  (ref: bilibili-API-collect/docs/misc/sign/wbi.md)
# ---------------------------------------------------------------------------

_MIXIN_KEY_ENC_TAB = [
    46, 47, 18, 2, 53, 8, 23, 32, 15, 50, 10, 31, 58, 3, 45, 35,
    27, 43, 5, 49, 33, 9, 42, 19, 29, 28, 14, 39, 12, 38, 41, 13,
    37, 48, 7, 16, 24, 55, 40, 61, 26, 17, 0, 1, 60, 51, 30, 4,
    22, 25, 54, 21, 56, 59, 6, 63, 57, 62, 11, 36, 20, 34, 44, 52,
]

_wbi_cache_lock = threading.Lock()
_wbi_img_key: str = ""
_wbi_sub_key: str = ""
_wbi_cache_ts: float = 0.0
_WBI_CACHE_TTL = 3600  # keys rotate daily; refresh hourly is safe


def _get_mixin_key(orig: str) -> str:
    return reduce(lambda s, i: s + orig[i], _MIXIN_KEY_ENC_TAB, "")[:32]


def _enc_wbi(params: Dict[str, Any], img_key: str, sub_key: str) -> Dict[str, Any]:
    mixin_key = _get_mixin_key(img_key + sub_key)
    curr_time = round(time.time())
    params["wts"] = curr_time
    params = dict(sorted(params.items()))
    params = {
        k: "".join(ch for ch in str(v) if ch not in "!'()*")
        for k, v in params.items()
    }
    query = urllib.parse.urlencode(params)
    wbi_sign = md5((query + mixin_key).encode()).hexdigest()
    params["w_rid"] = wbi_sign
    return params


def _fetch_wbi_keys() -> Tuple[str, str]:
    """GET /x/web-interface/nav → (img_key, sub_key). Works anonymously."""
    resp = httpx.get(
        "https://api.bilibili.com/x/web-interface/nav",
        headers=_HEADERS,
        timeout=_TIMEOUT,
    )
    resp.raise_for_status()
    wbi_img = resp.json().get("data", {}).get("wbi_img", {})
    img_url: str = wbi_img.get("img_url", "")
    sub_url: str = wbi_img.get("sub_url", "")
    if not img_url or not sub_url:
        raise RuntimeError("nav API did not return wbi_img keys")
    img_key = img_url.rsplit("/", 1)[-1].split(".")[0]
    sub_key = sub_url.rsplit("/", 1)[-1].split(".")[0]
    return img_key, sub_key


def get_wbi_keys() -> Tuple[str, str]:
    """Return cached (img_key, sub_key), refreshing if stale."""
    global _wbi_img_key, _wbi_sub_key, _wbi_cache_ts
    with _wbi_cache_lock:
        if _wbi_img_key and (time.time() - _wbi_cache_ts < _WBI_CACHE_TTL):
            return _wbi_img_key, _wbi_sub_key
    img_key, sub_key = _fetch_wbi_keys()
    with _wbi_cache_lock:
        _wbi_img_key, _wbi_sub_key = img_key, sub_key
        _wbi_cache_ts = time.time()
    return img_key, sub_key


def _signed_params(params: Dict[str, Any]) -> Dict[str, Any]:
    """Add WBI signature to *params* dict. Falls back to unsigned on error."""
    try:
        img_key, sub_key = get_wbi_keys()
        return _enc_wbi(dict(params), img_key, sub_key)
    except Exception as exc:
        logger.debug("WBI key fetch failed, falling back unsigned: %s", exc)
        params["wts"] = round(time.time())
        return params


# ---------------------------------------------------------------------------
# Public helpers
# ---------------------------------------------------------------------------


def extract_bvid(webpage_url: str) -> Optional[str]:
    """Extract BVxxxxxxxx from a Bilibili URL."""
    m = _BVID_RE.search(webpage_url)
    return m.group(1) if m else None


def fetch_view(bvid: str) -> Dict[str, Any]:
    """GET /x/web-interface/view → full data dict (aid, cid, title, subtitle …)."""
    url = f"https://api.bilibili.com/x/web-interface/view?bvid={bvid}"
    resp = httpx.get(url, headers=_HEADERS, timeout=_TIMEOUT)
    resp.raise_for_status()
    return resp.json().get("data") or {}


# ---------------------------------------------------------------------------
# Source 1: View API  →  data.subtitle.list
# ---------------------------------------------------------------------------


def _tracks_from_view(view_data: Dict[str, Any]) -> List[Dict[str, Any]]:
    raw_list = (view_data.get("subtitle") or {}).get("list") or []
    return _normalise_track_list(raw_list)


# ---------------------------------------------------------------------------
# Source 2: Player WBI API  →  data.subtitle.subtitles
# ---------------------------------------------------------------------------


def fetch_player_wbi(bvid: str, cid: int, aid: Optional[int] = None) -> Dict[str, Any]:
    """GET /x/player/wbi/v2 with WBI signature."""
    params: Dict[str, Any] = {"bvid": bvid, "cid": cid}
    if aid:
        params["aid"] = aid
    signed = _signed_params(params)
    resp = httpx.get(
        "https://api.bilibili.com/x/player/wbi/v2",
        params=signed,
        headers=_HEADERS,
        timeout=_TIMEOUT,
    )
    resp.raise_for_status()
    return resp.json().get("data") or {}


def _tracks_from_player_wbi(player_data: Dict[str, Any]) -> List[Dict[str, Any]]:
    raw_list = (player_data.get("subtitle") or {}).get("subtitles") or []
    return _normalise_track_list(raw_list)


# ---------------------------------------------------------------------------
# Source 3: AI Summary API  →  data.model_result.subtitle
# ---------------------------------------------------------------------------

_SUMMARY_URL = "https://api.bilibili.com/x/web-interface/view/conclusion/get"


def _tracks_from_ai_summary(bvid: str, cid: int, aid: Optional[int] = None) -> List[Dict[str, Any]]:
    """Fetch B站 AI summary and extract per-segment transcript as a pseudo-track."""
    params: Dict[str, Any] = {"bvid": bvid, "cid": cid}
    if aid:
        params["aid"] = aid
    signed = _signed_params(params)
    resp = httpx.get(_SUMMARY_URL, params=signed, headers=_HEADERS, timeout=_TIMEOUT)
    resp.raise_for_status()
    data = resp.json().get("data") or {}
    model_result = data.get("model_result") or {}
    ai_subs_list = model_result.get("subtitle") or []
    if not ai_subs_list:
        return []
    part_subs = ai_subs_list[0].get("part_subtitle") or [] if ai_subs_list else []
    if not part_subs:
        return []
    body = [
        {
            "from": seg.get("start_timestamp", 0),
            "to": seg.get("end_timestamp", 0),
            "content": seg.get("content", ""),
        }
        for seg in part_subs
        if seg.get("content")
    ]
    if not body:
        return []
    srt_text = _body_to_srt(body)
    return [{
        "lan": "ai-zh",
        "lan_doc": "中文（AI 摘要）",
        "subtitle_url": "",
        "is_ai": True,
        "_srt_text": srt_text,
        "_source": "ai_summary",
    }]


# ---------------------------------------------------------------------------
# Normalisation & dedup
# ---------------------------------------------------------------------------


def _normalise_track_list(raw_list: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    tracks: List[Dict[str, Any]] = []
    for item in raw_list:
        lan = item.get("lan") or ""
        subtitle_url = item.get("subtitle_url") or ""
        if not subtitle_url:
            continue
        if subtitle_url.startswith("//"):
            subtitle_url = "https:" + subtitle_url
        tracks.append({
            "lan": lan,
            "lan_doc": item.get("lan_doc") or lan,
            "subtitle_url": subtitle_url,
            "is_ai": lan.startswith("ai-"),
        })
    return tracks


def _dedup_tracks(all_tracks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Deduplicate by language code, keeping the first (higher-priority) entry."""
    seen: set[str] = set()
    result: List[Dict[str, Any]] = []
    for t in all_tracks:
        if t["lan"] not in seen:
            seen.add(t["lan"])
            result.append(t)
    return result


# ---------------------------------------------------------------------------
# Multi-source orchestration
# ---------------------------------------------------------------------------


def _collect_all_tracks(bvid: str) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """Try all sources, return (deduplicated tracks, view_data).

    Track priority: Source 1 (View) > Source 2 (Player WBI) > Source 3 (AI Summary).
    """
    view_data = fetch_view(bvid)
    aid = view_data.get("aid")
    cid = view_data.get("cid")
    if not cid:
        return [], view_data

    all_tracks: List[Dict[str, Any]] = []

    # Source 1
    try:
        s1 = _tracks_from_view(view_data)
        if s1:
            logger.debug("bilibili source 1 (View API): %d tracks", len(s1))
            all_tracks.extend(s1)
    except Exception as exc:
        logger.debug("bilibili source 1 failed: %s", exc)

    # Source 2
    try:
        player_data = fetch_player_wbi(bvid, int(cid), aid=aid)
        s2 = _tracks_from_player_wbi(player_data)
        if s2:
            logger.debug("bilibili source 2 (Player WBI): %d tracks", len(s2))
            all_tracks.extend(s2)
    except Exception as exc:
        logger.debug("bilibili source 2 failed: %s", exc)

    # Source 3 (only if previous sources returned nothing)
    if not all_tracks:
        try:
            s3 = _tracks_from_ai_summary(bvid, int(cid), aid=aid)
            if s3:
                logger.debug("bilibili source 3 (AI Summary): %d tracks", len(s3))
                all_tracks.extend(s3)
        except Exception as exc:
            logger.debug("bilibili source 3 failed: %s", exc)

    return _dedup_tracks(all_tracks), view_data


# ---------------------------------------------------------------------------
# Download helpers
# ---------------------------------------------------------------------------


def download_track(subtitle_url: str) -> str:
    """Download a Bilibili subtitle JSON and convert to SRT text."""
    resp = httpx.get(subtitle_url, headers=_HEADERS, timeout=_TIMEOUT)
    resp.raise_for_status()
    payload = resp.json()
    body: List[Dict[str, Any]] = payload.get("body") or []
    if not body:
        return ""
    return _body_to_srt(body)


def as_subtitle_languages(tracks: List[Dict[str, Any]]) -> List[SubtitleLanguage]:
    """Convert track list to project SubtitleLanguage schema."""
    return [
        SubtitleLanguage(
            code=t["lan"],
            name=t.get("lan_doc") or "AI 字幕",
            is_automatic=t.get("is_ai", True),
        )
        for t in tracks
    ]


# ---------------------------------------------------------------------------
# High-level probe used during parse
# ---------------------------------------------------------------------------


def probe(webpage_url: str) -> List[SubtitleLanguage]:
    """Probe Bilibili APIs for subtitle tracks. Returns SubtitleLanguage list.

    Uses multi-source fallback (View → Player WBI → AI Summary).
    On any failure returns [] without raising (non-fatal for the parse pipeline).
    """
    bvid = extract_bvid(webpage_url)
    if not bvid:
        return []
    try:
        tracks, _ = _collect_all_tracks(bvid)
        if not tracks:
            return []
        return as_subtitle_languages(tracks)
    except Exception as exc:
        logger.info("bilibili_subs.probe failed for %s: %s", bvid, exc)
        return []


def fetch_track_srt(webpage_url: str, lan: str) -> Optional[str]:
    """Fetch a specific subtitle track by language code and return SRT text.

    Returns None on failure.
    """
    bvid = extract_bvid(webpage_url)
    if not bvid:
        return None
    try:
        tracks, _ = _collect_all_tracks(bvid)
        target = next((t for t in tracks if t["lan"] == lan), None)
        if target is None:
            return None
        # Source 3 tracks carry pre-built SRT instead of a URL
        if target.get("_srt_text"):
            return target["_srt_text"]
        srt_text = download_track(target["subtitle_url"])
        return srt_text or None
    except Exception as exc:
        logger.warning("bilibili_subs.fetch_track_srt failed (%s, %s): %s", bvid, lan, exc)
        return None


# ---------------------------------------------------------------------------
# Backward-compat aliases used by other modules
# ---------------------------------------------------------------------------

def list_ai_subtitles(player_data: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Kept for backward compatibility. Prefer _collect_all_tracks for new code."""
    return _tracks_from_player_wbi(player_data)


def fetch_player(bvid: str, cid: int) -> Dict[str, Any]:
    """Backward-compat wrapper — now uses WBI endpoint."""
    return fetch_player_wbi(bvid, cid)


# ---------------------------------------------------------------------------
# Internal: JSON body → SRT
# ---------------------------------------------------------------------------


def _body_to_srt(body: List[Dict[str, Any]]) -> str:
    """Convert Bilibili subtitle JSON body array to SRT formatted string."""
    lines: List[str] = []
    for idx, item in enumerate(body, start=1):
        start = item.get("from", 0.0)
        end = item.get("to", 0.0)
        content = item.get("content", "").strip()
        if not content:
            continue
        lines.append(str(idx))
        lines.append(f"{_seconds_to_srt_ts(start)} --> {_seconds_to_srt_ts(end)}")
        lines.append(content)
        lines.append("")
    return "\n".join(lines)


def _seconds_to_srt_ts(seconds: float) -> str:
    """Convert float seconds to SRT timestamp HH:MM:SS,mmm."""
    total_ms = int(round(seconds * 1000))
    h = total_ms // 3600_000
    total_ms %= 3600_000
    m = total_ms // 60_000
    total_ms %= 60_000
    s = total_ms // 1000
    ms = total_ms % 1000
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"
