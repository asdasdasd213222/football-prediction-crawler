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
        "pg_isready -U crawler_owner -d crawler",
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


def test_compose_restricts_the_data_plane_and_separates_database_roles() -> None:
    compose = yaml.safe_load(Path("compose.yaml").read_text(encoding="utf-8"))
    services = compose["services"]
    role_sql = Path("configs/postgres/init/10-create-application-role.sql").read_text(
        encoding="utf-8"
    )

    assert compose["networks"]["crawler-internal"]["internal"] is True
    for service_name in ("redis", "postgres", "migration", "worker-http", "scheduler"):
        assert services[service_name]["networks"] == ["crawler-internal"]
    assert "crawler_app" in compose["x-app-environment"]["DATABASE_URL"]
    assert "crawler_owner" in compose["x-migration-environment"]["DATABASE_URL"]
    assert services["migration"]["environment"] == compose["x-migration-environment"]
    assert services["postgres"]["healthcheck"]["test"] == [
        "CMD-SHELL",
        "pg_isready -U crawler_owner -d crawler",
    ]
    for contract in (
        "CREATE ROLE crawler_app",
        "NOSUPERUSER",
        "REVOKE CREATE ON SCHEMA public FROM PUBLIC",
        "GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO crawler_app",
    ):
        assert contract in role_sql


def test_application_image_keeps_non_secret_runtime_configuration() -> None:
    dockerfile = Path("Dockerfile").read_text(encoding="utf-8")
    dockerignore = Path(".dockerignore").read_text(encoding="utf-8")

    assert "COPY . ." in dockerfile
    assert "configs" not in dockerignore
    assert ".env" in dockerignore


def test_application_image_uses_an_unprivileged_runtime_user() -> None:
    dockerfile = Path("Dockerfile").read_text(encoding="utf-8")

    assert "useradd --create-home --uid 10001 crawler" in dockerfile
    assert dockerfile.rstrip().endswith("USER crawler")
