# Repository Contract

## Mission And Scope

Build and maintain a stable, observable, and extensible multi-site data
collection system for authorized public or explicitly permitted sources.
Production collection is performed by the project's scheduler and workers;
agents plan, implement, test, review, diagnose, and maintain adapters.

Do not implement CAPTCHA bypasses, login bypasses, paywall bypasses, access
control evasion, or unreviewed production deployments. A task authorizes only
its selected TODO item and must not implement later phases opportunistically.

## Directory Ownership

- `src/` contains importable application code. Keep domain boundaries explicit.
- `src/.../adapters/` contains website-specific adapters only.
- `tests/` contains automated unit, integration, and regression tests.
- `configs/` contains validated, non-secret configuration templates.
- `scripts/` contains repeatable developer or operational helpers, not ad hoc
  production actions.
- `docs/` contains source cards, operational guidance, designs, and plans.

When a subdirectory needs stricter local rules, add a closer `AGENTS.md`. A
closer file may add requirements but must not weaken this repository contract.

## Architecture And Runtime Rules

- Use exactly one adapter per website. Site selectors, field mappings, and
  source-specific parsing stay in that adapter.
- Keep the scheduler, queues, and shared storage site-neutral. They must not
  contain website-specific parsing or selectors.
- Every task must be idempotent. Repeated delivery or retry must not create
  duplicate business records or duplicate change events.
- Prefer an official API, webhook, WebSocket, SSE, RSS, or ordinary HTTP before
  browser automation. Use browser automation only when authorized and required.
- Treat source configuration as validated input. Polling intervals may not be
  below 60 seconds unless a later approved task changes this rule.
- Preserve a redacted failure snapshot when parsing or browser work fails. A
  snapshot must exclude credentials, cookies, authorization headers, and
  personal data.
- Do not swallow exceptions. Raise or return explicit domain failures with
  source context, operation context, and the original cause where safe to log.

## Data And Migrations

- Store timestamps as Beijing local time (`Asia/Shanghai`) and keep external
  identifiers stable per source.
- When database work is introduced, use SQLAlchemy and Alembic; do not apply
  manual production DDL.
- Each migration must support and test upgrade, downgrade by one revision, and
  upgrade again: `alembic upgrade head`, `alembic downgrade -1`, then
  `alembic upgrade head`.

## Security And Compliance

- Never commit or log passwords, tokens, cookies, account data, private keys,
  proxy credentials, database credentials, or production environment values.
- Use environment variables or an approved secret manager for credentials;
  `.env.example` may contain only names and non-sensitive example values.
- Respect source authorization, terms, robots guidance, and rate limits. Stop
  and request review when authorization or compliance is unclear.

## Verification

Run these commands before completing any code or configuration change:

```powershell
ruff check .
ruff format --check .
mypy src
pytest -q
docker compose config
```

Run the migration verification commands in the Data And Migrations section for
every database change. Run an approved local end-to-end check when a task adds
container or runtime behavior.

## Definition Of Done

- Implement only the selected TODO item and cover its acceptance criteria.
- Add or update tests for behavior changes; do not use placeholder code as a
  completion claim.
- Update documentation for every behavior, configuration, operational, or
  interface change. If no documentation change is needed, state the reason in
  the task report.
- Report commands, results, remaining risks, and manual review points.
- Mark a TODO item complete only after its acceptance checks pass.
- Obtain human review before production deployment, release, or destructive
  operational action.
