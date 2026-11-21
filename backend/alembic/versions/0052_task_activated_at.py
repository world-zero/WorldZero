"""task.activated_at: when a task first went live, for the Updates card (#3775).

``IF NOT EXISTS`` because a fresh DB's root already built the column.

Revision ID: 0052_task_activated_at
Revises: 0051_era_peak_level
Create Date: 2026-11-21
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0052_task_activated_at"
down_revision: Union[str, None] = "0051_era_peak_level"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE task ADD COLUMN IF NOT EXISTS activated_at TIMESTAMPTZ")
    op.execute("UPDATE task SET activated_at = created_at WHERE status <> 'pending'")


def downgrade() -> None:
    op.execute("ALTER TABLE task DROP COLUMN IF EXISTS activated_at")
