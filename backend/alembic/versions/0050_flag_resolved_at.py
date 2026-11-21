"""flag.resolved_at: a mod ruling closes the open flags, keeping them (#3726).

``IF NOT EXISTS`` because a fresh DB's root already built the column.

Revision ID: 0050_flag_resolved_at
Revises: 0049_duel_forfeited_at
Create Date: 2026-11-21
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0050_flag_resolved_at"
down_revision: Union[str, None] = "0049_duel_forfeited_at"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE flag ADD COLUMN IF NOT EXISTS resolved_at TIMESTAMPTZ")


def downgrade() -> None:
    op.execute("ALTER TABLE flag DROP COLUMN IF EXISTS resolved_at")
