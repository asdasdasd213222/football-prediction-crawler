"""Add crawl run snapshot path.

Revision ID: 20260712_03
Revises: 20260711_02
Create Date: 2026-07-12
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260712_03"
down_revision: str | Sequence[str] | None = "20260711_02"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("crawl_runs", sa.Column("snapshot_path", sa.String(length=1024)))


def downgrade() -> None:
    op.drop_column("crawl_runs", "snapshot_path")
