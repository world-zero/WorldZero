"""Feed duel card carries duel_state; a lapsed challenge reads dissolved."""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from eras.era_1 import ERA_1
from models.duel import DuelStatus
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
