"""duel.live_at: when a duel went live, for the duel_live feed row and push (#3886).

Backfill: a settled duel's live_at is the later of its two sides' submit times.

Revision ID: 0055_duel_live_at
Revises: 0054_duel_rival_bonus
Create Date: 2026-11-21
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0055_duel_live_at"
down_revision: Union[str, None] = "0054_duel_rival_bonus"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE duel ADD COLUMN IF NOT EXISTS live_at TIMESTAMP WITH TIME ZONE"
    )
    op.execute(
        "UPDATE duel SET live_at = GREATEST(c.submitted_at, o.submitted_at) "
        "FROM praxis c, praxis o "
        "WHERE duel.status = 'settled' AND duel.live_at IS NULL "
        "AND c.id = duel.challenger_praxis_id AND o.id = duel.opponent_praxis_id"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE duel DROP COLUMN IF EXISTS live_at")
