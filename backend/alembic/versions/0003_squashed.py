"""Squashed baseline #3 — the whole schema, built straight from the ORM models.

Replaces ``0002_squashed`` through ``0058``. Tables come from ``Base.metadata``
so the baseline cannot drift; enums are VARCHAR + CHECK, so no ``CREATE TYPE``.

Invalidates every existing stamp by design: run
``alembic stamp --purge 0003_squashed`` on a DB that already holds this schema
(db-migrations.md). Nothing here auto-stamps or self-heals.

Revision ID: 0003_squashed
Revises: (root)
Create Date: 2026-11-22
"""
from typing import Sequence, Union

import models  # noqa: F401 — registers every mapped class on Base.metadata
from alembic import op
from models.base import Base

revision: str = "0003_squashed"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    Base.metadata.create_all(op.get_bind())


def downgrade() -> None:
    Base.metadata.drop_all(op.get_bind())
