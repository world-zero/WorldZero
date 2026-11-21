"""Duels time out on read (#3875).

Seam: ``settle_lapsed_duels`` and the public praxis visibility it unblocks.
"""
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from game_config import CURRENT_ERA
from models.character_stats import CharacterStats
from models.duel import DuelStatus
from models.era import Era
from models.faction import Faction
from models.praxis import Praxis, PraxisMember, PraxisStatus
from models.task import Task, TaskStatus
from services.duel import settle_lapsed_duels
from services.praxis_visibility import duel_side_hidden_condition
from tests.integration.factories import make_duel

DAYS = CURRENT_ERA.duel_challenge_lapse_days


async def _duel(db_session, era, label, *, status, age_days):
    duel, challenger, opponent = await make_duel(
        db_session, era, label=label, status=status
    )
    await db_session.execute(
        update(CharacterStats)
        .where(CharacterStats.character_id == opponent.id)
        .values(level=CURRENT_ERA.duel_level_required)
    )
    then = datetime.now(timezone.utc) - timedelta(days=age_days)
    duel.created_at = then
    if status == DuelStatus.pending:
        orphan_id, duel.opponent_praxis_id = duel.opponent_praxis_id, None
        await db_session.flush()
        await db_session.execute(
            delete(PraxisMember).where(PraxisMember.praxis_id == orphan_id)
        )
        await db_session.execute(delete(Praxis).where(Praxis.id == orphan_id))
    else:
        duel.accepted_at = then
    (await db_session.get(Praxis, duel.challenger_praxis_id)).status = (
        PraxisStatus.submitted
    )
    if duel.opponent_praxis_id is not None:
        (await db_session.get(Praxis, duel.opponent_praxis_id)).status = (
            PraxisStatus.in_progress
        )
    await db_session.commit()
    return duel, challenger, opponent


async def _hidden_from_public(db_session, praxis_id) -> bool:
    return bool(await db_session.scalar(
        select(duel_side_hidden_condition(None)).where(Praxis.id == praxis_id)
    ))


@pytest.mark.asyncio
async def test_unanswered_challenge_lapses_and_reveals_the_challenger(
    db_session: AsyncSession, era: Era, some_faction: Faction
):
    duel, *_ = await _duel(
        db_session, era, "lp1", status=DuelStatus.pending, age_days=DAYS + 1
    )
    assert await _hidden_from_public(db_session, duel.challenger_praxis_id)

    await settle_lapsed_duels(db_session, CURRENT_ERA)

    await db_session.refresh(duel)
    assert duel.status == DuelStatus.declined
    assert duel.declined_at is not None
    assert not await _hidden_from_public(db_session, duel.challenger_praxis_id)


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [DuelStatus.pending, DuelStatus.active])
async def test_nothing_lapses_before_the_deadline(
    db_session: AsyncSession, era: Era, some_faction: Faction, status
):
    duel, *_ = await _duel(
        db_session, era, f"nl{status.value}", status=status, age_days=DAYS - 1
    )

    await settle_lapsed_duels(db_session, CURRENT_ERA)

    await db_session.refresh(duel)
    assert duel.status == status
    assert duel.forfeited_by_character_id is None


@pytest.mark.asyncio
async def test_missing_cast_forfeits_the_opponent_and_settles(
    db_session: AsyncSession, era: Era, some_faction: Faction
):
    duel, challenger, opponent = await _duel(
        db_session, era, "lp2", status=DuelStatus.active,
        age_days=CURRENT_ERA.duel_cast_lapse_days + 1,
    )

    await settle_lapsed_duels(db_session, CURRENT_ERA)

    await db_session.refresh(duel)
    assert duel.forfeited_by_character_id == opponent.id
    assert duel.forfeited_at is not None
    assert duel.status == DuelStatus.settled
    assert not await _hidden_from_public(db_session, duel.challenger_praxis_id)


@pytest.mark.asyncio
async def test_a_cast_opponent_is_not_forfeited(
    db_session: AsyncSession, era: Era, some_faction: Faction
):
    duel, *_ = await _duel(
        db_session, era, "lp3", status=DuelStatus.active,
        age_days=CURRENT_ERA.duel_cast_lapse_days + 1,
    )
    (await db_session.get(Praxis, duel.opponent_praxis_id)).status = (
        PraxisStatus.submitted
    )
    await db_session.commit()

    await settle_lapsed_duels(db_session, CURRENT_ERA)

    await db_session.refresh(duel)
    assert duel.forfeited_by_character_id is None


@pytest.mark.asyncio
async def test_challenge_the_opponent_cannot_accept_declines_at_once(
    db_session: AsyncSession, era: Era, some_faction: Faction
):
    retired, *_ = await _duel(
        db_session, era, "lp4", status=DuelStatus.pending, age_days=0
    )
    low, _, low_opponent = await _duel(
        db_session, era, "lp5", status=DuelStatus.pending, age_days=0
    )
    fine, *_ = await _duel(
        db_session, era, "lp6", status=DuelStatus.pending, age_days=0
    )
    (await db_session.get(Task, retired.task_id)).status = TaskStatus.deleted
    await db_session.execute(
        update(CharacterStats)
        .where(CharacterStats.character_id == low_opponent.id)
        .values(level=CURRENT_ERA.duel_level_required - 1)
    )
    await db_session.commit()

    await settle_lapsed_duels(db_session, CURRENT_ERA)

    for duel in (retired, low, fine):
        await db_session.refresh(duel)
    assert retired.status == DuelStatus.declined
    assert low.status == DuelStatus.declined
    assert fine.status == DuelStatus.pending
