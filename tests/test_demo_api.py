from __future__ import annotations

import os
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import select

from multisite_crawler.adapters.base import AdapterRunner, FetchError, ParseError
from multisite_crawler.adapters.demo_api import DemoApiAdapter
from multisite_crawler.database import build_session_factory
from multisite_crawler.mock_server import MockCrawlerServer
from multisite_crawler.models import ChangeEvent, Record, Source
from multisite_crawler.record_repository import RecordRepository


def test_demo_api_adapter_runs_against_local_mock_server() -> None:
    with MockCrawlerServer() as server:
        server.state.items = [{"id": "one", "score": 1}]
        result = AdapterRunner(DemoApiAdapter(server.url)).run()
    assert result.items[0].external_id == "one"
    assert result.items[0].data["score"] == 1


def test_demo_api_adapter_handles_empty_invalid_and_http_failures() -> None:
    with MockCrawlerServer() as server:
        server.state.mode = "empty"
        assert AdapterRunner(DemoApiAdapter(server.url)).run().items == ()
        server.state.mode = "invalid_json"
        with pytest.raises(ParseError):
            AdapterRunner(DemoApiAdapter(server.url)).run()
        server.state.mode = "500"
        with pytest.raises(FetchError):
            AdapterRunner(DemoApiAdapter(server.url)).run()


@pytest.mark.integration
def test_demo_api_end_to_end_deduplicates_and_records_one_update() -> None:
    database_url = os.environ.get("TEST_DATABASE_URL")
    if database_url is None:
        pytest.skip("TEST_DATABASE_URL is required")
    migration_config = Config("alembic.ini")
    migration_config.set_main_option("sqlalchemy.url", database_url)
    command.upgrade(migration_config, "head")
    session_factory = build_session_factory(database_url)
    with MockCrawlerServer() as server, session_factory() as session:
        source = Source(source_key=f"demo-{uuid4()}", name="Demo API")
        session.add(source)
        session.commit()
        repository = RecordRepository(session)
        server.state.items = [{"id": "one", "score": 1}]
        result = AdapterRunner(DemoApiAdapter(server.url)).run()
        repository.persist_collection(source.id, result)
        session.commit()
        repository.persist_collection(source.id, result)
        session.commit()
        server.state.items = [{"id": "one", "score": 2}]
        repository.persist_collection(
            source.id, AdapterRunner(DemoApiAdapter(server.url)).run()
        )
        session.commit()
        records = session.scalars(
            select(Record).where(Record.source_id == source.id)
        ).all()
        events = session.scalars(
            select(ChangeEvent.event_type)
            .join(Record)
            .where(Record.source_id == source.id)
        ).all()
        assert len(records) == 1
        assert [event for event in events if event in {"created", "updated"}] == [
            "created",
            "updated",
        ]
