"""copy_proposal: CI-filed requests to change owner copy (#4280).

Carry-forward: a fresh DB already has the table from the 0003 root's create_all.

Revision ID: 0004_copy_proposal
Revises: 0003_squashed
Create Date: 2026-11-22
"""
from typing import Sequence, Union

from alembic import op
from models.copy_proposal import CopyProposal

revision: str = "0004_copy_proposal"
down_revision: Union[str, None] = "0003_squashed"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    CopyProposal.__table__.create(op.get_bind(), checkfirst=True)


def downgrade() -> None:
    op.drop_table("copy_proposal")
