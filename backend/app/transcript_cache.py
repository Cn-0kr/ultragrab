"""In-memory cache for parsed transcripts keyed by task_id + resolved subtitle langs."""

from __future__ import annotations

import threading
import time
from typing import Dict, List, Optional, Tuple

from .srt_parser import TranscriptCue


_lock = threading.RLock()
_data: Dict[str, Tuple[List[TranscriptCue], str, float]] = {}

TTL_SECONDS = 3600


def _cache_key(task_id: str, resolved_langs: List[str]) -> str:
    return f"{task_id}::{'|'.join(resolved_langs)}"


def _prune_locked(now: float) -> None:
    dead = [k for k, (_, _, ts) in _data.items() if now - ts > TTL_SECONDS]
    for k in dead:
        _data.pop(k, None)


def put(task_id: str, resolved_langs: List[str], cues: List[TranscriptCue], plain: str) -> None:
    with _lock:
        _prune_locked(time.time())
        _data[_cache_key(task_id, resolved_langs)] = (cues, plain, time.time())


def get(task_id: str, resolved_langs: List[str]) -> Optional[Tuple[List[TranscriptCue], str]]:
    with _lock:
        now = time.time()
        _prune_locked(now)
        row = _data.get(_cache_key(task_id, resolved_langs))
        if row is None:
            return None
        cues, plain, _ts = row
        _data[_cache_key(task_id, resolved_langs)] = (cues, plain, now)
        return cues, plain


def invalidate_task(task_id: str) -> None:
    with _lock:
        prefix = f"{task_id}::"
        for k in list(_data.keys()):
            if k.startswith(prefix):
                _data.pop(k, None)
