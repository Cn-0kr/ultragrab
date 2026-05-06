"""Request / response models for AI endpoints."""

from __future__ import annotations

from typing import List, Literal, Optional

from pydantic import BaseModel, Field


class TranscriptCueView(BaseModel):
    start_ms: int
    end_ms: int
    text: str


class TranscriptRequest(BaseModel):
    task_id: str = Field(..., min_length=8)
    subtitle_langs: Optional[List[str]] = None


class TranscriptResponse(BaseModel):
    task_id: str
    cues: List[TranscriptCueView]
    char_count: int
    truncated: bool


class SummarizeRequest(BaseModel):
    task_id: str = Field(..., min_length=8)
    subtitle_langs: Optional[List[str]] = None


class MindmapRequest(BaseModel):
    task_id: str = Field(..., min_length=8)
    subtitle_langs: Optional[List[str]] = None


class MindmapResponse(BaseModel):
    task_id: str
    mermaid: str


class ChatMessage(BaseModel):
    role: Literal["user", "assistant", "system"]
    content: str


class ChatRequest(BaseModel):
    task_id: str = Field(..., min_length=8)
    subtitle_langs: Optional[List[str]] = None
    messages: List[ChatMessage] = Field(..., min_length=1)
