"""Duels time out on read (#3875).

Seam: ``settle_lapsed_duels`` and the public praxis visibility it unblocks.
"""
from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest
from httpx import AsyncClient
from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from eras.era_1 import ERA_1
from errors import ErrorCode, detail_code
from game_config import CURRENT_ERA
from models.character_stats import CharacterStats
from models.duel import DuelStatus
from models.era import Era
from models.faction import Faction
from models.praxis import Praxis, PraxisMember, PraxisStatus
from models.task import Task, TaskStatus
from services import collab_consensus
from services import praxis as praxis_service
from services.activity_feed import get_activity_feed, pending_requests_counts
from services.auth import create_jwt
from services.duel import (
    get_duel_detail,
    respond_to_duel_challenge,
    settle_lapsed_duels,
)
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
    challenger_praxis = await db_session.get(Praxis, duel.challenger_praxis_id)
    challenger_praxis.status = PraxisStatus.submitted
    challenger_praxis.submitted_at = then
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
@pytest.mark.parametrize("age_days,listed", [(DAYS + 1, False), (DAYS - 1, True)])
async def test_a_lapsed_unswept_challenge_leaves_requests_and_the_badge(
    db_session: AsyncSession, era: Era, some_faction: Faction, age_days, listed
):
    duel, _, opponent = await _duel(
        db_session, era, "lq", status=DuelStatus.pending, age_days=age_days
    )

    feed = await get_activity_feed(opponent.id, db_session, feed_filter="requests")
    badge = await pending_requests_counts([opponent.id], db_session)

    assert (duel.id in [i.payload.duel_id for i in feed.items]) is listed
    assert badge[opponent.id] == int(listed)


@pytest.mark.asyncio
async def test_missing_cast_forfeits_the_opponent_and_settles(
    db_session: AsyncSession, era: Era, some_faction: Faction
):
    duel, challenger, opponent = await _duel(
        db_session, era, "lp2", status=DuelStatus.active,
        age_days=CURRENT_ERA.duel_cast_lapse_days + 1,
    )  # the challenger cast first, at acceptance

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
@pytest.mark.parametrize("window", [CURRENT_ERA.duel_challenge_lapse_days, None])
async def test_challenge_the_opponent_cannot_accept_declines_at_once(
    db_session: AsyncSession, era: Era, some_faction: Faction, window
):
    era_config = replace(CURRENT_ERA, duel_challenge_lapse_days=window)
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

    await settle_lapsed_duels(db_session, era_config)

    for duel in (retired, low, fine):
        await db_session.refresh(duel)
    assert retired.status == DuelStatus.declined
    assert low.status == DuelStatus.declined
    assert fine.status == DuelStatus.pending


def _bearer(character) -> dict:
    return {"Authorization": f"Bearer {create_jwt(character.account_id)}"}


@pytest.mark.asyncio
async def test_a_lapsed_challenge_cannot_be_accepted(
    client: AsyncClient, db_session: AsyncSession, era: Era, some_faction: Faction
):
    duel, _, opponent = await _duel(
        db_session, era, "lp7", status=DuelStatus.pending, age_days=DAYS + 1
    )

    resp = await client.post(
        f"/duels/{duel.id}/respond", json={"accept": True}, headers=_bearer(opponent)
    )

    assert resp.status_code == 400, resp.text
    assert (
        detail_code(resp.json()["detail"])
        == ErrorCode.duel_challenge_already_resolved.value
    )


@pytest.mark.asyncio
async def test_with_no_challenge_window_an_old_challenge_still_accepts(
    db_session: AsyncSession, era: Era, some_faction: Faction
):
    duel, _, opponent = await _duel(
        db_session, era, "lp7n", status=DuelStatus.pending, age_days=400
    )
    never = replace(CURRENT_ERA, duel_challenge_lapse_days=None)

    _, accepted = await respond_to_duel_challenge(
        duel.id, opponent.id, True, db_session, never
    )

    assert accepted.status == DuelStatus.active


@pytest.mark.asyncio
async def test_a_cast_past_the_window_is_still_the_opponents_forfeit(
    client: AsyncClient, db_session: AsyncSession, era: Era, some_faction: Faction
):
    duel, _, opponent = await _duel(
        db_session, era, "lp8", status=DuelStatus.active,
        age_days=CURRENT_ERA.duel_cast_lapse_days + 1,
    )

    resp = await client.post(
        f"/praxes/{duel.opponent_praxis_id}/submit", headers=_bearer(opponent)
    )

    assert resp.status_code == 200, resp.text
    await db_session.refresh(duel)
    assert duel.forfeited_by_character_id == opponent.id


@pytest.mark.asyncio
async def test_a_sticky_forfeit_survives_the_lapse_sweep(
    db_session: AsyncSession, era: Era, some_faction: Faction
):
    duel, challenger, _ = await _duel(
        db_session, era, "lp9", status=DuelStatus.active,
        age_days=CURRENT_ERA.duel_cast_lapse_days + 1,
    )
    stamped = datetime.now(timezone.utc) - timedelta(days=1)
    duel.forfeited_by_character_id = challenger.id
    duel.forfeited_at = stamped
    await db_session.commit()

    await settle_lapsed_duels(db_session, CURRENT_ERA)
    await settle_lapsed_duels(db_session, CURRENT_ERA)

    await db_session.refresh(duel)
    assert duel.forfeited_by_character_id == challenger.id
    assert duel.forfeited_at == stamped


@pytest.mark.asyncio
async def test_the_duel_sweep_runs_after_the_collab_seal(
    db_session: AsyncSession, era: Era, some_faction: Faction, monkeypatch
):
    """Lock order (#3655): 0x5A1B (seal) before any Duel FOR UPDATE."""
    duel, *_ = await _duel(
        db_session, era, "lp10", status=DuelStatus.pending, age_days=0
    )
    calls: list[str] = []
    real_seal = collab_consensus.settle_if_window_lapsed
    real_sweep = praxis_service._settle_lapsed_duels

    async def seal(*args, **kwargs):
        calls.append("seal")
        return await real_seal(*args, **kwargs)

    async def sweep(*args, **kwargs):
        calls.append("sweep")
        return await real_sweep(*args, **kwargs)

    monkeypatch.setattr(collab_consensus, "settle_if_window_lapsed", seal)
    monkeypatch.setattr(praxis_service, "_settle_lapsed_duels", sweep)

    await praxis_service.get_praxis_settling_consensus(
        duel.challenger_praxis_id, db_session, CURRENT_ERA
    )
    assert calls == ["seal", "sweep"]
    calls.clear()
    await praxis_service.list_praxes(db_session, era=CURRENT_ERA)
    assert calls and calls[-1] == "sweep" and "sweep" not in calls[:-1]


@pytest.mark.asyncio
async def test_a_sweep_with_nothing_lapsed_takes_no_row_lock(
    db_session: AsyncSession, era: Era, some_faction: Faction
):
    from sqlalchemy import event

    await _duel(db_session, era, "lp11", status=DuelStatus.pending, age_days=0)
    await _duel(db_session, era, "lp12", status=DuelStatus.active, age_days=0)
    statements: list[str] = []
    sync_engine = db_session.bind.sync_engine

    def spy(conn, cursor, statement, *args):
        statements.append(statement)

    event.listen(sync_engine, "before_cursor_execute", spy)
    try:
        changed = await settle_lapsed_duels(db_session, CURRENT_ERA)
    finally:
        event.remove(sync_engine, "before_cursor_execute", spy)

    assert changed is False
    assert not [s for s in statements if "FOR UPDATE" in s]


@pytest.mark.asyncio
async def test_a_candidate_cleared_under_lock_still_reports_the_reread(
    db_session: AsyncSession, era: Era, some_faction: Faction, monkeypatch
):
    """The locked re-read resets lazy='raise' relations, so the caller must reload."""
    from services import duel as duel_service
    from services.praxis_out import build_praxis_out

    duel, *_ = await _duel(
        db_session, era, "lp13", status=DuelStatus.pending, age_days=0
    )
    answers = iter([True])

    async def cleared_on_recheck(*args):
        return next(answers, False)

    monkeypatch.setattr(duel_service, "_challenge_unanswerable", cleared_on_recheck)

    praxis = await praxis_service.get_praxis_settling_consensus(
        duel.challenger_praxis_id, db_session
    )
    await db_session.refresh(duel)
    assert duel.status == DuelStatus.pending
    await build_praxis_out(praxis, db_session, viewer=None)


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [DuelStatus.pending, DuelStatus.active])
async def test_a_none_window_never_lapses(
    db_session: AsyncSession, era: Era, some_faction: Faction, status
):
    duel, *_ = await _duel(
        db_session, era, f"nv{status.value}", status=status, age_days=400
    )
    never = replace(
        CURRENT_ERA, duel_challenge_lapse_days=None, duel_cast_lapse_days=None
    )

    await settle_lapsed_duels(db_session, never)

    await db_session.refresh(duel)
    assert duel.status == status
    assert duel.forfeited_by_character_id is None


def test_era_1_duels_lapse_in_seven_days():
    assert CURRENT_ERA.duel_challenge_lapse_days == ERA_1.duel_challenge_lapse_days
    assert ERA_1.duel_challenge_lapse_days is not None
    assert ERA_1.duel_cast_lapse_days is not None


@pytest.mark.asyncio
async def test_an_accepted_duel_nobody_cast_never_lapses(
    db_session: AsyncSession, era: Era, some_faction: Faction
):
    duel, *_ = await _duel(
        db_session, era, "cc1", status=DuelStatus.active,
        age_days=CURRENT_ERA.duel_cast_lapse_days * 10,
    )
    (await db_session.get(Praxis, duel.challenger_praxis_id)).status = (
        PraxisStatus.in_progress
    )
    await db_session.commit()

    await settle_lapsed_duels(db_session, CURRENT_ERA)

    await db_session.refresh(duel)
    assert duel.status == DuelStatus.active
    assert duel.forfeited_by_character_id is None


@pytest.mark.asyncio
async def test_the_clock_starts_at_the_first_cast_not_acceptance(
    db_session: AsyncSession, era: Era, some_faction: Faction
):
    duel, *_ = await _duel(
        db_session, era, "cc2", status=DuelStatus.active,
        age_days=CURRENT_ERA.duel_cast_lapse_days * 10,
    )
    (await db_session.get(Praxis, duel.challenger_praxis_id)).submitted_at = (
        datetime.now(timezone.utc) - timedelta(days=1)
    )
    await db_session.commit()

    await settle_lapsed_duels(db_session, CURRENT_ERA)

    await db_session.refresh(duel)
    assert duel.forfeited_by_character_id is None


@pytest.mark.asyncio
async def test_opponent_casting_first_makes_the_challenger_forfeit(
    db_session: AsyncSession, era: Era, some_faction: Faction
):
    duel, challenger, opponent = await _duel(
        db_session, era, "cc3", status=DuelStatus.active,
        age_days=CURRENT_ERA.duel_cast_lapse_days + 1,
    )
    (await db_session.get(Praxis, duel.challenger_praxis_id)).status = (
        PraxisStatus.in_progress
    )
    cast = await db_session.get(Praxis, duel.opponent_praxis_id)
    cast.status = PraxisStatus.submitted
    cast.submitted_at = datetime.now(timezone.utc) - timedelta(
        days=CURRENT_ERA.duel_cast_lapse_days + 1
    )
    await db_session.commit()

    await settle_lapsed_duels(db_session, CURRENT_ERA)

    await db_session.refresh(duel)
    assert duel.forfeited_by_character_id == challenger.id
    assert duel.status == DuelStatus.settled


@pytest.mark.asyncio
async def test_a_challenger_cast_while_pending_starts_its_clock_at_acceptance(
    db_session: AsyncSession, era: Era, some_faction: Faction
):
    duel, _, opponent = await _duel(
        db_session, era, "cc4", status=DuelStatus.active,
        age_days=CURRENT_ERA.duel_cast_lapse_days + 1,
    )
    (await db_session.get(Praxis, duel.challenger_praxis_id)).submitted_at = (
        datetime.now(timezone.utc) - timedelta(days=500)
    )
    await db_session.commit()

    await settle_lapsed_duels(db_session, CURRENT_ERA)

    await db_session.refresh(duel)
    assert duel.forfeited_by_character_id == opponent.id


@pytest.mark.asyncio
async def test_detail_reports_the_clock_only_while_one_side_has_cast(
    db_session: AsyncSession, era: Era, some_faction: Faction
):
    duel, *_ = await _duel(
        db_session, era, "cc5", status=DuelStatus.active, age_days=1
    )
    detail = await get_duel_detail(duel.id, None, db_session, CURRENT_ERA)
    assert detail.cast_clock_started_at is not None

    (await db_session.get(Praxis, duel.challenger_praxis_id)).status = (
        PraxisStatus.in_progress
    )
    await db_session.commit()
    detail = await get_duel_detail(duel.id, None, db_session, CURRENT_ERA)
    assert detail.cast_clock_started_at is None
