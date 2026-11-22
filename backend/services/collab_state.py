"""The collab state machine as one derived enum (#4191). Pure: no session, no I/O."""

import enum

from models.praxis import Praxis, PraxisMember, PraxisStatus, PraxisType


class CollabState(enum.Enum):
    ALONE = "alone"
    DRAFTING = "drafting"
    PROPOSED = "proposed"
    LIVE = "live"


class MemberState(enum.Enum):
    EDITING = "editing"
    APPROVED = "approved"


# The states each collab transition may start from (#4191, rulings Q2/Q6).
# Leave is not listed: it is allowed anywhere but for a sole member (Q2), which
# the member count decides, since a sole host can seal a LIVE collab of one.
_NOT_LIVE = frozenset({CollabState.ALONE, CollabState.DRAFTING, CollabState.PROPOSED})
COLLAB_ALLOWED_FROM: dict[str, frozenset[CollabState]] = {
    "invite": _NOT_LIVE,
    "accept": _NOT_LIVE,
    "kick": _NOT_LIVE,
    "media": _NOT_LIVE,
}


def member_state(member: PraxisMember) -> MemberState:
    return MemberState.APPROVED if member.has_approved else MemberState.EDITING


def collab_state(praxis: Praxis) -> CollabState:
    if praxis.type != PraxisType.collab:
        raise ValueError("collab_state is for collab praxes only")
    # Unreachable: the last member cannot leave a collab (Q2) and a kick is never self.
    assert praxis.members, "collab with no members"
    if praxis.status == PraxisStatus.submitted:
        return CollabState.LIVE
    if praxis.status == PraxisStatus.pending:
        return CollabState.PROPOSED
    return CollabState.ALONE if len(praxis.members) == 1 else CollabState.DRAFTING
