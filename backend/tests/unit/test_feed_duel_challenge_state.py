"""Feed duel card carries duel_state; a lapsed challenge reads dissolved."""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from eras.era_1 import ERA_1
from models.duel import DuelStatus
from models.praxis import PraxisStatus
from services.activity_feed import _duel_challenge_item
from services.duel_state import DuelState

DAY = timedelta(days=1)


def _row(age_days, status=DuelStatus.pending):
    return SimpleNamespace(
        id=1, created_at=datetime.now(timezone.utc) - age_days * DAY, status=status,
        forfeited_by_character_id=None, live_at=None, challenger_praxis_id=2,
        task_id=3, challenger_character_id=4, task_title="t", task_point_value=10,
        task_faction_slug="snide", actor_display_name="a", actor_faction_slug="snide",
        actor_avatar_url=None,
        challenger_praxis_status=PraxisStatus.in_progress,
        opponent_praxis_status=None,
    )


@pytest.mark.parametrize(
    "age,status,state",
    [
        (1, DuelStatus.pending, DuelState.CHALLENGED),
        (ERA_1.duel_challenge_lapse_days + 1, DuelStatus.pending, DuelState.DISSOLVED),
        (1, DuelStatus.declined, DuelState.DISSOLVED),
    ],
)
def test_duel_state_on_feed_payload(age, status, state):
    item = _duel_challenge_item(_row(age, status), ERA_1)
    assert item.payload.duel_state == state


@pytest.mark.parametrize(
    "challenger,opponent,state",
    [
        (PraxisStatus.in_progress, None, DuelState.DRAFTING),
        (PraxisStatus.submitted, PraxisStatus.in_progress, DuelState.ONE_CAST),
        (PraxisStatus.submitted, PraxisStatus.submitted, DuelState.LIVE),
    ],
)
def test_active_duel_state_counts_casts(challenger, opponent, state):
    row = _row(1, DuelStatus.active)
    row.challenger_praxis_status, row.opponent_praxis_status = challenger, opponent
    assert _duel_challenge_item(row, ERA_1).payload.duel_state == state
