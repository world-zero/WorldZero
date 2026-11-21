"""account_tombstone.carried_from_account_id: find a carried ban from the old life.

Revision ID: 0058_tombstone_carried_from
Revises: 0057_tombstone_mod_banned
Create Date: 2026-11-21
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0058_tombstone_carried_from"
down_revision: Union[str, None] = "0057_tombstone_mod_banned"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE account_tombstone "
        "ADD COLUMN IF NOT EXISTS carried_from_account_id BIGINT REFERENCES account(id)"
    )


def downgrade() -> None:
    op.execute(
        "ALTER TABLE account_tombstone DROP COLUMN IF EXISTS carried_from_account_id"
    )
