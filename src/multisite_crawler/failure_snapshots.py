"""Private, redacted failure snapshots for offline regression investigation."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from uuid import UUID

from multisite_crawler.observability import redact_value

_SOURCE_ID = re.compile(r"^[a-z0-9_-]+$")
_HEADER_ALLOWLIST = {"content-type", "etag", "last-modified"}


class SnapshotConfigurationError(ValueError):
    """Raised when a snapshot location could expose repository artifacts."""


@dataclass(frozen=True)
class SnapshotRequest:
    """Typed redactable material from a failed adapter operation."""

    source_id: str
    crawl_run_id: UUID
    headers: dict[str, str]
    body: dict[str, object] | list[object]


@dataclass(frozen=True)
class SnapshotArtifact:
    """Private response artifact path associated with one failed crawl run."""

    response_path: Path


class FailureSnapshotWriter:
    """Write bounded redacted JSON artifacts to an external directory only."""

    def __init__(self, root: Path, *, repository_root: Path, max_bytes: int) -> None:
        if max_bytes <= 0:
            raise SnapshotConfigurationError("max_bytes must be positive")
        self._root = _external_root(root, repository_root)
        self._max_bytes = max_bytes
        self._root.mkdir(parents=True, exist_ok=True)

    def write(self, request: SnapshotRequest) -> SnapshotArtifact:
        if not _SOURCE_ID.fullmatch(request.source_id):
            raise ValueError("source_id must match [a-z0-9_-]+")
        payload = {
            "headers": {
                key: value
                for key, value in request.headers.items()
                if key.lower() in _HEADER_ALLOWLIST
            },
            "body": redact_value(request.body),
        }
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode(
            "utf-8"
        )
        if len(encoded) > self._max_bytes:
            raise ValueError("redacted snapshot exceeds configured maximum size")
        response_path = (
            self._root / f"{request.source_id}_{request.crawl_run_id}_response.json"
        )
        response_path.write_bytes(encoded)
        return SnapshotArtifact(response_path)


def cleanup_expired_snapshots(
    root: Path,
    *,
    cutoff: datetime,
    repository_root: Path,
) -> int:
    """Remove only expired files below one validated external snapshot root."""
    resolved_root = _external_root(root, repository_root)
    if not resolved_root.exists():
        return 0
    removed = 0
    cutoff_timestamp = cutoff.timestamp()
    for candidate in resolved_root.rglob("*"):
        if candidate.is_file() and candidate.stat().st_mtime < cutoff_timestamp:
            candidate.unlink()
            removed += 1
    return removed


def _external_root(root: Path, repository_root: Path) -> Path:
    if not root.is_absolute():
        raise SnapshotConfigurationError("snapshot root must be an absolute path")
    resolved_root = root.resolve()
    if resolved_root.is_relative_to(repository_root.resolve()):
        raise SnapshotConfigurationError(
            "snapshot root must be outside the repository root"
        )
    return resolved_root
