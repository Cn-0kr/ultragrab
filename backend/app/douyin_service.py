"""Douyin (抖音) 解析：短链重定向、iesdouyin 公开接口、playwm→play 无水印直链。

实现思路与 MIT 许可的 rathodpratham-dev/douyin_video_downloader 一致，使用 httpx（与项目其余部分统一）。
"""

from __future__ import annotations

import json
import logging
import re
import time
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import parse_qs, urljoin, urlparse

import httpx

from .schemas import FormatOption, SubtitleLanguage, VideoMetadata
from .task_store import FormatRecord

logger = logging.getLogger(__name__)

ITEMINFO_URL = "https://www.iesdouyin.com/web/api/v2/aweme/iteminfo/"

DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/json,*/*",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    "Connection": "keep-alive",
    "Referer": "https://www.douyin.com/",
}

MOBILE_PAGE_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) "
        "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.0 "
        "Mobile/15E148 Safari/604.1"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    "Referer": "https://www.douyin.com/",
}

URL_IN_TEXT = re.compile(r"https?://[^\s]+", re.IGNORECASE)

RETRYABLE_STATUS = {429, 500, 502, 503, 504}
_CONNECT_TIMEOUT = 15.0
_READ_TIMEOUT = 45.0


def is_douyin_url(url: str) -> bool:
    try:
        host = (urlparse(url).hostname or "").lower()
    except Exception:
        return False
    return bool(host) and (
        host == "douyin.com"
        or host.endswith(".douyin.com")
        or host == "iesdouyin.com"
        or host.endswith(".iesdouyin.com")
    )


def extract_first_url(text: str) -> str:
    text = (text or "").strip()
    if not text:
        raise ValueError("Empty URL.")
    match = URL_IN_TEXT.search(text)
    if match:
        return match.group(0).strip().strip('"').strip("'").rstrip(").,;!?")
    if text.startswith("http"):
        return text
    raise ValueError("No URL found in input.")


def extract_video_id(url: str) -> str:
    parsed = urlparse(url)
    query = parse_qs(parsed.query)
    for key in ("modal_id", "item_ids", "group_id", "aweme_id"):
        values = query.get(key)
        if not values:
            continue
        m = re.search(r"(\d{8,24})", values[0])
        if m:
            return m.group(1)
    for pattern in (r"/video/(\d{8,24})", r"/note/(\d{8,})", r"/(\d{8,24})(?:/|$)"):
        m = re.search(pattern, parsed.path)
        if m:
            return m.group(1)
    m = re.search(r"(\d{8,24})", url)
    if m:
        return m.group(1)
    raise ValueError("Could not extract Douyin video id from URL.")


_EMBEDDED_HTTP = re.compile(
    r"https?://(?:www\.|m\.)?(?:douyin\.com|iesdouyin\.com|v\.douyin\.com)[^\s&\"']+",
    re.IGNORECASE,
)


def _http_url_embedded_in_location(location: str) -> Optional[str]:
    """短链 302 可能指向 snssdk1128://...，其中内嵌真实 https 跳转目标。"""
    m = _EMBEDDED_HTTP.search(location)
    if m:
        return m.group(0).rstrip("/)")
    m2 = re.search(r"https?://[^\s&\"']+", location)
    return m2.group(0).rstrip("/)") if m2 else None


def _resolve_redirect(client: httpx.Client, share_url: str, max_retries: int = 3) -> str:
    """手动跟随重定向，避免 httpx 跟随 snssdk 等非标协议导致失败。"""
    last_err: Optional[Exception] = None
    for attempt in range(1, max_retries + 1):
        try:
            current = share_url
            for _ in range(35):
                r = client.get(current, follow_redirects=False)
                if r.status_code in (301, 302, 303, 307, 308):
                    loc = (r.headers.get("location") or "").strip()
                    if loc.startswith("http://") or loc.startswith("https://"):
                        current = urljoin(str(r.url), loc)
                        continue
                    embedded = _http_url_embedded_in_location(loc)
                    if embedded:
                        current = embedded
                        continue
                    return str(r.url)
                r.raise_for_status()
                return str(r.url)
            return str(r.url)
        except (httpx.HTTPError, ValueError) as exc:
            last_err = exc
            if attempt == max_retries:
                break
            time.sleep(1.0 * attempt)
    raise ValueError("Could not resolve Douyin share link.") from last_err


def _get_json(client: httpx.Client, params: Optional[Dict[str, str]] = None) -> Any:
    r = client.get(ITEMINFO_URL, params=params or {})
    if r.status_code in RETRYABLE_STATUS:
        r.raise_for_status()
    r.raise_for_status()
    return r.json()


def _extract_router_data_json(html: str) -> Dict[str, Any]:
    marker = "window._ROUTER_DATA = "
    start = html.find(marker)
    if start < 0:
        return {}
    index = start + len(marker)
    while index < len(html) and html[index].isspace():
        index += 1
    if index >= len(html) or html[index] != "{":
        return {}
    depth = 0
    in_string = False
    escaped = False
    for cursor in range(index, len(html)):
        char = html[cursor]
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                payload = html[index : cursor + 1]
                try:
                    return json.loads(payload)
                except ValueError:
                    return {}
    return {}


def _collect_video_info_res_nodes(obj: Any, out: Optional[List[dict]] = None) -> List[dict]:
    if out is None:
        out = []
    if isinstance(obj, dict):
        vir = obj.get("videoInfoRes")
        if isinstance(vir, dict):
            out.append(vir)
        for v in obj.values():
            _collect_video_info_res_nodes(v, out)
    elif isinstance(obj, list):
        for v in obj:
            _collect_video_info_res_nodes(v, out)
    return out


def _item_from_router(router: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    for vir in _collect_video_info_res_nodes(router):
        il = vir.get("item_list") or []
        if il and isinstance(il[0], dict):
            return il[0]
    return None


def _router_user_message(router: Dict[str, Any]) -> Optional[str]:
    for vir in _collect_video_info_res_nodes(router):
        fl = vir.get("filter_list") or []
        for f in fl:
            if not isinstance(f, dict):
                continue
            reason = str(f.get("filter_reason") or "")
            if reason in {"SYSTEM_ITEM_NOT_EXIST", "FINDER_SYSTEM_ITEM_NOT_EXIST"}:
                return "该视频不存在或已下架。"
            if reason and reason != "NONE":
                return f"无法获取视频（{reason}）。"
    return None


def _item_from_share_html(client: httpx.Client, video_id: str, resolved_url: str) -> Dict[str, Any]:
    parsed = urlparse(resolved_url)
    if (
        parsed.netloc
        and "iesdouyin.com" in parsed.netloc.lower()
        and "/share/video/" in (parsed.path or "")
    ):
        share_page = resolved_url.split("?")[0].rstrip("/") + "/"
    else:
        share_page = f"https://www.iesdouyin.com/share/video/{video_id}/"
    r = client.get(share_page, headers=MOBILE_PAGE_HEADERS)
    r.raise_for_status()
    router = _extract_router_data_json(r.text or "")
    if not router:
        raise ValueError("无法解析抖音分享页（页面无内嵌数据或结构已变更）。")
    msg = _router_user_message(router)
    item = _item_from_router(router)
    if item:
        return item
    if msg:
        raise ValueError(msg)
    raise ValueError(
        "分享页未返回作品数据。请在浏览器中打开该视频，复制地址栏里含 /video/ 的完整链接后重试。"
    )


def load_aweme_item(client: httpx.Client, video_id: str, resolved_url: str) -> Dict[str, Any]:
    data: Any = {}
    try:
        data = _get_json(client, params={"item_ids": video_id})
    except (httpx.HTTPError, ValueError, json.JSONDecodeError) as exc:
        logger.debug("Douyin iteminfo 请求失败，改用分享页: %s", exc)
        return _item_from_share_html(client, video_id, resolved_url)

    status_code = data.get("status_code")
    item_list = data.get("item_list") or []

    if status_code in (0, None) and item_list and isinstance(item_list[0], dict):
        return item_list[0]

    if status_code == 11110 or data.get("status_msg") == "encrypt_data_miss":
        logger.info("Douyin iteminfo 需签参 (status_code=%s)，改用分享页。", status_code)
        return _item_from_share_html(client, video_id, resolved_url)

    try:
        return _item_from_share_html(client, video_id, resolved_url)
    except ValueError:
        pass

    raise ValueError(
        f"抖音接口未返回作品数据（status_code={status_code!r}）。"
        "请在浏览器中打开视频页后，复制地址栏完整链接再解析。"
    )


def play_url_from_item(item: Dict[str, Any]) -> str:
    play_urls = (item.get("video") or {}).get("play_addr") or {}
    url_list = play_urls.get("url_list") or []
    if not url_list:
        raise ValueError("No play_addr url_list in item.")
    raw = url_list[0]
    if not isinstance(raw, str):
        raise ValueError("Invalid play URL.")
    return raw.replace("playwm", "play")


def metadata_from_item(resolved_page_url: str, video_id: str, item: Dict[str, Any]) -> VideoMetadata:
    video = item.get("video") or {}
    cover = video.get("cover") or {}
    thumbs = cover.get("url_list") or []
    thumb = thumbs[0] if thumbs else None
    duration = None
    if video.get("duration") is not None:
        try:
            duration = float(video["duration"]) / 1000.0
        except (TypeError, ValueError):
            duration = None
    author = item.get("author") or {}
    nickname = author.get("nickname") or author.get("unique_id")
    return VideoMetadata(
        title=item.get("desc") or f"douyin_{video_id}",
        thumbnail=thumb,
        duration=duration,
        uploader=nickname,
        webpage_url=resolved_page_url,
        extractor="douyin",
    )


def _video_download_headers() -> Dict[str, str]:
    return {
        "User-Agent": DEFAULT_HEADERS["User-Agent"],
        "Referer": "https://www.douyin.com/",
        "Accept": "*/*",
    }


def build_format_records(play_url: str) -> Tuple[List[FormatOption], Dict[str, FormatRecord]]:
    headers = _video_download_headers()
    core = FormatOption(
        format_id="douyin_video",
        ext="mp4",
        label="MP4 · 无水印",
        has_video=True,
        has_audio=True,
        kind="progressive",
        is_recommended=True,
    )
    best = FormatOption(
        format_id="best_merge",
        ext="mp4",
        label="自动（无水印）",
        has_video=True,
        has_audio=True,
        kind="progressive",
        is_recommended=True,
    )
    records: Dict[str, FormatRecord] = {
        "douyin_video": FormatRecord(option=core, url=play_url, http_headers=dict(headers)),
        "best_merge": FormatRecord(option=best, url=play_url, http_headers=dict(headers)),
    }
    return [best, core], records


def parse_douyin(url: str) -> Tuple[VideoMetadata, List[FormatOption], Dict[str, FormatRecord], List[SubtitleLanguage]]:
    share_url = extract_first_url(url)
    if not is_douyin_url(share_url):
        raise ValueError("URL is not a Douyin link.")

    timeout = httpx.Timeout(_CONNECT_TIMEOUT, read=_READ_TIMEOUT)
    with httpx.Client(timeout=timeout, headers=DEFAULT_HEADERS) as client:
        resolved = _resolve_redirect(client, share_url)
        video_id = extract_video_id(resolved)
        item = load_aweme_item(client, video_id, resolved)
        play_url = play_url_from_item(item)
        meta = metadata_from_item(resolved, video_id, item)
        options, records = build_format_records(play_url)

    return meta, options, records, []


def refresh_play_url(webpage_url: str) -> Tuple[str, Dict[str, str]]:
    """直链失效时根据作品页 URL 重新拉取无水印地址。"""
    timeout = httpx.Timeout(_CONNECT_TIMEOUT, read=_READ_TIMEOUT)
    with httpx.Client(timeout=timeout, headers=DEFAULT_HEADERS) as client:
        video_id = extract_video_id(webpage_url)
        item = load_aweme_item(client, video_id, webpage_url)
        play_url = play_url_from_item(item)
    return play_url, _video_download_headers()
