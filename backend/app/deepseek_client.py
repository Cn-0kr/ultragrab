"""DeepSeek OpenAI-compatible HTTP client (streaming + JSON completion)."""

from __future__ import annotations

import logging
from typing import Any, AsyncIterator, Dict, List, Optional

import httpx

from .ai_config import ai_max_transcript_chars, deepseek_api_base, deepseek_api_key, deepseek_model

logger = logging.getLogger(__name__)


def _headers() -> Dict[str, str]:
    return {
        "Authorization": f"Bearer {deepseek_api_key()}",
        "Content-Type": "application/json",
    }


async def stream_chat_completion(messages: List[Dict[str, str]]) -> AsyncIterator[bytes]:
    """Yield raw response bytes from DeepSeek SSE stream."""

    url = f"{deepseek_api_base()}/v1/chat/completions"
    payload = {
        "model": deepseek_model(),
        "messages": messages,
        "stream": True,
    }
    timeout = httpx.Timeout(60.0, read=300.0)
    async with httpx.AsyncClient(timeout=timeout) as client:
        async with client.stream(
            "POST",
            url,
            headers=_headers(),
            json=payload,
        ) as resp:
            if resp.status_code >= 400:
                text = await resp.aread()
                logger.warning("deepseek stream error %s %s", resp.status_code, text[:500])
                resp.raise_for_status()
            async for chunk in resp.aiter_bytes():
                if chunk:
                    yield chunk


async def chat_completion_text(
    messages: List[Dict[str, str]],
    *,
    json_mode: bool = False,
    max_tokens: Optional[int] = None,
) -> str:
    url = f"{deepseek_api_base()}/v1/chat/completions"
    body: Dict[str, Any] = {
        "model": deepseek_model(),
        "messages": messages,
        "stream": False,
    }
    if json_mode:
        body["response_format"] = {"type": "json_object"}
    if max_tokens is not None:
        body["max_tokens"] = max_tokens

    timeout = httpx.Timeout(60.0, read=180.0)
    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.post(url, headers=_headers(), json=body)
        if resp.status_code >= 400:
            logger.warning("deepseek completion error %s %s", resp.status_code, resp.text[:800])
        resp.raise_for_status()
        data = resp.json()
        try:
            return data["choices"][0]["message"]["content"]
        except (KeyError, IndexError) as exc:
            raise RuntimeError(f"unexpected DeepSeek response: {data!r}") from exc


def truncate_for_llm(transcript_plain: str) -> Tuple[str, bool]:
    limit = ai_max_transcript_chars()
    if len(transcript_plain) <= limit:
        return transcript_plain, False
    return transcript_plain[:limit], True
