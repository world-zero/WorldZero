"""Copy-proposal wire contracts. The token-only POST is the trust boundary."""

from pydantic import ConfigDict, Field, HttpUrl

from models.copy_proposal import LineStatus
from schemas.base import WireModel
from schemas.copy import (
    _KEY_PATTERN,
    _NS_PATTERN,
    MAX_KEY_LENGTH,
    MAX_NS_LENGTH,
    MAX_VALUE_LENGTH,
)

#: A PR touching more owner keys than this is no typo fix; refuse, never store.
MAX_LINES = 200


class CopyProposalLineIn(WireModel):
    ns: str = Field(..., min_length=1, max_length=MAX_NS_LENGTH, pattern=_NS_PATTERN)
    key: str = Field(..., min_length=1, max_length=MAX_KEY_LENGTH, pattern=_KEY_PATTERN)
    #: The live override when CI looked.
    owner_value: str = Field(..., max_length=MAX_VALUE_LENGTH)
    #: The PR's wording; null = the PR removes the key.
    proposed_value: str | None = Field(..., max_length=MAX_VALUE_LENGTH)


class CopyProposalIn(WireModel):
    pr_number: int = Field(..., ge=1)
    pr_url: HttpUrl
    lines: list[CopyProposalLineIn] = Field(..., min_length=1, max_length=MAX_LINES)


class CopyProposalLineOut(CopyProposalLineIn):
    status: LineStatus


class CopyProposalOut(WireModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    pr_number: int
    pr_url: str
    lines: list[CopyProposalLineOut]


class CopyProposalLineRef(WireModel):
    """The line to settle: ns + key, not an index, so a replace cannot shift it."""

    ns: str = Field(..., min_length=1, max_length=MAX_NS_LENGTH)
    key: str = Field(..., min_length=1, max_length=MAX_KEY_LENGTH)
