from __future__ import annotations

from pathlib import Path

import yaml


def test_compose_defines_local_database_migration_and_host_edge_boundary() -> None:
    compose = yaml.safe_load(Path("compose.yaml").read_text(encoding="utf-8"))
    services = compose["services"]

    assert {"redis", "postgres", "migration", "worker-http", "scheduler"} <= set(
        services
    )
    assert "worker-browser" not in services
    assert services["postgres"]["healthcheck"]["test"] == [
        "CMD-SHELL",
        "pg_isready -U crawler -d crawler",
    ]
    assert services["migration"]["command"] == ["alembic", "upgrade", "head"]
    for name in ("redis", "postgres", "worker-http", "scheduler"):
        assert services[name]["restart"] == "unless-stopped"
        assert "resources" in services[name]["deploy"]

    for name in ("migration", "worker-http", "scheduler"):
        assert services[name]["image"] == "multisite-crawler:local"
        assert services[name]["build"] == "."


def test_host_edge_worker_is_managed_outside_compose() -> None:
    script = Path("scripts/install_edge_worker_task.ps1").read_text(encoding="utf-8")

    assert "MultisiteCrawlerEdgeWorker" in script
    assert "New-ScheduledTaskTrigger -AtLogOn" in script
    assert "New-ScheduledTaskSettingsSet -RestartCount" in script
    assert "outside the repository" in script


def test_compose_binds_development_ports_to_loopback_only() -> None:
    compose = yaml.safe_load(Path("compose.yaml").read_text(encoding="utf-8"))

    assert compose["services"]["redis"]["ports"] == ["127.0.0.1:6379:6379"]
    assert compose["services"]["postgres"]["ports"] == ["127.0.0.1:54329:5432"]


def test_application_image_keeps_non_secret_runtime_configuration() -> None:
    dockerfile = Path("Dockerfile").read_text(encoding="utf-8")
    dockerignore = Path(".dockerignore").read_text(encoding="utf-8")

    assert "COPY . ." in dockerfile
    assert "configs" not in dockerignore
    assert ".env" in dockerignore
