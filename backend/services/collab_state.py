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


def member_state(member: PraxisMember) -> MemberState:
    return MemberState.APPROVED if member.has_approved else MemberState.EDITING


def collab_state(praxis: Praxis) -> CollabState:
    if praxis.type != PraxisType.collab:
        raise ValueError("collab_state is for collab praxes only")
    # TODO(#4201): a 0-member collab (EMPTY) is reachable today; the collab-rules
    # PR stops the last member leaving, after which this can't fire.
    if not praxis.members:
        raise ValueError("collab with no members")
    if praxis.status == PraxisStatus.submitted:
        return CollabState.LIVE
    if praxis.status == PraxisStatus.pending:
        return CollabState.PROPOSED
    return CollabState.ALONE if len(praxis.members) == 1 else CollabState.DRAFTING
