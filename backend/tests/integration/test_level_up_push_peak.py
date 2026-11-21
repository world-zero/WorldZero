"""The level-up push fires only past the era's peak level (#3788).

Seam: ``recalculate_character_stats`` -> ``push.notify_level_up``; the level is
driven by patching ``compute_level`` so no praxis scoring is needed.
"""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from models.account import Account
from models.character import Character
from models.era import Era
from models.push_subscription import PushSubscription
from services import character_stats
from services.era import apply_era_reset
from tests.integration.test_push import PRIVATE, PUBLIC, _queued


@pytest.fixture
def opted_in(db_session: AsyncSession, account: Account, monkeypatch):
    monkeypatch.setattr(settings, "VAPID_PUBLIC_KEY", PUBLIC)
    monkeypatch.setattr(settings, "VAPID_PRIVATE_KEY", PRIVATE)
    monkeypatch.setattr(settings, "VAPID_CONTACT", "mailto:hi@worldzero.org")
    account.notification_prefs = {"level_up": {"by_push": True}}
    db_session.add(
        PushSubscription(
            account_id=account.id,
            endpoint="https://fcm.googleapis.com/fcm/send/abc",
            p256dh="k",
            auth="a",
        )
    )


@pytest.fixture
def set_level(monkeypatch):
    def _set(level: int) -> None:
        monkeypatch.setattr(character_stats, "compute_level", lambda *_: level)

    return _set


async def _recalc(db_session, character, era_row) -> int:
    before = len(_queued(db_session))
    await character_stats.recalculate_character_stats(
        character.id, db_session, era_row=era_row
    )
    return len(_queued(db_session)) - before


@pytest.mark.asyncio
async def test_a_new_level_pushes_once(db_session, character, era, opted_in, set_level):
    set_level(1)
    assert await _recalc(db_session, character, era) == 1
    assert await _recalc(db_session, character, era) == 0


@pytest.mark.asyncio
async def test_a_dip_and_recovery_pushes_nothing(
    db_session, character, era, opted_in, set_level
):
    set_level(2)
    assert await _recalc(db_session, character, era) == 1
    set_level(1)
    assert await _recalc(db_session, character, era) == 0
    set_level(2)
    assert await _recalc(db_session, character, era) == 0


@pytest.mark.asyncio
async def test_passing_the_era_peak_pushes_again(
    db_session, character, era, opted_in, set_level
):
    set_level(1)
    await _recalc(db_session, character, era)
    set_level(0)
    await _recalc(db_session, character, era)
    set_level(2)
    assert await _recalc(db_session, character, era) == 1


@pytest.mark.asyncio
async def test_level_one_pushes_in_a_new_era_despite_a_higher_character_peak(
    db_session: AsyncSession,
    account: Account,
    character: Character,
    era: Era,
    opted_in,
    set_level,
):
    set_level(3)
    await _recalc(db_session, character, era)
    assert character.peak_level >= 3

    new_era = Era(name="Era 2", config_key=era.config_key, started_by_id=account.id)
    db_session.add(new_era)
    await db_session.flush()
    await apply_era_reset([character], new_era, db_session)
    set_level(1)
    assert await _recalc(db_session, character, new_era) == 1
