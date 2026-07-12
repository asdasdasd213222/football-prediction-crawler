"""Loopback HTTP endpoint for Prometheus-compatible crawler metrics."""

from __future__ import annotations

from collections.abc import Callable
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from multisite_crawler.metrics import MetricsSnapshot, render_prometheus


def create_metrics_server(
    host: str,
    port: int,
    snapshot_reader: Callable[[], MetricsSnapshot],
) -> ThreadingHTTPServer:
    """Create a small server that exposes only the metrics exposition path."""
    if host != "127.0.0.1":
        raise ValueError("metrics service must bind to 127.0.0.1")

    class MetricsHandler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            if self.path != "/metrics":
                self.send_error(404)
                return
            body = render_prometheus(snapshot_reader()).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; version=0.0.4")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format: str, *args: object) -> None:
            del format, args

    return ThreadingHTTPServer((host, port), MetricsHandler)
