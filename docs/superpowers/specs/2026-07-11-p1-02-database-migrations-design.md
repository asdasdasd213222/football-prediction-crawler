# P1-02 Database And Migration Design

## Scope

Add PostgreSQL persistence foundations only: connection management, SQLAlchemy
models, Alembic migration support, and focused tests. This task does not add
collection, scheduling, adapters, queues, browser automation, credentials, or
production deployment.

## Time Convention

All application timestamps represent Beijing civil time (`Asia/Shanghai`). They
will use PostgreSQL `TIMESTAMP WITHOUT TIME ZONE` columns and naive Python
`datetime` values produced only by a shared `beijing_now()` helper. This avoids
implicit conversion by a PostgreSQL session timezone. Callers must supply or
interpret every stored timestamp as Beijing time; a later task may add explicit
conversion at an external boundary when needed.

## Database Interface

`multisite_crawler.database` will create a synchronous SQLAlchemy engine from
an explicit PostgreSQL URL and expose a session factory. A connection probe
will wrap driver and SQLAlchemy connection failures in a `DatabaseUnavailableError`
that preserves context and the original cause without logging the URL or any
credentials. URLs are read from the caller or `DATABASE_URL`; no URL value is
committed to the repository.

## Schema

The initial Alembic revision will create these site-neutral tables:

- `sources`: stable UUID primary key, unique source key, display name, enabled
  flag, non-secret configuration JSONB, and Beijing creation/update timestamps.
- `crawl_runs`: UUID primary key, source foreign key, status, start/end times,
  counters, and optional redacted error metadata JSONB.
- `records`: UUID primary key, source foreign key, stable external identifier,
  payload JSONB, content hash, active flag, and Beijing creation/update
  timestamps. A unique constraint on `(source_id, external_id)` makes repeated
  delivery reject duplicate business records.
- `change_events`: UUID primary key, record foreign key, event type, payload
  JSONB, and a Beijing occurrence timestamp.

The revision creates indexes for source lookup, crawl-run history by source and
start time, record freshness and activity by source, and event history by
record and occurrence time. PostgreSQL JSONB is used for all structured
metadata and payload fields.

## Migrations And Tests

Alembic will derive metadata from the SQLAlchemy models and provide one
reversible initial revision. Migration integration tests will use an explicit,
disposable PostgreSQL URL from `TEST_DATABASE_URL`; they will exercise upgrade
to head, downgrade one revision, then upgrade again. Unit tests will cover the
connection error contract and the record uniqueness constraint using the same
explicit test database. Tests will fail clearly when the database URL is not
provided rather than silently targeting a shared or production database.

## Dependencies And Documentation

Add SQLAlchemy, Alembic, and Psycopg as runtime dependencies. Add only the
names `DATABASE_URL` and `TEST_DATABASE_URL` to the environment template, and
document local database verification without embedding a credential or a
production endpoint.

## Verification

Run the repository quality gates plus a disposable local PostgreSQL migration
check. The acceptance evidence must show upgrade, downgrade, re-upgrade,
duplicate-record rejection, and a clear failed-connection error before
checking P1-02 in `TODO.md`.
