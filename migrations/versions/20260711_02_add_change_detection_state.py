"""Add change detection state.

Revision ID: 20260711_02
Revises: 20260711_01
Create Date: 2026-07-11
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260711_02"
down_revision: str | Sequence[str] | None = "20260711_01"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "source_fetch_states",
        sa.Column("id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("source_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("etag", sa.String(length=512), nullable=True),
        sa.Column("last_modified", sa.String(length=128), nullable=True),
        sa.Column("raw_response_hash", sa.String(length=64), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=False), nullable=False),
        sa.ForeignKeyConstraint(
            ["source_id"],
            ["sources.id"],
            name="fk_source_fetch_states_source_id_sources",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_source_fetch_states"),
        sa.UniqueConstraint("source_id", name="uq_source_fetch_states_source_id"),
    )
    op.add_column("records", sa.Column("last_seen_at", sa.DateTime(), nullable=True))
    op.add_column(
        "records",
        sa.Column("missing_count", sa.Integer(), nullable=False, server_default="0"),
    )
    op.alter_column("records", "missing_count", server_default=None)


def downgrade() -> None:
    op.drop_column("records", "missing_count")
    op.drop_column("records", "last_seen_at")
    op.drop_table("source_fetch_states")
