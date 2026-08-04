"""The example app: one streaming endpoint, one static page, no AI.

Deliberately trivial. If this file grows features it becomes the project, and the
blueprint stops being the point. Forty lines is the budget.
"""

import asyncio
from collections.abc import AsyncIterator
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse, StreamingResponse

STATIC_DIR = Path(__file__).parent / "static"
DEFAULT_TEXT = "these words should arrive one at a time and not all at once"

app = FastAPI(title="Slipway example app")


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    """Liveness probe. `smoke.py` gates the deploy pipeline on this."""
    return {"status": "ok"}


async def _token_stream(text: str) -> AsyncIterator[str]:
    """Emit one server-sent event per word, standing in for a model's tokens."""
    for word in text.split():
        await asyncio.sleep(0.15)
        yield f"data: {word}\n\n"
    yield "data: [DONE]\n\n"


@app.get("/api/stream")
async def stream(text: str = DEFAULT_TEXT) -> StreamingResponse:
    """SSE endpoint whose whole job is to prove response streaming survives Lambda.

    If `AWS_LWA_INVOKE_MODE=response_stream` is missing, the adapter buffers and every
    word lands at once at the end — the response still looks correct, which is exactly
    what makes it easy to ship broken.
    """
    return StreamingResponse(
        _token_stream(text),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.get("/")
async def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")
