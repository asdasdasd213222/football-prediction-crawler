# P1-02 Database And Migration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add PostgreSQL persistence models and a reversible initial Alembic migration with verified idempotency constraints.

**Architecture:** A small database module owns URL validation, engine/session creation, connection probing, and the Beijing-time clock helper. SQLAlchemy declarative models own the site-neutral schema, while Alembic imports only their metadata to create a single reversible initial revision. Database integration tests use an explicit disposable `TEST_DATABASE_URL` and never infer or target a production endpoint.

**Tech Stack:** Python 3.12, SQLAlchemy 2, Alembic, Psycopg 3, PostgreSQL 16, Pytest, Ruff, Mypy.

## Global Constraints

- Implement P1-02 only; do not add crawler, scheduler, adapter, queue, browser, credential, or deployment behavior.
- Store every timestamp as Beijing civil time (`Asia/Shanghai`) in PostgreSQL `TIMESTAMP WITHOUT TIME ZONE` columns.
- Use SQLAlchemy and Alembic for all schema changes; do not apply manual production DDL.
- JSON payloads and metadata use PostgreSQL JSONB.
- Never commit, log, or document a real credential, cookie, token, or production database URL.
- Migration evidence must run `alembic upgrade head`, `alembic downgrade -1`, then `alembic upgrade head` against a disposable local PostgreSQL instance.
- Run `ruff check .`, `ruff format --check .`, `mypy src`, `pytest -q`, and `docker compose config` before checking P1-02 in `TODO.md`.
- Do not create a Git commit because the shared repository contains pre-existing untracked work outside this task.

---

### Task 1: Database Runtime And Beijing Clock

**Files:**
- Modify: `pyproject.toml`
- Modify: `.env.example`
- Create: `src/multisite_crawler/database.py`
- Test: `tests/test_database.py`

**Interfaces:**
- Produces: `beijing_now() -> datetime`, `DatabaseUnavailableError`, `load_database_url(variable_name: str = "DATABASE_URL") -> str`, `build_engine(database_url: str) -> Engine`, `build_session_factory(database_url: str) -> sessionmaker[Session]`, and `probe_connection(engine: Engine) -> None`.
- Consumes: SQLAlchemy's synchronous `Engine`, `Session`, and `sessionmaker` APIs.

- [ ] **Step 1: Add the failing unit tests**

```python
from datetime import datetime

import pytest

from multisite_crawler.database import (
    DatabaseUnavailableError,
    beijing_now,
    build_engine,
    load_database_url,
    probe_connection,
)


def test_beijing_now_returns_naive_beijing_clock_time() -> None:
    value = beijing_now()

    assert isinstance(value, datetime)
    assert value.tzinfo is None


def test_load_database_url_requires_named_variable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)

    with pytest.raises(DatabaseUnavailableError, match="DATABASE_URL is required"):
        load_database_url()


def test_probe_connection_hides_database_url_on_failure() -> None:
    database_url = "postgresql+psycopg://127.0.0.1:1/local"

    with pytest.raises(DatabaseUnavailableError) as error:
        probe_connection(build_engine(database_url))

    assert "connection" in str(error.value).lower()
    assert database_url not in str(error.value)
    assert error.value.__cause__ is not None
```

- [ ] **Step 2: Run the test file and verify the expected missing-module failure**

Run: `.\\.venv\\Scripts\\python.exe -m pytest tests/test_database.py -q`

Expected: FAIL during collection because `multisite_crawler.database` does not exist.

- [ ] **Step 3: Add runtime dependencies and the minimal database implementation**

Add these runtime dependencies in `pyproject.toml`:

```toml
"alembic>=1.13,<2",
"psycopg[binary]>=3.2,<4",
"SQLAlchemy>=2.0,<3",
```

Add only these names to `.env.example`:

```dotenv
DATABASE_URL=
TEST_DATABASE_URL=
```

Implement `src/multisite_crawler/database.py` with an explicit `ZoneInfo("Asia/Shanghai")` conversion followed by `.replace(tzinfo=None)`, `pool_pre_ping=True`, and a `SELECT 1` probe. Catch only SQLAlchemy `SQLAlchemyError` while probing, raise `DatabaseUnavailableError("Database connection probe failed.") from error`, and do not interpolate the URL in any error message.

- [ ] **Step 4: Install the declared dependencies and verify the unit tests pass**

Run: `.\\.venv\\Scripts\\python.exe -m pip install -e ".[dev]"`

Run: `.\\.venv\\Scripts\\python.exe -m pytest tests/test_database.py -q`

Expected: PASS; the invalid loopback URL produces the wrapped error without exposing its value.

### Task 2: SQLAlchemy Models And Schema Metadata

**Files:**
- Create: `src/multisite_crawler/models.py`
- Modify: `tests/test_database.py`

**Interfaces:**
- Consumes: `beijing_now` from `multisite_crawler.database`.
- Produces: `Base`, `Source`, `CrawlRun`, `Record`, and `ChangeEvent` declarative models with `Base.metadata` ready for Alembic.

- [ ] **Step 1: Add failing metadata tests**

```python
from sqlalchemy import UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB

from multisite_crawler.models import ChangeEvent, CrawlRun, Record, Source


def test_models_use_postgresql_jsonb_and_beijing_timestamp_columns() -> None:
    assert isinstance(Source.__table__.c.settings.type, JSONB)
    assert isinstance(CrawlRun.__table__.c.error_metadata.type, JSONB)
    assert isinstance(Record.__table__.c.payload.type, JSONB)
    assert isinstance(ChangeEvent.__table__.c.payload.type, JSONB)
    assert Source.__table__.c.created_at.type.timezone is False
    assert Record.__table__.c.updated_at.type.timezone is False


def test_records_define_source_external_id_uniqueness() -> None:
    constraints = [
        constraint
        for constraint in Record.__table__.constraints
        if isinstance(constraint, UniqueConstraint)
    ]

    assert any(
        tuple(column.name for column in constraint.columns)
        == ("source_id", "external_id")
        for constraint in constraints
    )
```

- [ ] **Step 2: Run the metadata tests and verify the expected missing-module failure**

Run: `.\\.venv\\Scripts\\python.exe -m pytest tests/test_database.py -q`

Expected: FAIL during collection because `multisite_crawler.models` does not exist.

- [ ] **Step 3: Implement the minimum declarative schema**

Create `models.py` with `DeclarativeBase`, PostgreSQL `JSONB`, `Uuid`, named
foreign keys, named indexes, and named constraints. Each table has a UUID
primary key. `sources` includes `source_key`, `name`, `enabled`, `settings`,
`created_at`, and `updated_at`; `crawl_runs` includes `source_id`, `status`,
`started_at`, `finished_at`, `record_count`, and `error_metadata`; `records`
includes `source_id`, `external_id`, `payload`, `content_hash`, `is_active`,
`created_at`, and `updated_at`; `change_events` includes `record_id`,
`event_type`, `payload`, and `occurred_at`. Use `default=beijing_now` for
application-created timestamps and `onupdate=beijing_now` for update columns.

- [ ] **Step 4: Verify model metadata tests pass**

Run: `.\\.venv\\Scripts\\python.exe -m pytest tests/test_database.py -q`

Expected: PASS; metadata exposes JSONB columns, naive timestamp types, and the
source/external-id unique constraint.

### Task 3: Alembic Environment And Reversible Initial Revision

**Files:**
- Create: `alembic.ini`
- Create: `migrations/env.py`
- Create: `migrations/script.py.mako`
- Create: `migrations/versions/20260711_01_create_collection_schema.py`
- Modify: `tests/test_database.py`

**Interfaces:**
- Consumes: `Base.metadata` from `multisite_crawler.models` and the explicit `TEST_DATABASE_URL` environment variable.
- Produces: an Alembic environment where `alembic upgrade head`, `alembic downgrade -1`, and `alembic upgrade head` operate on the supplied disposable database.

- [ ] **Step 1: Add the failing migration integration test**

```python
import os
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect


@pytest.mark.integration
def test_initial_migration_upgrades_downgrades_and_upgrades_again() -> None:
    database_url = os.environ.get("TEST_DATABASE_URL")
    if database_url is None:
        pytest.skip("TEST_DATABASE_URL is required for PostgreSQL migration tests")

    config = Config(str(Path("alembic.ini")))
    config.set_main_option("sqlalchemy.url", database_url)
    command.upgrade(config, "head")

    engine = create_engine(database_url)
    assert {"sources", "crawl_runs", "records", "change_events"} <= set(
        inspect(engine).get_table_names()
    )

    command.downgrade(config, "-1")
    assert "sources" not in inspect(engine).get_table_names()

    command.upgrade(config, "head")
    assert "records" in inspect(engine).get_table_names()
```

- [ ] **Step 2: Run the integration test against the disposable database and verify it fails**

Run: `.\\.venv\\Scripts\\python.exe -m pytest tests/test_database.py::test_initial_migration_upgrades_downgrades_and_upgrades_again -q` after setting `TEST_DATABASE_URL` in the current shell to the disposable local database.

Expected: FAIL because the Alembic configuration and revision do not exist.

- [ ] **Step 3: Implement the Alembic environment and initial revision**

Configure `migrations/env.py` to read `config.get_main_option("sqlalchemy.url")`, set `target_metadata = Base.metadata`, and refuse a blank URL with a clear `RuntimeError`. The revision must call `op.create_table` with PostgreSQL JSONB columns, then `op.create_index` for the planned lookup paths. Its downgrade must drop indexes before dropping tables in dependency order: `change_events`, `records`, `crawl_runs`, then `sources`.

- [ ] **Step 4: Verify the migration cycle passes on the disposable database**

Run: `.\\.venv\\Scripts\\python.exe -m pytest tests/test_database.py::test_initial_migration_upgrades_downgrades_and_upgrades_again -q` with the same shell-local `TEST_DATABASE_URL`.

Expected: PASS; the schema exists after the first and third upgrade, and is absent after the downgrade.

### Task 4: Database Constraint Evidence, Documentation, And Acceptance

**Files:**
- Modify: `tests/test_database.py`
- Modify: `README.md`
- Modify: `TODO.md` only after every required check passes

**Interfaces:**
- Consumes: `build_session_factory`, `Source`, `Record`, and the Alembic head schema.
- Produces: executable evidence that duplicate source/external business records are rejected and clear local database setup guidance.

- [ ] **Step 1: Add a failing duplicate-record integration test**

```python
import os
from uuid import uuid4

import pytest
from sqlalchemy.exc import IntegrityError

from multisite_crawler.database import build_session_factory
from multisite_crawler.models import Record, Source


@pytest.mark.integration
def test_record_source_external_id_pair_cannot_be_inserted_twice() -> None:
    database_url = os.environ.get("TEST_DATABASE_URL")
    if database_url is None:
        pytest.skip("TEST_DATABASE_URL is required for PostgreSQL integration tests")

    session_factory = build_session_factory(database_url)
    with session_factory.begin() as session:
        source = Source(source_key=f"test-{uuid4()}", name="Test source")
        session.add(source)
        session.flush()
        session.add(Record(source_id=source.id, external_id="external-1", payload={}))
        session.flush()
        session.add(Record(source_id=source.id, external_id="external-1", payload={}))
        with pytest.raises(IntegrityError):
            session.flush()
```

- [ ] **Step 2: Run it after applying the migration and verify it fails for the missing model behavior or schema**

Run: `.\\.venv\\Scripts\\python.exe -m pytest tests/test_database.py::test_record_source_external_id_pair_cannot_be_inserted_twice -q` with the current shell's `TEST_DATABASE_URL` set to the disposable local database.

Expected: FAIL until the unique constraint and test transaction handling are complete.

- [ ] **Step 3: Make the test transaction-safe and document the local contract**

Use a nested transaction or separate transactions so the expected `IntegrityError` does not poison the test session. Extend `README.md` with the names of `DATABASE_URL` and `TEST_DATABASE_URL`, state that they must be disposable local PostgreSQL URLs for migration tests, and state that timestamps are Beijing local time (`Asia/Shanghai`). Do not add a URL value or startup/deployment instructions.

- [ ] **Step 4: Run the complete acceptance suite**

Run these commands after starting a disposable local PostgreSQL container and setting only the current shell's `TEST_DATABASE_URL`:

```powershell
.\\.venv\\Scripts\\ruff.exe check .
.\\.venv\\Scripts\\ruff.exe format --check .
.\\.venv\\Scripts\\mypy.exe src
.\\.venv\\Scripts\\python.exe -m pytest -q
$env:DOCKER_CONFIG = Join-Path $env:TEMP "codex-docker-client"
docker compose config
```

Also run the explicit Alembic cycle:

```powershell
$env:DATABASE_URL = $env:TEST_DATABASE_URL
.\\.venv\\Scripts\\alembic.exe upgrade head
.\\.venv\\Scripts\\alembic.exe downgrade -1
.\\.venv\\Scripts\\alembic.exe upgrade head
```

Expected: every quality command passes; the migration cycle completes; the
duplicate-record test raises `IntegrityError`; and the invalid loopback probe
raises `DatabaseUnavailableError` without exposing its URL.

- [ ] **Step 5: Check P1-02 only after acceptance passes**

Replace every P1-02 acceptance and delivery checkbox in `TODO.md` with `[x]`
only when Step 4 has passed. Leave every later TODO item unchanged and report
that no production deployment was performed.

## Self-Review

1. **Spec coverage:** Task 1 covers connection management, failures, and the
   Beijing clock. Task 2 covers all four SQLAlchemy models, JSONB, indexes, and
   the idempotency constraint. Task 3 covers Alembic and the required
   upgrade/downgrade/re-upgrade sequence. Task 4 covers duplicate insertion,
   documentation, quality gates, acceptance evidence, and TODO timing.
2. **Placeholder scan:** No unfinished-content placeholders remain. Every
   implementation action names its files, interface, test behavior, and
   command; the temporary database URL remains shell-local and is never written
   to the repository.
3. **Type consistency:** `beijing_now`, `build_engine`, `build_session_factory`,
   `probe_connection`, `Base`, `Source`, and `Record` use the same names in all
   tasks. Migration tests use `TEST_DATABASE_URL`; operational commands use
   `DATABASE_URL` only after copying the disposable test value within the
   current shell.
