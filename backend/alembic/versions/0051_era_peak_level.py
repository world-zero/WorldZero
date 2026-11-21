"""character_stats.era_peak_level: per-era peak gating the level-up push (#3788).

``IF NOT EXISTS`` because a fresh DB's root already built the column.

Revision ID: 0051_era_peak_level
Revises: 0050_flag_resolved_at
Create Date: 2026-11-21
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0051_era_peak_level"
down_revision: Union[str, None] = "0050_flag_resolved_at"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE character_stats ADD COLUMN IF NOT EXISTS "
        "era_peak_level INTEGER NOT NULL DEFAULT 0"
    )
    op.execute("UPDATE character_stats SET era_peak_level = level")


def downgrade() -> None:
    op.execute("ALTER TABLE character_stats DROP COLUMN IF EXISTS era_peak_level")
