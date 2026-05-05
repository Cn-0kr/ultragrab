"""HTTP routes for the video download service."""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Dict, List, Optional
from urllib.parse import quote

import httpx
from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import JSONResponse, RedirectResponse, StreamingResponse

from . import ytdlp_service
from .schemas import (
    DownloadRequest,
    DownloadResponse,
    ErrorPayload,
    ErrorResponse,
    ParseBatchItem,
    ParseBatchRequest,
    ParseBatchResponse,
    ParseRequest,
    ParseResult,
    TaskView,
)
from .settings import settings
from .task_store import task_store

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api")

_download_semaphore = asyncio.Semaphore(settings.max_concurrent_downloads)


def _error(status_code: int, payload: ErrorPayload) -> HTTPException:
    return HTTPException(status_code=status_code, detail=payload.model_dump())


@router.get("/health")
async def health() -> Dict[str, object]:
    return {
        "status": "ok",
        "ffmpeg": ytdlp_service.has_ffmpeg(),
        "time": time.time(),
    }


@router.post("/parse", response_model=ParseResult, responses={400: {"model": ErrorResponse}})
async def parse(payload: ParseRequest) -> ParseResult:
    try:
        _, result = await asyncio.to_thread(ytdlp_service.parse_url, str(payload.url))
    except ytdlp_service.ClientError as exc:
        raise _error(400, exc.payload) from exc
    except Exception as exc:  # pragma: no cover
        logger.exception("parse failed")
        raise _error(500, ErrorPayload(code="internal", message=str(exc))) from exc
    return result


@router.post("/parse/batch", response_model=ParseBatchResponse)
async def parse_batch(payload: ParseBatchRequest) -> ParseBatchResponse:
    if len(payload.urls) > settings.max_batch_urls:
        raise _error(
            400,
            ErrorPayload(
                code="invalid_url",
                message=f"Too many URLs (max {settings.max_batch_urls}).",
            ),
        )

    async def _one(url: str) -> ParseBatchItem:
        try:
            _, result = await asyncio.to_thread(ytdlp_service.parse_url, url)
            return ParseBatchItem(url=url, ok=True, result=result)
        except ytdlp_service.ClientError as exc:
            return ParseBatchItem(url=url, ok=False, error=exc.payload)
        except Exception as exc:  # pragma: no cover
            logger.exception("batch parse failed for %s", url)
            return ParseBatchItem(
                url=url,
                ok=False,
                error=ErrorPayload(code="internal", message=str(exc)),
            )

    items = await asyncio.gather(*[_one(str(u)) for u in payload.urls])
    return ParseBatchResponse(items=list(items))


@router.post("/download", response_model=DownloadResponse)
async def download(payload: DownloadRequest) -> DownloadResponse:
    record = task_store.get(payload.task_id)
    if record is None:
        raise _error(404, ErrorPayload(code="task_not_found", message="Task does not exist."))

    if payload.mode == "server":
        return await _start_server_download(payload)
    if payload.mode == "proxy":
        try:
            ytdlp_service.prepare_direct_link(payload.task_id, payload.format_id)
        except ytdlp_service.ClientError as exc:
            raise _error(400, exc.payload) from exc
        proxy_url = ytdlp_service.build_proxy_url(payload.task_id, payload.format_id)
        task_store.update(payload.task_id, mode="proxy", status="ready", download_url=proxy_url)
        return DownloadResponse(
            task_id=payload.task_id,
            mode="proxy",
            status="ready",
            download_url=proxy_url,
        )
    if payload.mode == "redirect":
        if not settings.allow_redirect:
            raise _error(
                400,
                ErrorPayload(
                    code="redirect_disabled",
                    message="Redirect mode has been disabled by the server.",
                    hint="Use proxy mode instead.",
                ),
            )
        try:
            ytdlp_service.prepare_direct_link(payload.task_id, payload.format_id)
        except ytdlp_service.ClientError as exc:
            raise _error(400, exc.payload) from exc
        redirect_url = ytdlp_service.build_redirect_url(payload.task_id, payload.format_id)
        task_store.update(payload.task_id, mode="redirect", status="ready", download_url=redirect_url)
        return DownloadResponse(
            task_id=payload.task_id,
            mode="redirect",
            status="ready",
            download_url=redirect_url,
        )

    raise _error(400, ErrorPayload(code="invalid_mode", message=f"Unknown mode '{payload.mode}'."))


async def _start_server_download(payload: DownloadRequest) -> DownloadResponse:
    task_store.update(payload.task_id, status="queued", mode="server", progress=0.0)

    async def _run() -> None:
        async with _download_semaphore:
            try:
                await asyncio.to_thread(
                    ytdlp_service.server_download,
                    payload.task_id,
                    payload.format_id,
                    settings.download_dir,
                    payload.subtitle_langs,
                )
            except ytdlp_service.ClientError:
                pass
            except Exception as exc:  # pragma: no cover
                logger.exception("server download failed")
                task_store.set_error(
                    payload.task_id,
                    ErrorPayload(code="internal", message=str(exc)),
                )

    asyncio.create_task(_run())

    return DownloadResponse(
        task_id=payload.task_id,
        mode="server",
        status="queued",
    )


@router.get("/tasks/{task_id}", response_model=TaskView)
async def get_task(task_id: str) -> TaskView:
    record = task_store.get(task_id)
    if record is None:
        raise _error(404, ErrorPayload(code="task_not_found", message="Task does not exist."))
    return record.to_view()


@router.get("/files/{task_id}")
async def get_file(task_id: str) -> StreamingResponse:
    record = task_store.get(task_id)
    if record is None:
        raise _error(404, ErrorPayload(code="task_not_found", message="Task does not exist."))
    if record.status != "done" or not record.file_path:
        raise _error(
            409,
            ErrorPayload(
                code="not_ready",
                message=f"Task is not ready (status={record.status}).",
                hint="Poll GET /api/tasks/{task_id} until status is 'done'.",
            ),
        )
    path = record.file_path
    if not path.exists():
        raise _error(410, ErrorPayload(code="expired_url", message="File has been removed."))

    file_name = record.file_name or path.name
    size = path.stat().st_size

    def iter_chunks():
        with path.open("rb") as fh:
            while True:
                chunk = fh.read(64 * 1024)
                if not chunk:
                    break
                yield chunk

    ascii_fallback = file_name.encode("ascii", "ignore").decode() or "download"
    encoded = quote(file_name, safe="")
    headers = {
        "Content-Disposition": f"attachment; filename=\"{ascii_fallback}\"; filename*=UTF-8''{encoded}",
        "Content-Length": str(size),
    }
    media_type = _guess_media_type(path.suffix.lower())
    return StreamingResponse(iter_chunks(), media_type=media_type, headers=headers)


def _guess_media_type(suffix: str) -> str:
    return {
        ".mp4": "video/mp4",
        ".m4a": "audio/mp4",
        ".mp3": "audio/mpeg",
        ".webm": "video/webm",
        ".mkv": "video/x-matroska",
        ".mov": "video/quicktime",
        ".flv": "video/x-flv",
        ".ogg": "audio/ogg",
        ".opus": "audio/opus",
        ".wav": "audio/wav",
    }.get(suffix, "application/octet-stream")


@router.get("/proxy")
async def proxy(
    request: Request,
    task_id: str = Query(...),
    format_id: str = Query(...),
) -> StreamingResponse:
    try:
        direct_url, headers = ytdlp_service.prepare_direct_link(task_id, format_id)
    except ytdlp_service.ClientError as exc:
        raise _error(400, exc.payload) from exc

    forward_headers: Dict[str, str] = dict(headers)
    incoming_range = request.headers.get("range")
    if incoming_range:
        forward_headers["Range"] = incoming_range
    if "User-Agent" not in forward_headers:
        forward_headers["User-Agent"] = request.headers.get("user-agent", "Mozilla/5.0")

    client = httpx.AsyncClient(timeout=httpx.Timeout(30.0, read=None), follow_redirects=True)
    try:
        response = await client.send(
            client.build_request("GET", direct_url, headers=forward_headers),
            stream=True,
        )
    except httpx.HTTPError as exc:
        await client.aclose()
        raise _error(
            502,
            ErrorPayload(code="upstream_error", message=f"Upstream fetch failed: {exc}"),
        ) from exc

    if response.status_code >= 400:
        await response.aclose()
        await client.aclose()
        raise _error(
            502,
            ErrorPayload(
                code="upstream_error",
                message=f"Upstream returned {response.status_code}.",
                hint="Try re-parsing the URL or switching to server mode.",
            ),
        )

    passthrough = {
        k: v
        for k, v in response.headers.items()
        if k.lower() in {"content-length", "content-range", "accept-ranges", "content-type", "etag"}
    }
    record = task_store.get(task_id)
    file_hint = "download"
    if record and record.metadata and record.metadata.title:
        file_hint = ytdlp_service._safe_filename(record.metadata.title)
    extension = _guess_extension_from_headers(response.headers.get("content-type"))
    filename = f"{file_hint}{extension}"
    ascii_fallback = filename.encode("ascii", "ignore").decode() or "download"
    encoded = quote(filename, safe="")
    passthrough["Content-Disposition"] = (
        f"attachment; filename=\"{ascii_fallback}\"; filename*=UTF-8''{encoded}"
    )

    async def streamer():
        try:
            async for chunk in response.aiter_bytes(64 * 1024):
                yield chunk
        finally:
            await response.aclose()
            await client.aclose()

    return StreamingResponse(
        streamer(),
        status_code=response.status_code,
        headers=passthrough,
        media_type=response.headers.get("content-type", "application/octet-stream"),
    )


def _guess_extension_from_headers(content_type: Optional[str]) -> str:
    if not content_type:
        return ".bin"
    mapping = {
        "video/mp4": ".mp4",
        "audio/mp4": ".m4a",
        "audio/mpeg": ".mp3",
        "video/webm": ".webm",
        "video/x-matroska": ".mkv",
    }
    base = content_type.split(";")[0].strip().lower()
    return mapping.get(base, ".bin")


@router.get("/redirect")
async def redirect_to_direct(
    task_id: str = Query(...),
    format_id: str = Query(...),
) -> RedirectResponse:
    if not settings.allow_redirect:
        raise _error(
            400,
            ErrorPayload(
                code="redirect_disabled",
                message="Redirect mode has been disabled by the server.",
            ),
        )
    try:
        direct_url, _ = ytdlp_service.prepare_direct_link(task_id, format_id)
    except ytdlp_service.ClientError as exc:
        raise _error(400, exc.payload) from exc
    return RedirectResponse(url=direct_url, status_code=302)
