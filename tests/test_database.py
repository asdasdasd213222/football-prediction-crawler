import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from time import monotonic
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import UniqueConstraint, create_engine, inspect, select, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from multisite_crawler.adapters.base import AdapterResult, CrawlItem, FetchResult
from multisite_crawler.database import (
    DatabaseUnavailableError,
    beijing_now,
    build_engine,
    build_session_factory,
    load_database_url,
    probe_connection,
)
from multisite_crawler.models import (
    ChangeEvent,
    CrawlRun,
    Record,
    Source,
    SourceFetchState,
)
from multisite_crawler.record_repository import RecordRepository


def test_beijing_now_returns_naive_beijing_clock_time() -> None:
    value = beijing_now()

    assert isinstance(value, datetime)
    assert value.tzinfo is None


def test_load_database_url_requires_named_variable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)

    with pytest.raises(DatabaseUnavailableError, match="DATABASE_URL is required"):
        load_database_url()


def test_probe_connection_hides_database_url_on_failure() -> None:
    database_url = "postgresql+psycopg://127.0.0.1:1/local"

    started_at = monotonic()
    with pytest.raises(DatabaseUnavailableError) as error:
        probe_connection(build_engine(database_url))

    elapsed_seconds = monotonic() - started_at

    assert "connection" in str(error.value).lower()
    assert database_url not in str(error.value)
    assert error.value.__cause__ is not None
    assert elapsed_seconds < 5


def test_models_use_postgresql_jsonb_and_beijing_timestamp_columns() -> None:
    assert isinstance(Source.__table__.c.settings.type, JSONB)
    assert isinstance(CrawlRun.__table__.c.error_metadata.type, JSONB)
    assert isinstance(Record.__table__.c.payload.type, JSONB)
    assert isinstance(ChangeEvent.__table__.c.payload.type, JSONB)
    assert Source.__table__.c.created_at.type.timezone is False
    assert Record.__table__.c.updated_at.type.timezone is False


def test_crawl_run_model_has_nullable_snapshot_path() -> None:
    column = CrawlRun.__table__.c.snapshot_path

    assert column.type.length == 1024
    assert column.nullable is True


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


def test_models_define_indexes_for_common_queries() -> None:
    assert {index.name for index in CrawlRun.__table__.indexes} >= {
        "ix_crawl_runs_source_started_at"
    }
    assert {index.name for index in Record.__table__.indexes} >= {
        "ix_records_source_is_active",
        "ix_records_source_updated_at",
    }
    assert {index.name for index in ChangeEvent.__table__.indexes} >= {
        "ix_change_events_record_occurred_at"
    }


def test_change_detection_models_include_source_state_and_missing_fields() -> None:
    assert SourceFetchState.__table__.c.source_id.unique is True
    assert SourceFetchState.__table__.c.raw_response_hash.type.length == 64
    assert Record.__table__.c.last_seen_at.type.timezone is False
    assert Record.__table__.c.missing_count.default.arg == 0


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
    assert "sources" in inspect(engine).get_table_names()
    assert "source_fetch_states" in inspect(engine).get_table_names()
    assert "snapshot_path" not in {
        column["name"] for column in inspect(engine).get_columns("crawl_runs")
    }

    command.upgrade(config, "head")
    assert "snapshot_path" in {
        column["name"] for column in inspect(engine).get_columns("crawl_runs")
    }


@pytest.mark.integration
def test_change_detection_migration_is_reversible() -> None:
    database_url = os.environ.get("TEST_DATABASE_URL")
    if database_url is None:
        pytest.skip("TEST_DATABASE_URL is required for PostgreSQL migration tests")

    config = Config(str(Path("alembic.ini")))
    config.set_main_option("sqlalchemy.url", database_url)
    command.upgrade(config, "head")
    engine = create_engine(database_url)
    assert "source_fetch_states" in inspect(engine).get_table_names()
    assert {"last_seen_at", "missing_count"} <= {
        column["name"] for column in inspect(engine).get_columns("records")
    }

    command.downgrade(config, "20260711_01")
    assert "source_fetch_states" not in inspect(engine).get_table_names()

    command.upgrade(config, "head")


@pytest.mark.integration
def test_snapshot_path_migration_is_reversible() -> None:
    database_url = os.environ.get("TEST_DATABASE_URL")
    if database_url is None:
        pytest.skip("TEST_DATABASE_URL is required for PostgreSQL migration tests")

    config = Config(str(Path("alembic.ini")))
    config.set_main_option("sqlalchemy.url", database_url)
    command.upgrade(config, "head")
    engine = create_engine(database_url)
    assert "snapshot_path" in {
        column["name"] for column in inspect(engine).get_columns("crawl_runs")
    }

    command.downgrade(config, "-1")
    assert "snapshot_path" not in {
        column["name"] for column in inspect(engine).get_columns("crawl_runs")
    }


@pytest.mark.integration
def test_change_detection_events_and_three_absences() -> None:
    database_url = os.environ.get("TEST_DATABASE_URL")
    if database_url is None:
        pytest.skip("TEST_DATABASE_URL is required for PostgreSQL integration tests")
    config = Config(str(Path("alembic.ini")))
    config.set_main_option("sqlalchemy.url", database_url)
    command.upgrade(config, "head")
    session_factory = build_session_factory(database_url)
    with session_factory() as session:
        source = Source(source_key=f"change-{uuid4()}", name="Change source")
        session.add(source)
        session.commit()
        repository = RecordRepository(session)
        first = AdapterResult(
            FetchResult(body=b"one", etag="etag-1"),
            (CrawlItem(external_id="record-1", data={"home": 1, "away": 0}),),
            "a" * 64,
        )
        same = AdapterResult(
            FetchResult(body=b"noise"),
            (CrawlItem(external_id="record-1", data={"away": 0, "home": 1}),),
            "b" * 64,
        )
        changed = AdapterResult(
            FetchResult(body=b"two"),
            (CrawlItem(external_id="record-1", data={"home": 2, "away": 0}),),
            "c" * 64,
        )
        empty = AdapterResult(FetchResult(body=b"empty"), (), "d" * 64)
        for result in (first, same, changed, empty, empty, empty):
            repository.persist_collection(source.id, result)
            session.commit()
        record = session.scalar(select(Record).where(Record.source_id == source.id))
        assert record is not None
        assert record.is_active is False
        events = session.scalars(
            select(ChangeEvent.event_type).where(ChangeEvent.record_id == record.id)
        ).all()
        assert events == ["created", "updated", "inactive"]
        repository.persist_collection(source.id, changed)
        session.commit()
        session.refresh(record)
        assert record.is_active is True
        assert record.missing_count == 0
        events_after_recovery = session.scalars(
            select(ChangeEvent.event_type).where(ChangeEvent.record_id == record.id)
        ).all()
        assert events_after_recovery == ["created", "updated", "inactive"]


@pytest.mark.integration
def test_concurrent_upsert_creates_one_record_and_event() -> None:
    database_url = os.environ.get("TEST_DATABASE_URL")
    if database_url is None:
        pytest.skip("TEST_DATABASE_URL is required for PostgreSQL integration tests")
    session_factory = build_session_factory(database_url)
    with session_factory() as session:
        source = Source(source_key=f"concurrent-{uuid4()}", name="Concurrent source")
        session.add(source)
        session.commit()
        source_id = source.id
    result = AdapterResult(
        FetchResult(body=b"concurrent"),
        (CrawlItem(external_id="record-1", data={"score": 1}),),
        "e" * 64,
    )

    def persist() -> None:
        with session_factory() as session:
            RecordRepository(session).persist_collection(source_id, result)
            session.commit()

    with ThreadPoolExecutor(max_workers=2) as executor:
        list(executor.map(lambda _: persist(), range(2)))
    with session_factory() as session:
        records = session.scalars(
            select(Record).where(Record.source_id == source_id)
        ).all()
        events = session.scalars(
            select(ChangeEvent).join(Record).where(Record.source_id == source_id)
        ).all()
        assert len(records) == 1
        assert [event.event_type for event in events] == ["created"]


@pytest.mark.integration
def test_alembic_cli_accepts_database_url() -> None:
    database_url = os.environ.get("TEST_DATABASE_URL")
    if database_url is None:
        pytest.skip("TEST_DATABASE_URL is required for PostgreSQL integration tests")

    environment = os.environ.copy()
    environment["DATABASE_URL"] = database_url
    environment.pop("TEST_DATABASE_URL", None)
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "current"],
        check=False,
        cwd=Path.cwd(),
        capture_output=True,
        env=environment,
        text=True,
    )

    assert result.returncode == 0, result.stderr


@pytest.mark.integration
def test_record_source_external_id_pair_cannot_be_inserted_twice() -> None:
    database_url = os.environ.get("TEST_DATABASE_URL")
    if database_url is None:
        pytest.skip("TEST_DATABASE_URL is required for PostgreSQL integration tests")

    session_factory = build_session_factory(database_url)
    with session_factory() as session:
        source = Source(source_key=f"test-{uuid4()}", name="Test source")
        session.add(source)
        session.commit()

        session.add(
            Record(
                source_id=source.id,
                external_id="external-1",
                content_hash="first-content",
                payload={},
            )
        )
        session.commit()

        session.add(
            Record(
                source_id=source.id,
                external_id="external-1",
                content_hash="duplicate-content",
                payload={},
            )
        )
        with pytest.raises(IntegrityError):
            session.commit()
        session.rollback()


@pytest.mark.integration
def test_application_database_role_cannot_create_schema_objects() -> None:
    database_url = os.environ.get("TEST_APPLICATION_DATABASE_URL")
    if database_url is None:
        pytest.skip("TEST_APPLICATION_DATABASE_URL is required for role tests")
    engine = create_engine(database_url)

    with engine.connect() as connection:
        assert connection.execute(text("SELECT 1")).scalar_one() == 1
        with pytest.raises(SQLAlchemyError):
            connection.execute(
                text("CREATE TABLE p8_application_role_denied (id integer)")
            )
