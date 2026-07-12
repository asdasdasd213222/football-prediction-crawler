"""Create the collection persistence schema.

Revision ID: 20260711_01
Revises:
Create Date: 2026-07-11
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "20260711_01"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "sources",
        sa.Column("id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("source_key", sa.String(length=128), nullable=False),
        sa.Column("name", sa.String(length=256), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("settings", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=False), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=False), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_sources"),
        sa.UniqueConstraint("source_key", name="uq_sources_source_key"),
    )
    op.create_index("ix_sources_enabled", "sources", ["enabled"], unique=False)

    op.create_table(
        "crawl_runs",
        sa.Column("id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("source_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=False), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=False), nullable=True),
        sa.Column("record_count", sa.Integer(), nullable=False),
        sa.Column(
            "error_metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
        sa.ForeignKeyConstraint(
            ["source_id"],
            ["sources.id"],
            name="fk_crawl_runs_source_id_sources",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_crawl_runs"),
    )
    op.create_index(
        "ix_crawl_runs_source_started_at",
        "crawl_runs",
        ["source_id", "started_at"],
        unique=False,
    )

    op.create_table(
        "records",
        sa.Column("id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("source_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("external_id", sa.String(length=256), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("content_hash", sa.String(length=128), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=False), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=False), nullable=False),
        sa.ForeignKeyConstraint(
            ["source_id"],
            ["sources.id"],
            name="fk_records_source_id_sources",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_records"),
        sa.UniqueConstraint(
            "source_id",
            "external_id",
            name="uq_records_source_external_id",
        ),
    )
    op.create_index(
        "ix_records_source_is_active",
        "records",
        ["source_id", "is_active"],
        unique=False,
    )
    op.create_index(
        "ix_records_source_updated_at",
        "records",
        ["source_id", "updated_at"],
        unique=False,
    )

    op.create_table(
        "change_events",
        sa.Column("id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("record_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=False), nullable=False),
        sa.ForeignKeyConstraint(
            ["record_id"],
            ["records.id"],
            name="fk_change_events_record_id_records",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_change_events"),
    )
    op.create_index(
        "ix_change_events_record_occurred_at",
        "change_events",
        ["record_id", "occurred_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_change_events_record_occurred_at", table_name="change_events")
    op.drop_table("change_events")
    op.drop_index("ix_records_source_updated_at", table_name="records")
    op.drop_index("ix_records_source_is_active", table_name="records")
    op.drop_table("records")
    op.drop_index("ix_crawl_runs_source_started_at", table_name="crawl_runs")
    op.drop_table("crawl_runs")
    op.drop_index("ix_sources_enabled", table_name="sources")
    op.drop_table("sources")
