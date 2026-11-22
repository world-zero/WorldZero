"""Duel rules read DuelState (#4200, rulings in #4191's decision log).

Seam: the duel and praxis routes in; duel rows, badges and era close out.
"""
from datetime import datetime, timezone

import pytest
from httpx import AsyncClient
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from errors import ErrorCode, detail_code
from models.account import Account
from models.character import Character
from models.duel import Duel, DuelStatus
from models.era import Era
from models.faction import Faction
from models.praxis import Praxis, PraxisMember, PraxisStatus
from services.auth import create_jwt
from services.duel_outcome import duel_winner
from services.duel_state import DuelState
from services.praxis_duel import duel_state_of
from tests.integration.factories import make_duel, raise_to_duel_level
from tests.integration.test_duel_era_resolution import (
    NOT_TIE_TAKER,
    TIE_TAKER,
    _close_the_era,
)
from tests.integration.test_duelist_badge import _badge_keys


def _headers(character: Character) -> dict:
    return {"Authorization": f"Bearer {create_jwt(character.account_id)}"}


async def _duel(db_session, era, label, status, *, cast=(), forfeiter=None, **kwargs):
    """A duel whose sides are submitted only if named in ``cast``
    (``"challenger"`` / ``"opponent"``), committed."""
    duel, challenger, opponent = await make_duel(
        db_session, era, label=label, status=DuelStatus.active,
        forfeiter=forfeiter, **kwargs,
    )
    sides = {
        "challenger": duel.challenger_praxis_id,
        "opponent": duel.opponent_praxis_id,
    }
    for side, praxis_id in sides.items():
        (await db_session.get(Praxis, praxis_id)).status = (
            PraxisStatus.submitted if side in cast else PraxisStatus.in_progress
        )
    duel.accepted_at = duel.created_at
    duel.status = status
    if status == DuelStatus.pending:
        duel.accepted_at = None
        duel.opponent_praxis_id = None
        await db_session.execute(
            delete(PraxisMember).where(PraxisMember.praxis_id == sides["opponent"])
        )
        await db_session.delete(await db_session.get(Praxis, sides["opponent"]))
        await raise_to_duel_level(db_session, opponent.id)
    await db_session.commit()
    return duel, challenger, opponent


# Q1


@pytest.mark.asyncio
async def test_no_early_submit_while_challenged(
    client: AsyncClient, db_session: AsyncSession, era: Era, some_faction: Faction
):
    duel, challenger, _ = await _duel(db_session, era, "q1", DuelStatus.pending)
    resp = await client.post(
        f"/praxes/{duel.challenger_praxis_id}/submit", headers=_headers(challenger)
    )
    assert resp.status_code == 409, resp.text
    assert detail_code(resp.json()["detail"]) == ErrorCode.duel_awaiting_accept.value
    praxis = await db_session.get(Praxis, duel.challenger_praxis_id)
    await db_session.refresh(praxis)
    assert praxis.status == PraxisStatus.in_progress


@pytest.mark.asyncio
async def test_submit_allowed_once_accepted(
    client: AsyncClient, db_session: AsyncSession, era: Era, some_faction: Faction
):
    duel, challenger, _ = await _duel(db_session, era, "q1ok", DuelStatus.active)
    resp = await client.post(
        f"/praxes/{duel.challenger_praxis_id}/submit", headers=_headers(challenger)
    )
    assert resp.status_code == 200, resp.text


# Q5


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "status,cast",
    [(DuelStatus.active, ()), (DuelStatus.settled, ("challenger", "opponent"))],
    ids=["awaiting_honest_side", "live_forfeited"],
)
async def test_a_forfeit_cannot_be_dissolved(
    client: AsyncClient, db_session: AsyncSession, era: Era, some_faction: Faction,
    status: DuelStatus, cast: tuple,
):
    duel, challenger, _ = await _duel(
        db_session, era, f"q5{status.value}", status, cast=cast, forfeiter="opponent"
    )
    resp = await client.post(f"/duels/{duel.id}/cancel", headers=_headers(challenger))
    assert resp.status_code == 400, resp.text
    await db_session.refresh(duel)
    assert duel.status == status
    assert duel.forfeited_by_character_id is not None


@pytest.mark.asyncio
async def test_drafting_duel_still_dissolves(
    client: AsyncClient, db_session: AsyncSession, era: Era, some_faction: Faction
):
    duel, challenger, _ = await _duel(db_session, era, "q5ok", DuelStatus.active)
    resp = await client.post(f"/duels/{duel.id}/cancel", headers=_headers(challenger))
    assert resp.status_code == 200, resp.text


# Q4, Q8, no-contest finals


@pytest.mark.asyncio
async def test_era_close_gives_awaiting_honest_side_the_win(
    db_session: AsyncSession, era: Era, account: Account, some_faction: Faction
):
    duel, challenger, _ = await _duel(
        db_session, era, "q4", DuelStatus.active, forfeiter="opponent"
    )
    await _close_the_era(db_session, account)
    await db_session.refresh(duel)
    assert duel.status == DuelStatus.resolved
    assert duel.winner_character_id == challenger.id
    assert (await duel_state_of(duel, db_session)) is DuelState.RESOLVED


@pytest.mark.asyncio
@pytest.mark.parametrize("cast", [(), ("challenger",)], ids=["drafting", "one_cast"])
async def test_no_contest_writes_null_finals(
    db_session: AsyncSession, era: Era, account: Account, some_faction: Faction,
    cast: tuple,
):
    duel, _, _ = await _duel(
        db_session, era, f"nc{len(cast)}", DuelStatus.active, cast=cast
    )
    await _close_the_era(db_session, account)
    await db_session.refresh(duel)
    assert duel.status == DuelStatus.resolved
    assert duel.winner_character_id is None
    assert duel.challenger_final_points is None
    assert duel.opponent_final_points is None


@pytest.mark.asyncio
async def test_era_close_dissolves_a_challenged_duel(
    db_session: AsyncSession, era: Era, account: Account, some_faction: Faction
):
    duel, _, _ = await _duel(db_session, era, "q8", DuelStatus.pending)
    await _close_the_era(db_session, account)
    await db_session.refresh(duel)
    assert duel.status == DuelStatus.declined
    assert duel.declined_at is not None


# Q10


def test_no_votes_no_winner_even_with_a_tie_perk():
    kwargs = dict(
        challenger_character_id=1, opponent_character_id=2,
        challenger_moderation=None, opponent_moderation=None, tie_break_winner_id=2,
    )
    assert duel_winner(challenger_points=0, opponent_points=0, **kwargs) is None
    assert duel_winner(challenger_points=3, opponent_points=3, **kwargs) == 2
    # A forfeit is a win at 0 votes.
    assert duel_winner(
        challenger_points=0, opponent_points=0, forfeited_by_character_id=1, **kwargs
    ) == 2


@pytest.mark.asyncio
@pytest.mark.skipif(TIE_TAKER is None, reason="the era has no tie perk")
async def test_era_close_zero_votes_tie_perk_gives_no_win(
    db_session: AsyncSession, era: Era, account: Account, some_faction: Faction
):
    duel, _, _ = await _duel(
        db_session, era, "q10", DuelStatus.settled, cast=("challenger", "opponent"),
        challenger_faction=TIE_TAKER, opponent_faction=NOT_TIE_TAKER,
    )
    await _close_the_era(db_session, account)
    await db_session.refresh(duel)
    assert duel.status == DuelStatus.resolved
    assert duel.winner_character_id is None


@pytest.mark.asyncio
@pytest.mark.skipif(TIE_TAKER is None, reason="the era has no tie perk")
async def test_badge_zero_votes_tie_perk_gives_no_win(
    db_session: AsyncSession, era: Era, some_faction: Faction
):
    _, challenger, _ = await _duel(
        db_session, era, "q10b", DuelStatus.settled, cast=("challenger", "opponent"),
        challenger_faction=TIE_TAKER, opponent_faction=NOT_TIE_TAKER,
    )
    assert await _badge_keys(db_session, challenger) == []


@pytest.mark.asyncio
async def test_badge_ignores_a_duel_nobody_cast(
    db_session: AsyncSession, era: Era, some_faction: Faction
):
    _, challenger, _ = await _duel(
        db_session, era, "q10c", DuelStatus.active, challenger_votes=5, opponent_votes=1
    )
    assert await _badge_keys(db_session, challenger) == []


# Q11


@pytest.mark.asyncio
async def test_unsubmit_forfeit_stamps_both_columns(
    client: AsyncClient, db_session: AsyncSession, era: Era, some_faction: Faction
):
    duel, challenger, _ = await _duel(
        db_session, era, "q11", DuelStatus.settled, cast=("challenger", "opponent")
    )
    resp = await client.post(
        f"/praxes/{duel.challenger_praxis_id}/unsubmit", headers=_headers(challenger)
    )
    assert resp.status_code == 200, resp.text
    await db_session.refresh(duel)
    assert duel.forfeited_by_character_id == challenger.id
    assert duel.forfeited_at is not None


# Item 7


@pytest.mark.asyncio
async def test_a_decided_duel_cannot_be_reopened(
    client: AsyncClient, db_session: AsyncSession, era: Era, some_faction: Faction
):
    duel, challenger, opponent = await _duel(
        db_session, era, "reopen", DuelStatus.settled,
        cast=("challenger", "opponent"), forfeiter="challenger",
    )
    resp = await client.post(
        f"/praxes/{duel.opponent_praxis_id}/unsubmit", headers=_headers(opponent)
    )
    assert resp.status_code == 409, resp.text
    assert detail_code(resp.json()["detail"]) == ErrorCode.duel_side_locked.value
    praxis = await db_session.get(Praxis, duel.opponent_praxis_id)
    await db_session.refresh(praxis)
    assert praxis.status == PraxisStatus.submitted


async def _no_contest_side(db_session, era, label):
    duel, challenger, opponent = await _duel(db_session, era, label, DuelStatus.active)
    duel.status = DuelStatus.resolved
    duel.resolved_at = datetime.now(timezone.utc)
    duel.resolved_era_id = era.id
    await db_session.commit()
    return duel, challenger, opponent


@pytest.mark.asyncio
async def test_no_rechallenge_after_a_no_contest(
    client: AsyncClient, db_session: AsyncSession, era: Era, some_faction: Faction
):
    duel, challenger, _ = await _no_contest_side(db_session, era, "rechal")
    other = await make_other(db_session, era)
    resp = await client.post(
        "/duels/challenge",
        json={
            "challenger_praxis_id": duel.challenger_praxis_id,
            "opponent_character_id": other.id,
        },
        headers=_headers(challenger),
    )
    assert resp.status_code == 409, resp.text
    assert detail_code(resp.json()["detail"]) == ErrorCode.duel_already_exists.value


async def make_other(db_session, era) -> Character:
    from tests.integration.factories import make_character

    other = await make_character(db_session, era, username="rechalother")
    await raise_to_duel_level(db_session, other.id)
    await db_session.commit()
    return other


@pytest.mark.asyncio
async def test_nudge_lookup_ignores_a_declined_row(
    db_session: AsyncSession, era: Era, some_faction: Faction
):
    from services.nudge import _authorize_duel

    duel, _, opponent = await _duel(db_session, era, "nudge", DuelStatus.active)
    db_session.add(Duel(
        task_id=duel.task_id,
        challenger_praxis_id=duel.challenger_praxis_id,
        opponent_character_id=opponent.id,
        status=DuelStatus.declined,
        declined_at=datetime.now(timezone.utc),
    ))
    await db_session.commit()
    praxis = await db_session.get(Praxis, duel.challenger_praxis_id)
    await _authorize_duel(praxis, opponent.id, db_session)


@pytest.mark.asyncio
async def test_a_side_of_a_finished_duel_refuses_drop_cleanly(
    client: AsyncClient, db_session: AsyncSession, era: Era, some_faction: Faction
):
    duel, challenger, _ = await _no_contest_side(db_session, era, "drop")
    resp = await client.delete(
        f"/praxes/{duel.challenger_praxis_id}", headers=_headers(challenger)
    )
    assert resp.status_code == 409, resp.text
    assert detail_code(resp.json()["detail"]) == ErrorCode.duel_side_locked.value


@pytest.mark.asyncio
async def test_decline_rescores_like_withdraw(
    client: AsyncClient, db_session: AsyncSession, era: Era, some_faction: Faction,
    monkeypatch,
):
    import services.duel as duel_service

    duel, challenger, opponent = await _duel(
        db_session, era, "decl", DuelStatus.pending
    )
    rescored: list[int] = []
    real = duel_service.recalculate_character_stats

    async def spy(character_id, *args, **kwargs):
        rescored.append(character_id)
        return await real(character_id, *args, **kwargs)

    monkeypatch.setattr(duel_service, "recalculate_character_stats", spy)
    resp = await client.post(
        f"/duels/{duel.id}/respond", json={"accept": False}, headers=_headers(opponent)
    )
    assert resp.status_code == 200, resp.text
    assert sorted(rescored) == sorted([challenger.id, opponent.id])
