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
        if casts == 2:
            raise ValueError("active duel with both sides cast should be settled")
        return DuelState.ONE_CAST if casts else DuelState.DRAFTING
    # resolved: a forfeit still has a winner (Q4); otherwise both must have cast.
    # ponytail: no column records "resolved from active", so a side reopened after
    # the close reads NO_CONTEST; store the state if that ever matters.
    return DuelState.RESOLVED if forfeited or casts == 2 else DuelState.NO_CONTEST
