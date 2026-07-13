from __future__ import annotations

from pathlib import Path


def test_backup_and_restore_scripts_require_local_database_and_external_paths() -> None:
    backup = Path("scripts/backup_local_postgres.ps1").read_text(encoding="utf-8")
    restore = Path("scripts/restore_local_postgres.ps1").read_text(encoding="utf-8")

    for script in (backup, restore):
        assert "DATABASE_URL" in script
        assert "127.0.0.1" in script
        assert "localhost" in script
        assert "outside the repository" in script
        assert "pg_dump" in backup
        assert "pg_restore" in restore


def test_backup_security_check_rejects_repository_and_broad_acl_paths() -> None:
    script = Path("scripts/verify_backup_security.ps1").read_text(encoding="utf-8")

    for contract in (
        "outside the repository root",
        "Get-Acl",
        "Everyone",
        "BUILTIN\\Users",
        "backup_security_verified=true",
    ):
        assert contract in script
