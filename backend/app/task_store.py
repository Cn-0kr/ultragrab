"""In-memory task store.

Keeps metadata, format tables and download state for every task. Not persistent;
a restart wipes everything. Thread-safe via a module-level lock so both async
handlers and the yt-dlp worker thread can touch it.
"""

from __future__ import annotations

import shutil
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from .schemas import (
    DownloadMode,
    ErrorPayload,
    FormatOption,
    SubtitleLanguage,
    TaskStatus,
    TaskView,
    VideoMetadata,
)


@dataclass
class FormatRecord:
    """Internal copy of a format entry with the real (server-side only) url + headers."""

    option: FormatOption
    url: Optional[str] = None
    http_headers: Dict[str, str] = field(default_factory=dict)


@dataclass
class TaskRecord:
    task_id: str
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    status: TaskStatus = "queued"
    mode: Optional[DownloadMode] = None
    progress: float = 0.0
    speed: Optional[str] = None
    eta: Optional[int] = None

    metadata: Optional[VideoMetadata] = None
    formats: Dict[str, FormatRecord] = field(default_factory=dict)
    subtitles: List[SubtitleLanguage] = field(default_factory=list)

    file_path: Optional[Path] = None
    file_name: Optional[str] = None
    download_url: Optional[str] = None

    error: Optional[ErrorPayload] = None

    expires_at: Optional[float] = None

    def touch(self) -> None:
        self.updated_at = time.time()

    def to_view(self) -> TaskView:
        return TaskView(
            task_id=self.task_id,
            status=self.status,
            mode=self.mode,
            progress=self.progress,
            speed=self.speed,
            eta=self.eta,
            download_url=self.download_url,
            file_name=self.file_name,
            metadata=self.metadata,
            error=self.error,
        )


class TaskStore:
    def __init__(self) -> None:
        self._tasks: Dict[str, TaskRecord] = {}
        self._lock = threading.RLock()

    def create(self, task_id: str) -> TaskRecord:
        with self._lock:
            record = TaskRecord(task_id=task_id)
            self._tasks[task_id] = record
            return record

    def get(self, task_id: str) -> Optional[TaskRecord]:
        with self._lock:
            return self._tasks.get(task_id)

    def require(self, task_id: str) -> TaskRecord:
        record = self.get(task_id)
        if record is None:
            raise KeyError(task_id)
        return record

    def update(self, task_id: str, **fields: Any) -> Optional[TaskRecord]:
        with self._lock:
            record = self._tasks.get(task_id)
            if record is None:
                return None
            for key, value in fields.items():
                setattr(record, key, value)
            record.touch()
            return record

    def set_error(self, task_id: str, error: ErrorPayload) -> None:
        with self._lock:
            record = self._tasks.get(task_id)
            if record is None:
                return
            record.status = "error"
            record.error = error
            record.touch()

    def delete(self, task_id: str) -> None:
        with self._lock:
            record = self._tasks.pop(task_id, None)
        if record and record.file_path:
            _safe_remove(record.file_path.parent)

    def sweep_expired(self, retention_seconds: int) -> None:
        now = time.time()
        victims: List[TaskRecord] = []
        with self._lock:
            for task_id, record in list(self._tasks.items()):
                expiry = record.expires_at
                if expiry and now >= expiry:
                    victims.append(record)
                    self._tasks.pop(task_id, None)
                elif record.status in {"done", "error"} and now - record.updated_at > retention_seconds:
                    victims.append(record)
                    self._tasks.pop(task_id, None)
        for record in victims:
            if record.file_path:
                _safe_remove(record.file_path.parent)


def _safe_remove(path: Path) -> None:
    try:
        if path.is_file():
            path.unlink(missing_ok=True)
        elif path.is_dir():
            shutil.rmtree(path, ignore_errors=True)
    except Exception:
        pass


task_store = TaskStore()
