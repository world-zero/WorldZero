"""praxis_member.faction_slug: the faction held when the praxis sealed (#3873).

Backfilled from the defection history: the faction a character left after the
praxis was submitted, else their current one. Unsealed rows get the current
faction, which the seal overwrites.

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
    op.execute(
        "ALTER TABLE praxis_member ADD COLUMN IF NOT EXISTS faction_slug VARCHAR"
    )
    op.execute(
        "UPDATE praxis_member pm SET faction_slug = COALESCE(("
        "SELECT d.faction_slug FROM faction_defection_history d "
        "JOIN praxis p ON p.id = pm.praxis_id "
        "WHERE d.character_id = pm.character_id AND d.defected_at > p.submitted_at "
        "ORDER BY d.defected_at LIMIT 1), c.faction_slug) "
        "FROM character c WHERE c.id = pm.character_id"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE praxis_member DROP COLUMN IF EXISTS faction_slug")
