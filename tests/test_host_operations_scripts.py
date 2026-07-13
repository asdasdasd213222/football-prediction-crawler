from __future__ import annotations

from pathlib import Path


def test_edge_supervisor_has_bounded_restart_and_no_login_handling() -> None:
    script = Path("scripts/start_edge_worker_supervisor.ps1").read_text(
        encoding="utf-8"
    )

    assert "MaxRestarts" in script
    assert "BROWSER_WORKER_HEALTH_FILE" in script
    assert "outside the repository" in script
    assert "Start-Process" in script
    assert "cookie" not in script.lower()
    assert "password" not in script.lower()


def test_backup_schedule_installer_keeps_database_url_out_of_task_definition() -> None:
    script = Path("scripts/install_local_backup_task.ps1").read_text(encoding="utf-8")

    assert "Register-ScheduledTask" in script
    assert "backup_local_postgres.ps1" in script
    assert "outside the repository" in script
    assert "DATABASE_URL" not in script


def test_host_edge_task_uses_bounded_restarts_without_login_data() -> None:
    script = Path("scripts/install_edge_worker_task.ps1").read_text(encoding="utf-8")

    assert "MultisiteCrawlerEdgeWorker" in script
    assert "RestartCount" in script
    assert "outside the repository" in script
    assert "cookie" not in script.lower()
    assert "password" not in script.lower()
