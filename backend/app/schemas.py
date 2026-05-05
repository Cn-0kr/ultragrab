"""Pydantic models shared between routes and services."""

from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field, HttpUrl


DownloadMode = Literal["server", "proxy", "redirect"]
TaskStatus = Literal["queued", "parsing", "ready", "downloading", "done", "error"]


class ParseRequest(BaseModel):
    url: HttpUrl


class ParseBatchRequest(BaseModel):
    urls: List[HttpUrl] = Field(..., min_length=1)


class FormatOption(BaseModel):
    format_id: str
    ext: str
    label: str
    height: Optional[int] = None
    fps: Optional[float] = None
    tbr: Optional[float] = None
    vcodec: Optional[str] = None
    acodec: Optional[str] = None
    has_video: bool
    has_audio: bool
    filesize: Optional[int] = None
    is_recommended: bool = False
    kind: Literal["progressive", "video_only", "audio_only"] = "progressive"


class SubtitleLanguage(BaseModel):
    code: str
    name: Optional[str] = None
    is_automatic: bool = False


class VideoMetadata(BaseModel):
    title: Optional[str] = None
    thumbnail: Optional[str] = None
    duration: Optional[float] = None
    uploader: Optional[str] = None
    webpage_url: Optional[str] = None
    extractor: Optional[str] = None


class ParseResult(BaseModel):
    task_id: str
    metadata: VideoMetadata
    formats: List[FormatOption]
    subtitles: List[SubtitleLanguage]


class ParseBatchItem(BaseModel):
    url: str
    ok: bool
    result: Optional[ParseResult] = None
    error: Optional["ErrorPayload"] = None


class ParseBatchResponse(BaseModel):
    items: List[ParseBatchItem]


class DownloadRequest(BaseModel):
    task_id: str
    format_id: str
    mode: DownloadMode = "server"
    subtitle_langs: Optional[List[str]] = None


class DownloadResponse(BaseModel):
    task_id: str
    mode: DownloadMode
    status: TaskStatus
    download_url: Optional[str] = None
    expires_at: Optional[float] = None


class TaskView(BaseModel):
    task_id: str
    status: TaskStatus
    mode: Optional[DownloadMode] = None
    progress: float = 0.0
    speed: Optional[str] = None
    eta: Optional[int] = None
    download_url: Optional[str] = None
    file_name: Optional[str] = None
    metadata: Optional[VideoMetadata] = None
    error: Optional["ErrorPayload"] = None


class ErrorPayload(BaseModel):
    code: str
    message: str
    hint: Optional[str] = None


class ErrorResponse(BaseModel):
    error: ErrorPayload


ParseBatchItem.model_rebuild()
TaskView.model_rebuild()
