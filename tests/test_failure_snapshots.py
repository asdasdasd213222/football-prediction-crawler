from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path
from uuid import UUID

import pytest

from multisite_crawler.failure_snapshots import (
    FailureSnapshotWriter,
    SnapshotConfigurationError,
    SnapshotRequest,
    cleanup_expired_snapshots,
)

RUN_ID = UUID("00000000-0000-0000-0000-000000000001")


def test_snapshot_uses_run_id_and_redacts_headers_body_and_url(tmp_path: Path) -> None:
    root = tmp_path.parent / "crawler-snapshots"
    writer = FailureSnapshotWriter(root, repository_root=tmp_path, max_bytes=4096)

    artifact = writer.write(
        SnapshotRequest(
            source_id="demo_api",
            crawl_run_id=RUN_ID,
            headers={"ETag": "safe", "Cookie": "secret"},
            body={
                "name": "safe",
                "token": "secret",
                "url": "https://example.invalid/path?account=1",
            },
        )
    )

    serialized = artifact.response_path.read_text(encoding="utf-8")
    assert str(RUN_ID) in artifact.response_path.name
    assert '"ETag":"safe"' in serialized
    assert "secret" not in serialized
    assert "account=1" not in serialized


def test_snapshot_root_must_be_external_to_repository(tmp_path: Path) -> None:
    with pytest.raises(SnapshotConfigurationError, match="outside the repository"):
        FailureSnapshotWriter(tmp_path, repository_root=tmp_path, max_bytes=4096)


def test_cleanup_removes_only_expired_files_below_snapshot_root(tmp_path: Path) -> None:
    root = tmp_path.parent / "crawler-snapshots"
    root.mkdir(exist_ok=True)
    expired = root / "expired.json"
    fresh = root / "fresh.json"
    expired.write_text("{}", encoding="utf-8")
    fresh.write_text("{}", encoding="utf-8")
    old = datetime(2026, 7, 1).timestamp()
    os.utime(expired, (old, old))

    removed = cleanup_expired_snapshots(
        root,
        cutoff=datetime(2026, 7, 7),
        repository_root=tmp_path,
    )

    assert removed == 1
    assert not expired.exists()
    assert fresh.exists()
