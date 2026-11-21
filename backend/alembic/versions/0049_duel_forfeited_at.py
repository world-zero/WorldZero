"""duel.forfeited_at: when a lock-out forfeited a duel (#3766).

``IF NOT EXISTS`` because a fresh DB's root already built the column.

Revision ID: 0049_duel_forfeited_at
Revises: 0048_task_backdoor
Create Date: 2026-11-21
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0049_duel_forfeited_at"
down_revision: Union[str, None] = "0048_task_backdoor"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE duel ADD COLUMN IF NOT EXISTS forfeited_at TIMESTAMPTZ")


def downgrade() -> None:
    op.execute("ALTER TABLE duel DROP COLUMN IF EXISTS forfeited_at")
