"""Controlled local HTTP fixture server for adapter integration tests."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread
from time import sleep
from typing import Any, cast


@dataclass
class MockServerState:
    mode: str = "normal"
    items: list[dict[str, Any]] = field(default_factory=lambda: [{"id": "one"}])
    etag: str = '"v1"'


class MockCrawlerServer:
    """A no-network test server with repeatable source failure scenarios."""

    def __init__(self) -> None:
        self.state = MockServerState()
        state = self.state

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:  # noqa: N802
                if state.mode == "timeout":
                    sleep(1)
                if state.mode == "429":
                    self.send_response(429)
                    self.send_header("Retry-After", "7")
                    self.end_headers()
                    return
                if state.mode in {"500", "502", "503"}:
                    self.send_response(int(state.mode))
                    self.end_headers()
                    return
                if self.headers.get("If-None-Match") == state.etag:
                    self.send_response(304)
                    self.end_headers()
                    return
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("ETag", state.etag)
                self.end_headers()
                body: bytes
                if state.mode == "invalid_json":
                    body = b"{"
                elif state.mode == "empty":
                    body = b'{"items": []}'
                elif state.mode == "missing_field":
                    body = b'{"items": [{}]}'
                else:
                    body = json.dumps({"items": state.items}).encode()
                self.wfile.write(body)

            def log_message(self, format: str, *args: object) -> None:
                return

        self._server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self._thread = Thread(target=self._server.serve_forever, daemon=True)

    @property
    def url(self) -> str:
        host, port = cast(tuple[str, int], self._server.server_address)
        return f"http://{host}:{port}/items"

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._server.shutdown()
        self._thread.join()

    def __enter__(self) -> MockCrawlerServer:
        self.start()
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        self.stop()
