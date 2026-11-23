"""A CI-filed ask to change owner copy; nothing applies until she approves."""

import enum

from sqlalchemy import BigInteger, Identity, Integer, String, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from models.base import Base
from models.mixins import TimestampMixin


class LineStatus(str, enum.Enum):
    open = "open"
    approved = "approved"
    rejected = "rejected"


class CopyProposal(TimestampMixin, Base):
    __tablename__ = "copy_proposal"

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    #: One row per PR: a re-run replaces its lines.
    pr_number: Mapped[int] = mapped_column(Integer, unique=True, nullable=False)
    pr_url: Mapped[str] = mapped_column(String(255), nullable=False)
    #: ``[{ns, key, owner_value, proposed_value | null, status}]``.
    lines: Mapped[list] = mapped_column(
        JSONB, nullable=False, server_default=text("'[]'::jsonb")
    )
