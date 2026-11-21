"""duel.rival_bonus: the pair were mutual foes when the duel was accepted (#3858).

No backfill: existing duels stay false (pre-launch).

Revision ID: 0054_duel_rival_bonus
Revises: 0053_praxis_member_faction_slug
Create Date: 2026-11-21
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0054_duel_rival_bonus"
down_revision: Union[str, None] = "0053_praxis_member_faction_slug"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE duel ADD COLUMN IF NOT EXISTS rival_bonus BOOLEAN NOT NULL DEFAULT false"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE duel DROP COLUMN IF EXISTS rival_bonus")
