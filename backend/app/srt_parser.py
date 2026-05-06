"""Parse SubRip (.srt) subtitle files into timed cues."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import List

_TS = re.compile(
    r"(?P<h>\d{2}):(?P<m>\d{2}):(?P<s>\d{2}),(?P<ms>\d{3})\s*-->\s*"
    r"(?P<h2>\d{2}):(?P<m2>\d{2}):(?P<s2>\d{2}),(?P<ms2>\d{3})"
)


@dataclass
class TranscriptCue:
    index: int
    start_ms: int
    end_ms: int
    text: str


def _ts_to_ms(h: str, m: str, s: str, ms: str) -> int:
    return int(h) * 3600_000 + int(m) * 60_000 + int(s) * 1_000 + int(ms)


def parse_srt(content: str) -> List[TranscriptCue]:
    """Parse SRT text into cues."""

    text = content.lstrip("\ufeff").strip()
    if not text:
        return []

    blocks = re.split(r"\n\s*\n+", text)
    cues: List[TranscriptCue] = []
    idx = 0
    for block in blocks:
        lines = [ln.strip() for ln in block.splitlines() if ln.strip() != ""]
        if len(lines) < 2:
            continue
        cursor = 0
        if lines[0].isdigit():
            cursor = 1
            if cursor >= len(lines):
                continue
        ts_line = lines[cursor]
        m = _TS.match(ts_line.replace("\u200e", "").strip())
        if not m:
            continue
        start_ms = _ts_to_ms(m.group("h"), m.group("m"), m.group("s"), m.group("ms"))
        end_ms = _ts_to_ms(m.group("h2"), m.group("m2"), m.group("s2"), m.group("ms2"))
        body_lines = lines[cursor + 1 :]
        body = " ".join(body_lines)
        body = re.sub(r"<[^>]+>", "", body)
        body = body.replace("\u200b", "").strip()
        if not body:
            continue
        idx += 1
        cues.append(
            TranscriptCue(index=idx, start_ms=start_ms, end_ms=end_ms, text=body)
        )
    cues.sort(key=lambda c: (c.start_ms, c.index))
    return cues


def cues_to_plain_text(cues: List[TranscriptCue], max_chars: int | None = None) -> str:
    chunks = [c.text for c in cues]
    out = "\n".join(chunks)
    if max_chars is not None and len(out) > max_chars:
        return out[:max_chars]
    return out
