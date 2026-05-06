"""FastAPI application entry point."""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from .settings import settings
from .routes import router as api_router
from .ai_routes import router as ai_router
from .task_store import task_store
from .ytdlp_service import sweep_orphan_downloads

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("app")


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    stop_event = asyncio.Event()

    async def sweeper() -> None:
        logger.info("File sweeper started (retention=%ss)", settings.file_retention)
        while not stop_event.is_set():
            try:
                task_store.sweep_expired(settings.file_retention)
                sweep_orphan_downloads(settings.download_dir, settings.file_retention)
            except Exception:  # pragma: no cover
                logger.exception("sweep failed")
            try:
                await asyncio.wait_for(stop_event.wait(), timeout=60)
            except asyncio.TimeoutError:
                continue

    sweep_orphan_downloads(settings.download_dir, settings.file_retention)
    task = asyncio.create_task(sweeper())
    try:
        yield
    finally:
        stop_event.set()
        await task


app = FastAPI(
    title="Universal Video Downloader API",
    description="yt-dlp-powered API for parsing, downloading and proxying public video links.",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins or ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(StarletteHTTPException)
async def handle_http_exc(_, exc: StarletteHTTPException) -> JSONResponse:
    if isinstance(exc.detail, dict) and "code" in exc.detail:
        return JSONResponse(status_code=exc.status_code, content={"error": exc.detail})
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": {"code": "http_error", "message": str(exc.detail)}},
    )


@app.exception_handler(RequestValidationError)
async def handle_validation_exc(_, exc: RequestValidationError) -> JSONResponse:
    return JSONResponse(
        status_code=422,
        content={
            "error": {
                "code": "invalid_request",
                "message": "Request payload failed validation.",
                "hint": str(exc.errors()[0]) if exc.errors() else None,
            }
        },
    )


app.include_router(api_router)
app.include_router(ai_router)


@app.get("/")
async def root() -> dict:
    return {"name": "universal-video-downloader", "docs": "/docs"}
