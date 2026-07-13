from __future__ import annotations

from pathlib import Path


def test_ci_runs_required_quality_migration_build_and_security_gates() -> None:
    workflow = Path(".github/workflows/ci.yml").read_text(encoding="utf-8")

    for command in (
        "ruff check .",
        "ruff format --check .",
        "mypy src",
        "pytest -q",
        "alembic upgrade head",
        "alembic downgrade -1",
        "docker build",
        "pip-audit",
        "gitleaks",
    ):
        assert command in workflow


def test_ci_has_read_only_permissions() -> None:
    workflow = Path(".github/workflows/ci.yml").read_text(encoding="utf-8").lower()

    assert "contents: read" in workflow


def test_release_uses_immutable_image_tags_and_guarded_promotion() -> None:
    workflow = Path(".github/workflows/release.yml").read_text(encoding="utf-8")

    for contract in (
        "branches: [main]",
        "ghcr.io/${GITHUB_REPOSITORY,,}:${GITHUB_SHA}",
        "docker/build-push-action@v6",
        "environment:",
        "name: production",
        "DEPLOY_HEALTH_URL",
        "curl --fail",
        "adapter_version",
    ):
        assert contract in workflow

    assert ":latest" not in workflow
