# P6 Deployment And Operations Implementation Plan

> **For agentic workers:** Execute each task with failing-first tests and mark
> TODO only after its local acceptance evidence passes.

**Goal:** Deliver local deployment, CI, and recovery operations for P6 without
production deployment.

## Task 1: P6-01 Local Compose Environment

Files: `compose.yaml`, `compose.dev.yaml`, `scripts/verify_local_stack.ps1`,
`scripts/run_migrations.ps1`, `tests/test_operations.py`, `README.md`.

1. Add a disposable PostgreSQL service, migration service, loopback metrics,
   health checks, restart policy, named volumes, non-root images, and resource
   limits.
2. Keep Edge as a documented host-only service with the existing worker script.
3. Add local health/migration acceptance tests and clean all containers/volumes
   created for the check.

## Task 2: P6-02 CI/CD Guardrails

Files: `.github/workflows/ci.yml`, `.github/workflows/security.yml`,
`scripts/verify_ci_contract.py`, `README.md`, `tests/test_ci_contract.py`.

1. Add PR checks for Ruff, format, Mypy, Pytest, migration round trip, image
   build, dependency audit, and secret scan.
2. Keep workflow permissions minimal; create no publish or deploy job.
3. Test workflow content for each required gate and deployment prohibition.

## Task 3: P6-03 Backup And Recovery

Files: `scripts/backup_local_postgres.ps1`, `scripts/restore_local_postgres.ps1`,
`docs/operations/backup-recovery.md`, `tests/test_backup_scripts.py`.

1. Validate loopback-only disposable database URLs and external backup paths.
2. Use `pg_dump`/`pg_restore` with environment-only credentials; never print
   the URL or password.
3. Run a local backup/restore count verification and document RPO/RTO,
   full-machine rebuild, and human review requirements.

## Final Verification

Run `ruff check .`, `ruff format --check .`, `mypy src`, `pytest -q`,
`docker compose config`, the disposable Compose health check, CI contract
tests, and local backup/restore acceptance. Do not deploy or publish images.
