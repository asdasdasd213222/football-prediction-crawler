# Deployment And Rollback

## Scope

The repository provides a CI and image-publication contract. It does not
authorize an unattended production deployment. A human must review the source
authorization, configuration, secret resolution, host Edge state, and target
health endpoint before enabling a promotion.

## CI

`CI` runs on every pull request and push. It runs formatting, linting, type
checks, tests, Alembic upgrade/downgrade/upgrade, Compose validation, image
building, dependency auditing, and secret scanning. A pull request is only
mergeable when repository branch protection requires this workflow.

The `Release` workflow runs only for `main`. It publishes a GHCR image tagged
with the immutable commit SHA. It never promotes by default. A maintainer may
manually dispatch the workflow with `promote=true`; the job targets the GitHub
`production` environment. Configure that environment with required reviewers
before allowing promotion.

## Local Compose

Run `docker compose up --build -d` to build the application image and start
Redis, PostgreSQL, migrations, the HTTP worker, and the scheduler. The image
contains the non-secret example source configuration. Local ports bind only to
loopback addresses. Stop and remove disposable local state with
`docker compose down -v`.

## Health Gate And Version Record

Set the protected `DEPLOY_HEALTH_URL` environment secret only after a reviewed
target exists. The promotion job requires a successful `GET` health response
before it records the deployed image SHA and adapter version in the workflow
summary. A missing URL or failed request stops the workflow before any success
record is written.

## Rollback

Identify the last successful immutable SHA from the `Release` workflow, then
manually dispatch `Release` using that SHA as `image_tag` and set
`promote=true`. The same approval and health gate applies. Never use a mutable
tag to deploy.

## Host Edge Worker

The dedicated Edge worker is intentionally outside Compose because it uses a
Windows-local profile. Run `scripts/install_edge_worker_task.ps1` only after a
human has configured its non-secret runtime environment and an external health
file path. The task starts at user logon and Windows Task Scheduler restarts a
failed supervisor a bounded number of times. It does not automate login or
read browser storage.
