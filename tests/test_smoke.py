"""Prove the smoke test can tell streaming from buffering.

This is the test of the test. `smoke.py` is the pipeline's gate, and the failure it exists
to catch — a buffered response — returns 200 with a correct body. If the gate cannot
distinguish the two, it is decoration.

Two local servers stand in for the deployed app: one that writes each event as it goes,
and one that assembles the whole response and writes it at the end. Nothing here talks to
AWS.
"""

import threading
import time
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import httpx
import pytest
from smoke import check_page, check_streaming

WORDS = ["these", "words", "should", "arrive", "one", "at", "a", "time"]
DELAY = 0.08


class Handler(BaseHTTPRequestHandler):
    buffered = False

    def log_message(self, *_: object) -> None:
        """Silence the default per-request logging to stderr."""

    def do_GET(self) -> None:  # noqa: N802 — name fixed by BaseHTTPRequestHandler
        if self.path == "/":
            body = b"<!doctype html><title>t</title>"
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Transfer-Encoding", "chunked")
        self.end_headers()

        chunks = [f"data: {word}\n\n".encode() for word in WORDS]

        if self.buffered:
            # What a buffering proxy or a BUFFERED invoke mode produces: the client waits
            # the whole time, then receives everything at once.
            time.sleep(DELAY * len(WORDS))
            self.wfile.write(b"".join(f"{len(c):x}\r\n".encode() + c + b"\r\n" for c in chunks))
        else:
            for chunk in chunks:
                self.wfile.write(f"{len(chunk):x}\r\n".encode() + chunk + b"\r\n")
                self.wfile.flush()
                time.sleep(DELAY)

        self.wfile.write(b"0\r\n\r\n")
        self.wfile.flush()


def serve(buffered: bool) -> Iterator[str]:
    handler = type("BoundHandler", (Handler,), {"buffered": buffered})
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        server.server_close()


@pytest.fixture
def streaming_url() -> Iterator[str]:
    yield from serve(buffered=False)


@pytest.fixture
def buffered_url() -> Iterator[str]:
    yield from serve(buffered=True)


def test_streaming_response_passes(streaming_url: str) -> None:
    with httpx.Client(base_url=streaming_url, timeout=30.0) as client:
        result = check_streaming(client)

    assert result.passed, result.detail
    assert "real gaps" in result.detail


def test_buffered_response_fails(buffered_url: str) -> None:
    """The whole reason smoke.py measures timing instead of status codes."""
    with httpx.Client(base_url=buffered_url, timeout=30.0) as client:
        result = check_streaming(client)

    assert not result.passed
    assert "BUFFERED" in result.detail
    # The message has to name the three places it can break, or whoever sees it in CI at
    # 11pm has nowhere to start.
    assert "AWS_LWA_INVOKE_MODE" in result.detail
    assert "compress" in result.detail


def test_page_check_accepts_html(streaming_url: str) -> None:
    with httpx.Client(base_url=streaming_url, timeout=30.0) as client:
        result = check_page(client)

    assert result.passed, result.detail
