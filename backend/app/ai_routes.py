"""AI summarization routes (DeepSeek + platform subtitles + ASR fallback)."""

from __future__ import annotations

import asyncio
import json
import logging
from typing import AsyncIterator, Dict, List, Optional, Tuple

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from .ai_config import ai_max_transcript_chars, deepseek_api_key
from .ai_schemas import (
    ChatRequest,
    MindmapRequest,
    MindmapResponse,
    SummarizeRequest,
    TranscriptCueView,
    TranscriptRequest,
    TranscriptResponse,
)
from .asr_service import asr_for_task, is_asr_configured
from .deepseek_client import chat_completion_text, stream_chat_completion, truncate_for_llm
from .schemas import ErrorPayload
from .srt_parser import TranscriptCue, cues_to_plain_text
from .subtitle_extractor import fetch_subtitles_to_cues, resolve_langs_for_task
from .task_store import task_store
from . import transcript_cache

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["ai"])

_SUMMARY_SYSTEM = (
    "你是专业的中文学习助手。根据用户提供的视频字幕文本，输出结构化摘要："
    "先用一两句话概括主题，再用 Markdown 二级标题分段（如 ## 核心观点、## 关键步骤、## 术语与定义、## 行动建议）。"
    "语气简洁，便于复习；不要编造字幕中不存在的事实。"
)

_MINDMAP_SYSTEM = (
    "你是专业的「视频知识导图」助手，遵循认知负荷原则（主干 5–7 条、层级清晰、关键词优先）。\n"
    "用户输入为视频字幕文本（可能较短）。你必须输出**唯一** JSON：{\"mermaid\": \"...\"}，"
    "其中 mermaid 为**可直接渲染**的 Mermaid **mindmap** 源码字符串（注意：使用 mindmap 图类型，不是 flowchart）。\n\n"
    "**Mermaid mindmap 语法示例**（严格遵循缩进层级，用两个空格缩进）：\n"
    "```\nmindmap\n  root((视频主题))\n    分支A\n      细节1\n      细节2\n    分支B\n      细节3\n```\n\n"
    "**结构要求：**\n"
    "1. 根节点：`root((视频主题))`，主题≤12字，概括整段字幕。\n"
    "2. 一级分支：**至少 4 条、至多 7 条**，每条代表一大语义块（场景/论点/步骤/人物/结论等）。\n"
    "3. 二级及以下：在确有信息量时再展开；单条一级分支下建议 1–5 个子节点；总节点数建议 **12–28**。\n"
    "4. 节点文案：优先**名词短语或短句**，每条≤10个汉字或等价长度；禁止整句照搬字幕长段落。\n"
    "5. 若字幕很短：也不得只做「两点一线」；应从「背景/内容/细节/感受或结论」等维度**合理拆分**出多条分支。\n"
    "6. 节点文案直接写纯文字即可，不需要节点 id。**禁止在节点文案中使用括号 `()` `(())` `[]` `{}`**——Mermaid mindmap 的节点默认自带样式，加括号会导致语法错误。\n"
    "7. **重要**：mindmap 类型靠缩进（2个空格为一级）表示层级关系，不要使用箭头 `-->`。\n"
    "8. 禁止 Markdown 代码围栏；禁止输出 JSON 以外的文字；禁止 classDef / class 等 flowchart 语法。\n"
    "9. 节点文案中禁止使用引号 `\"` `'`、反引号、冒号 `:`、分号 `;`。如需表达，用中文标点或省略。\n"
)

_JSON_FENCE = "```"


def _parse_llm_json(raw: str) -> dict:
    """Accept raw JSON or ```json ... ``` wrapped output."""

    text = (raw or "").strip()
    if text.startswith(_JSON_FENCE):
        lines = text.split("\n")
        if lines and lines[0].startswith(_JSON_FENCE):
            lines = lines[1:]
        if lines and lines[-1].strip().startswith(_JSON_FENCE):
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    return json.loads(text)

_CHAT_SYSTEM_TEMPLATE = (
    "你是严谨的中文助手，只能根据下列「视频字幕摘录」回答问题；不确定就说明不清楚，不要编造。"
    "若提问与字幕无关，请简要拒绝。\n\n---字幕摘录开始---\n{body}\n---字幕摘录结束---"
)


def _http_error(code: str, message: str, hint: Optional[str] = None, status_code: int = 400) -> HTTPException:
    payload = ErrorPayload(code=code, message=message, hint=hint).model_dump()
    return HTTPException(status_code=status_code, detail=payload)


def _require_deepseek() -> None:
    if not deepseek_api_key():
        raise _http_error(
            "ai_disabled",
            "AI 功能未配置：请在服务端设置 DEEPSEEK_API_KEY。",
            hint="复制 backend/.env.example 中的示例变量到 .env。",
            status_code=503,
        )


def _append_bilibili_cookie_tip(task_id: str, hint: str) -> str:
    """Bilibili often hides subtitle tracks unless the player API sees login cookies."""

    rec = task_store.get(task_id)
    ext = ((rec.metadata.extractor or "") if rec and rec.metadata else "").lower()
    if "bili" not in ext:
        return hint
    tip = (
        "（B 站：网页登录能看到字幕但接口返回空时，请在 backend/.env 设置 "
        "YTDLP_COOKIE_FILE=浏览器导出的 cookies.txt（Netscape），重启后端后重新解析该链接。）"
    )
    return f"{hint} {tip}"


async def _try_asr_fallback(task_id: str) -> Optional[Tuple[List[TranscriptCue], str]]:
    """Attempt ASR transcription as fallback. Returns None on failure."""

    if not is_asr_configured():
        return None
    try:
        cues, plain = await asr_for_task(task_id)
        if cues and plain:
            return cues, plain
    except Exception as exc:
        logger.warning("ASR fallback failed for task %s: %s", task_id, exc)
    return None


async def _ensure_transcript(
    task_id: str, subtitle_langs: Optional[List[str]]
) -> Tuple[List[str], List[TranscriptCue], str]:
    record = task_store.get(task_id)
    if record is None:
        raise _http_error("task_not_found", "Task does not exist.", status_code=404)

    # --- Phase 1: try platform subtitles ---
    no_platform_subs = False
    try:
        langs = await asyncio.to_thread(resolve_langs_for_task, task_id, subtitle_langs)
    except ValueError as exc:
        raise _http_error("invalid_request", str(exc)) from exc
    except KeyError as exc:
        raise _http_error("task_not_found", "Task does not exist.", status_code=404) from exc
    except RuntimeError as exc:
        msg = str(exc) or "no subtitles"
        if "no subtitles" in msg.lower():
            no_platform_subs = True
            langs = []
        else:
            raise _http_error("subtitle_resolve_failed", msg, status_code=502) from exc

    if not no_platform_subs:
        cached = transcript_cache.get(task_id, langs)
        if cached:
            cues, plain_full = cached
            return langs, cues, plain_full

        try:
            cues = await asyncio.to_thread(fetch_subtitles_to_cues, task_id, langs)
        except RuntimeError:
            cues = []

        if cues:
            plain_full = cues_to_plain_text(cues)
            transcript_cache.put(task_id, langs, cues, plain_full)
            return langs, cues, plain_full

        no_platform_subs = True

    # --- Phase 2: ASR fallback ---
    asr_cache_key = ["_asr"]
    cached = transcript_cache.get(task_id, asr_cache_key)
    if cached:
        cues, plain_full = cached
        return asr_cache_key, cues, plain_full

    result = await _try_asr_fallback(task_id)
    if result:
        cues, plain_full = result
        transcript_cache.put(task_id, asr_cache_key, cues, plain_full)
        return asr_cache_key, cues, plain_full

    # --- Both paths failed ---
    hint = "可更换含字幕的视频稍后再试。"
    if not is_asr_configured():
        hint += " 或在 backend/.env 配置 SILICONFLOW_API_KEY 启用 ASR 语音转写。"
    raise _http_error(
        "no_subtitles",
        "当前视频没有可用的平台字幕，ASR 语音转写也未成功。",
        hint=_append_bilibili_cookie_tip(task_id, hint),
    )


@router.post("/transcript", response_model=TranscriptResponse)
async def transcript(payload: TranscriptRequest) -> TranscriptResponse:
    langs, cues, plain_full = await _ensure_transcript(payload.task_id, payload.subtitle_langs)
    del langs
    views = [TranscriptCueView(start_ms=c.start_ms, end_ms=c.end_ms, text=c.text) for c in cues]
    truncated = len(plain_full) > ai_max_transcript_chars()
    return TranscriptResponse(
        task_id=payload.task_id,
        cues=views,
        char_count=len(plain_full),
        truncated=truncated,
    )


@router.post("/summarize")
async def summarize(payload: SummarizeRequest) -> StreamingResponse:
    _require_deepseek()
    _langs, _cues, plain_full = await _ensure_transcript(payload.task_id, payload.subtitle_langs)

    async def byte_iter() -> AsyncIterator[bytes]:
        chunk_plain, _ = truncate_for_llm(plain_full)
        messages: List[Dict[str, str]] = [
            {"role": "system", "content": _SUMMARY_SYSTEM},
            {
                "role": "user",
                "content": "以下为视频字幕全文（若过长可能被截断）。请输出摘要：\n\n" + chunk_plain,
            },
        ]
        try:
            async for part in stream_chat_completion(messages):
                yield part
        except Exception as exc:  # pragma: no cover
            logger.exception("summarize stream failed")
            err_msg = json.dumps({"error": {"code": "ai_upstream_error", "message": str(exc)}})
            yield f"data: {err_msg}\n\n".encode()

    headers = {
        "Cache-Control": "no-cache",
        "Connection": "keep-alive",
        "X-Accel-Buffering": "no",
    }
    return StreamingResponse(byte_iter(), media_type="text/event-stream", headers=headers)


@router.post("/mindmap", response_model=MindmapResponse)
async def mindmap(payload: MindmapRequest) -> MindmapResponse:
    _require_deepseek()
    _langs, _cues, plain_full = await _ensure_transcript(payload.task_id, payload.subtitle_langs)

    chunk_plain, _ = truncate_for_llm(plain_full)
    messages = [
        {"role": "system", "content": _MINDMAP_SYSTEM},
        {"role": "user", "content": chunk_plain},
    ]
    try:
        raw = await chat_completion_text(messages, json_mode=True, max_tokens=4096)
        data = _parse_llm_json(raw)
        mermaid = data.get("mermaid") if isinstance(data, dict) else None
        if isinstance(mermaid, (dict, list)):
            mermaid = json.dumps(mermaid, ensure_ascii=False)
        if not isinstance(mermaid, str) or not mermaid.strip():
            raise ValueError("missing mermaid")
        return MindmapResponse(task_id=payload.task_id, mermaid=mermaid.strip())
    except Exception as exc:
        logger.warning("mindmap generation failed: %s", exc)
        raise _http_error(
            "mindmap_failed",
            "思维导图生成失败，请稍后重试。",
            hint=str(exc)[:200],
            status_code=502,
        ) from exc


@router.post("/chat")
async def chat(payload: ChatRequest) -> StreamingResponse:
    _require_deepseek()
    _langs, _cues, plain_full = await _ensure_transcript(payload.task_id, payload.subtitle_langs)

    chunk_plain, _ = truncate_for_llm(plain_full)
    system_msg = _CHAT_SYSTEM_TEMPLATE.format(body=chunk_plain)

    convo: List[Dict[str, str]] = [{"role": "system", "content": system_msg}]
    for m in payload.messages:
        if m.role not in {"user", "assistant"}:
            continue
        convo.append({"role": m.role, "content": m.content})

    async def byte_iter() -> AsyncIterator[bytes]:
        try:
            async for part in stream_chat_completion(convo):
                yield part
        except Exception as exc:  # pragma: no cover
            logger.exception("chat stream failed")
            err_msg = json.dumps({"error": {"code": "ai_upstream_error", "message": str(exc)}})
            yield f"data: {err_msg}\n\n".encode()

    headers = {
        "Cache-Control": "no-cache",
        "Connection": "keep-alive",
        "X-Accel-Buffering": "no",
    }
    return StreamingResponse(byte_iter(), media_type="text/event-stream", headers=headers)
