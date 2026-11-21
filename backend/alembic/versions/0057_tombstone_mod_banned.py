"""account_tombstone.mod_banned: a mod ban outlives account deletion (ADR-0081).

Revision ID: 0057_tombstone_mod_banned
Revises: 0056_admin_permissions
Create Date: 2026-11-21
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0057_tombstone_mod_banned"
down_revision: Union[str, None] = "0056_admin_permissions"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE account_tombstone "
        "ADD COLUMN IF NOT EXISTS mod_banned BOOLEAN NOT NULL DEFAULT false"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE account_tombstone DROP COLUMN IF EXISTS mod_banned")
