"""The duel state machine as one derived enum (#4191). Pure: no session, no I/O."""

import enum
from datetime import datetime, timedelta
from typing import Optional

from game_config import EraConfig
from models.duel import Duel, DuelStatus
from models.praxis import Praxis, PraxisStatus


class DuelState(enum.Enum):
    CHALLENGED = "challenged"
    DRAFTING = "drafting"
    ONE_CAST = "one_cast"
    AWAITING_HONEST_SIDE = "awaiting_honest_side"
    LIVE = "live"
    LIVE_FORFEITED = "live_forfeited"
    DISSOLVED = "dissolved"
    RESOLVED = "resolved"
    NO_CONTEST = "no_contest"


# The states each transition may start from (#4191 tables, rulings Q1/Q4/Q5).
# "cast" is a duel side's submit: refused while CHALLENGED (Q1). "reopen" is
# its unsubmit: refused once forfeited, so a decided duel keeps both sides cast.
ALLOWED_FROM: dict[str, frozenset[DuelState]] = {
    "accept": frozenset({DuelState.CHALLENGED}),
    "decline": frozenset({DuelState.CHALLENGED}),
    "dissolve": frozenset(
        {DuelState.CHALLENGED, DuelState.DRAFTING, DuelState.ONE_CAST}
    ),
    "cast": frozenset(
        {
            DuelState.DRAFTING,
            DuelState.ONE_CAST,
            DuelState.AWAITING_HONEST_SIDE,
            DuelState.LIVE,
            DuelState.LIVE_FORFEITED,
        }
    ),
    "reopen": frozenset(
        {
            DuelState.CHALLENGED,
            DuelState.DISSOLVED,
            DuelState.ONE_CAST,
            DuelState.AWAITING_HONEST_SIDE,
            DuelState.LIVE,
        }
    ),
}

#: The states a winner may be named from (Q10); never a draft or a no-contest.
CONTEST_STATES = frozenset(
    {DuelState.LIVE, DuelState.LIVE_FORFEITED, DuelState.RESOLVED}
)


def challenge_lapsed(duel: Duel, now: datetime, era: EraConfig) -> bool:
    """Unanswered past ``duel_challenge_lapse_days``; ``None`` never lapses."""
    days = era.duel_challenge_lapse_days
    return days is not None and now >= duel.created_at + timedelta(days=days)


def _cast(praxis: Optional[Praxis]) -> bool:
    return praxis is not None and praxis.status == PraxisStatus.submitted


def duel_state(
    duel: Duel,
    challenger_praxis: Optional[Praxis],
    opponent_praxis: Optional[Praxis],
    now: datetime,
    era: EraConfig,
) -> DuelState:
    forfeited = duel.forfeited_by_character_id is not None
    status = duel.status
    if status == DuelStatus.declined:
        return DuelState.DISSOLVED
    if status == DuelStatus.pending:
        if challenge_lapsed(duel, now, era):
            return DuelState.DISSOLVED
        return DuelState.CHALLENGED
    if status == DuelStatus.settled:
        return DuelState.LIVE_FORFEITED if forfeited else DuelState.LIVE
    casts = _cast(challenger_praxis) + _cast(opponent_praxis)
    if status == DuelStatus.active:
        if forfeited:
            return DuelState.AWAITING_HONEST_SIDE
        # Both cast but not yet settled (settling is a write): already live.
        if casts == 2:
            return DuelState.LIVE
        return DuelState.ONE_CAST if casts else DuelState.DRAFTING
    # resolved: live_at (set once, never cleared) marks a duel that went live; a
    # forfeit frozen from AWAITING_HONEST_SIDE has a winner too (Q4). Pending
    # duels dissolve at close, so a forfeit here was never a declined one.
    went_live = duel.live_at is not None or forfeited
    return DuelState.RESOLVED if went_live else DuelState.NO_CONTEST
