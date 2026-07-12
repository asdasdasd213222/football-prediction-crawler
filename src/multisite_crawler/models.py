from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from multisite_crawler.database import beijing_now


class Base(DeclarativeBase):
    """Base class for the collection system's relational metadata."""


class Source(Base):
    """A configured data source with a stable internal identifier."""

    __tablename__ = "sources"
    __table_args__ = (
        UniqueConstraint("source_key", name="uq_sources_source_key"),
        Index("ix_sources_enabled", "enabled"),
    )

    id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )
    source_key: Mapped[str] = mapped_column(String(128), nullable=False)
    name: Mapped[str] = mapped_column(String(256), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    settings: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False), nullable=False, default=beijing_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False),
        nullable=False,
        default=beijing_now,
        onupdate=beijing_now,
    )


class CrawlRun(Base):
    """A single site-neutral execution attempt for a source."""

    __tablename__ = "crawl_runs"
    __table_args__ = (
        Index("ix_crawl_runs_source_started_at", "source_id", "started_at"),
    )

    id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )
    source_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("sources.id", name="fk_crawl_runs_source_id_sources"),
        nullable=False,
    )
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False), nullable=False, default=beijing_now
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=False))
    record_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_metadata: Mapped[dict[str, Any] | None] = mapped_column(JSONB)


class SourceFetchState(Base):
    """Latest source response validators and raw-response fingerprint."""

    __tablename__ = "source_fetch_states"

    id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )
    source_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("sources.id", name="fk_source_fetch_states_source_id_sources"),
        nullable=False,
        unique=True,
    )
    etag: Mapped[str | None] = mapped_column(String(512))
    last_modified: Mapped[str | None] = mapped_column(String(128))
    raw_response_hash: Mapped[str | None] = mapped_column(String(64))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False),
        nullable=False,
        default=beijing_now,
        onupdate=beijing_now,
    )


class Record(Base):
    """The current source-owned representation of a business record."""

    __tablename__ = "records"
    __table_args__ = (
        UniqueConstraint(
            "source_id",
            "external_id",
            name="uq_records_source_external_id",
        ),
        Index("ix_records_source_is_active", "source_id", "is_active"),
        Index("ix_records_source_updated_at", "source_id", "updated_at"),
    )

    id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )
    source_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("sources.id", name="fk_records_source_id_sources"),
        nullable=False,
    )
    external_id: Mapped[str] = mapped_column(String(256), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
    )
    content_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=False))
    missing_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False), nullable=False, default=beijing_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False),
        nullable=False,
        default=beijing_now,
        onupdate=beijing_now,
    )


class ChangeEvent(Base):
    """An append-only change notification associated with a stored record."""

    __tablename__ = "change_events"
    __table_args__ = (
        Index("ix_change_events_record_occurred_at", "record_id", "occurred_at"),
    )

    id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )
    record_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("records.id", name="fk_change_events_record_id_records"),
        nullable=False,
    )
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
    )
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False), nullable=False, default=beijing_now
    )
