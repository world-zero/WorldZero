"""praxis_member.faction_slug: the faction held when the member joined (#3873).

Backfilled from each character's CURRENT faction: the best record we have, since
nothing stored the faction at the time. Rows of members who defected earlier keep
the wrong stamp; only new rows are exact.

Revision ID: 0053_praxis_member_faction_slug
Revises: 0052_task_activated_at
Create Date: 2026-11-21
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0053_praxis_member_faction_slug"
down_revision: Union[str, None] = "0052_task_activated_at"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE praxis_member ADD COLUMN IF NOT EXISTS faction_slug VARCHAR")
    op.execute(
        "UPDATE praxis_member pm SET faction_slug = c.faction_slug "
        "FROM character c WHERE c.id = pm.character_id"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE praxis_member DROP COLUMN IF EXISTS faction_slug")
