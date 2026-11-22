"""duel_state / collab_state: each column combination maps to one state (#4199)."""
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from eras.era_1 import ERA_1
from models.duel import DuelStatus
from models.praxis import PraxisStatus, PraxisType
from services.collab_state import CollabState, MemberState, collab_state, member_state
from services.duel_state import DuelState, duel_state

NOW = datetime(2026, 1, 20, tzinfo=timezone.utc)
FRESH = NOW - timedelta(days=1)
STALE = NOW - timedelta(days=ERA_1.duel_challenge_lapse_days + 1)
CAST = SimpleNamespace(status=PraxisStatus.submitted)
DRAFT = SimpleNamespace(status=PraxisStatus.in_progress)
P, A, S, D, R = (
    DuelStatus.pending, DuelStatus.active, DuelStatus.settled,
    DuelStatus.declined, DuelStatus.resolved,
)


def _duel(status, created_at=FRESH, forfeit=None):
    return SimpleNamespace(
        status=status, created_at=created_at, forfeited_by_character_id=forfeit
    )


DUEL_CASES = [
    (P, FRESH, None, DRAFT, None, DuelState.CHALLENGED),
    (P, STALE, None, DRAFT, None, DuelState.DISSOLVED),
    (D, FRESH, None, DRAFT, None, DuelState.DISSOLVED),
    (A, FRESH, None, DRAFT, DRAFT, DuelState.DRAFTING),
    (A, FRESH, None, CAST, DRAFT, DuelState.ONE_CAST),
    (A, FRESH, None, DRAFT, CAST, DuelState.ONE_CAST),
    (A, FRESH, 7, DRAFT, DRAFT, DuelState.AWAITING_HONEST_SIDE),
    (A, FRESH, 7, CAST, DRAFT, DuelState.AWAITING_HONEST_SIDE),
    (S, FRESH, None, CAST, CAST, DuelState.LIVE),
    (S, FRESH, 7, CAST, CAST, DuelState.LIVE_FORFEITED),
    (R, FRESH, None, CAST, CAST, DuelState.RESOLVED),
    (R, FRESH, 7, DRAFT, CAST, DuelState.RESOLVED),
    (R, FRESH, None, DRAFT, DRAFT, DuelState.NO_CONTEST),
    (R, FRESH, None, CAST, DRAFT, DuelState.NO_CONTEST),
]


@pytest.mark.parametrize("status,created,forfeit,mine,theirs,expected", DUEL_CASES)
def test_duel_state(status, created, forfeit, mine, theirs, expected):
    duel = _duel(status, created, forfeit)
    assert duel_state(duel, mine, theirs, NOW, ERA_1) is expected


def test_pending_never_lapses_without_a_window():
    era = replace(ERA_1, duel_challenge_lapse_days=None)
    assert duel_state(_duel(P, STALE), DRAFT, None, NOW, era) is DuelState.CHALLENGED


def test_active_with_both_cast_is_unreachable():
    with pytest.raises(ValueError):
        duel_state(_duel(A), CAST, CAST, NOW, ERA_1)


def _collab(status, member_count, kind=PraxisType.collab):
    return SimpleNamespace(type=kind, status=status, members=[object()] * member_count)


IP, PE, SU = PraxisStatus.in_progress, PraxisStatus.pending, PraxisStatus.submitted
COLLAB_CASES = [
    (IP, 1, CollabState.ALONE),
    (IP, 2, CollabState.DRAFTING),
    (IP, 3, CollabState.DRAFTING),
    (PE, 2, CollabState.PROPOSED),
    (SU, 1, CollabState.LIVE),
    (SU, 2, CollabState.LIVE),
]


@pytest.mark.parametrize("status,members,expected", COLLAB_CASES)
def test_collab_state(status, members, expected):
    assert collab_state(_collab(status, members)) is expected


@pytest.mark.parametrize("status", [IP, PE, SU])
def test_empty_collab_raises(status):
    # TODO(#4201): EMPTY must become unreachable; then this test goes.
    with pytest.raises(ValueError):
        collab_state(_collab(status, 0))


def test_collab_state_refuses_solo():
    with pytest.raises(ValueError):
        collab_state(_collab(IP, 1, PraxisType.solo))


def test_member_state():
    assert member_state(SimpleNamespace(has_approved=True)) is MemberState.APPROVED
    assert member_state(SimpleNamespace(has_approved=False)) is MemberState.EDITING
