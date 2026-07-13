from __future__ import annotations

from pathlib import Path


def test_p8_uses_a_reproducible_five_minute_local_reliability_baseline() -> None:
    todo = Path("TODO.md").read_text(encoding="utf-8")
    script = Path("scripts/run_p8_local_reliability.ps1").read_text(encoding="utf-8")
    runbook = Path("docs/operations/pre-release-acceptance.md").read_text(
        encoding="utf-8"
    )

    assert "连续运行至少 5 分钟的本地稳定性验收" in todo
    assert "连续运行至少 72 小时" not in todo
    for contract in (
        "ValidateRange(300, 1800)",
        "redis_restart",
        "postgres_transient_unavailable",
        "worker_restart_recovery",
        "restart worker-http",
        "scheduler_restart",
        "p8_local_reliability=passed",
        "down --volumes --remove-orphans",
        "New-AsciiBuildContext",
        "robocopy",
        "multisite-crawler-p8-",
    ):
        assert contract in script
    assert "does not establish a\n72-hour reliability record" in runbook


def test_p8_production_release_stays_human_gated_and_source_specific() -> None:
    todo = Path("TODO.md").read_text(encoding="utf-8")
    source_card = Path("docs/sources/sporttery_zqspf.md").read_text(encoding="utf-8")
    intake = Path("docs/operations/source-approval-intake.md").read_text(
        encoding="utf-8"
    )

    assert "不授权 Codex 进行生产迁移、\n> 部署或启用任何真实网站" in todo
    assert "robots" in source_card
    assert "remains **not approved**" in source_card
    assert "does not constitute source operator or" in source_card
    assert "Source-side authorization" in intake
    assert "Do not send or commit authorization documents, passwords, cookies" in intake
