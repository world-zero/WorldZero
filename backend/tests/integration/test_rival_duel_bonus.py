"""Rival duel bonus (#3858): snapshot on accept, flat bonus to whoever duel_winner names."""

import pytest
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from faction_slugs import real_faction_slugs
from game_config import CURRENT_ERA
from models.character_block import CharacterBlock
from models.duel import Duel, DuelStatus
from models.era import Era
from models.praxis import Praxis, PraxisStatus
from models.relationship import Relationship, RelationshipType
from services.duel import get_duel_detail, respond_to_duel_challenge
from services.era import resolve_duels_at_era_close
from services.praxis_scoring import compute_contributions
from tests.integration.factories import (
    make_character,
    make_duel,
    make_solo_praxis,
    make_task,
    raise_to_duel_level,
)

BONUS = CURRENT_ERA.rival_duel_bonus
TIE_TAKER = next(
    s for s in real_faction_slugs(CURRENT_ERA) if CURRENT_ERA.factions[s].takes_duel_ties
)
NOT_TIE_TAKER = next(
    s
    for s in real_faction_slugs(CURRENT_ERA)
    if not CURRENT_ERA.factions[s].takes_duel_ties
)


@pytest.fixture(autouse=True)
def _factions(some_faction):
    """Faction rows the characters' FKs need."""


def _foe(a, b) -> Relationship:
    return Relationship(
        from_character_id=a.id, to_character_id=b.id, type=RelationshipType.foe
    )


async def _bonus_of(session: AsyncSession, duel: Duel, character) -> int:
    praxis_id = (
        duel.opponent_praxis_id
        if character.id == duel.opponent_character_id
        else duel.challenger_praxis_id
    )
    praxis = await session.get(Praxis, praxis_id)
    c = (await compute_contributions([praxis], character, CURRENT_ERA, session))[
        praxis_id
    ]
    multiplied = c.base_points * c.faction_multiplier * c.duel_multiplier
    assert c.total == pytest.approx(
        multiplied
        + c.metatask_points
        + c.points_from_votes
        + c.habit_bonus_points
        + c.rival_bonus_points
    )
    return c.rival_bonus_points


async def _accepted(session: AsyncSession, era: Era, label: str, *edges) -> Duel:
    challenger = await make_character(session, era, username=f"{label}ch")
    opponent = await make_character(session, era, username=f"{label}op")
    await raise_to_duel_level(session, opponent.id)
    for edge in edges:
        session.add(_foe(*{"ch": (challenger, opponent), "op": (opponent, challenger)}[edge]))
    task = await make_task(session, challenger)
    praxis = await make_solo_praxis(
        session, task, challenger, status=PraxisStatus.in_progress
    )
    duel = Duel(
        task_id=task.id,
        challenger_praxis_id=praxis.id,
        opponent_character_id=opponent.id,
        status=DuelStatus.pending,
    )
    session.add(duel)
    await session.commit()
    _, duel = await respond_to_duel_challenge(duel.id, opponent.id, True, session)
    return duel


@pytest.mark.asyncio
async def test_accept_snapshots_mutual_foes_only(db_session: AsyncSession, era: Era):
    rivals = await _accepted(db_session, era, "riv", "ch", "op")
    one_sided = await _accepted(db_session, era, "one", "ch")
    assert rivals.rival_bonus is True
    assert one_sided.rival_bonus is False
    detail = await get_duel_detail(rivals.id, None, db_session)
    assert detail.challenger.rival_bonus == detail.opponent.rival_bonus == BONUS
    assert (await get_duel_detail(one_sided.id, None, db_session)).opponent.rival_bonus == 0
    assert (await _accepted(db_session, era, "non")).rival_bonus is False


@pytest.mark.asyncio
async def test_edges_changed_after_accept_keep_the_bonus(
    db_session: AsyncSession, era: Era
):
    duel = await _accepted(db_session, era, "snap", "ch", "op")
    challenger_id = (await db_session.get(Praxis, duel.challenger_praxis_id)).created_by_id
    await db_session.execute(delete(Relationship))
    db_session.add(
        CharacterBlock(
            blocker_character_id=challenger_id,
            blocked_character_id=duel.opponent_character_id,
        )
    )
    await db_session.flush()
    refreshed = (
        await db_session.execute(select(Duel).where(Duel.id == duel.id))
    ).scalar_one()
    assert refreshed.rival_bonus is True


@pytest.mark.asyncio
async def test_winner_takes_bonus_after_multipliers(db_session: AsyncSession, era: Era):
    duel, challenger, opponent = await make_duel(
        db_session, era, label="win", challenger_votes=2, opponent_votes=5
    )
    duel.rival_bonus = True
    await db_session.flush()
    assert await _bonus_of(db_session, duel, opponent) == BONUS
    assert await _bonus_of(db_session, duel, challenger) == 0

    # Era close freezes the same winner: the bonus never fed the comparison.
    await resolve_duels_at_era_close(db_session, closing_era_id=era.id)
    assert duel.winner_character_id == opponent.id
    assert await _bonus_of(db_session, duel, opponent) == BONUS


@pytest.mark.asyncio
async def test_non_rival_duel_pays_no_bonus(db_session: AsyncSession, era: Era):
    duel, _, opponent = await make_duel(
        db_session, era, label="plain", challenger_votes=2, opponent_votes=5
    )
    assert await _bonus_of(db_session, duel, opponent) == 0


@pytest.mark.asyncio
async def test_true_tie_pays_nobody(db_session: AsyncSession, era: Era):
    duel, challenger, opponent = await make_duel(
        db_session, era, label="tie", challenger_votes=3, opponent_votes=3
    )
    duel.rival_bonus = True
    await db_session.flush()
    assert await _bonus_of(db_session, duel, challenger) == 0
    assert await _bonus_of(db_session, duel, opponent) == 0


@pytest.mark.asyncio
async def test_sole_tie_taker_takes_the_bonus(db_session: AsyncSession, era: Era):
    duel, challenger, opponent = await make_duel(
        db_session, era, label="snide", challenger_votes=3, opponent_votes=3,
        challenger_faction=NOT_TIE_TAKER, opponent_faction=TIE_TAKER,
    )
    duel.rival_bonus = True
    await db_session.flush()
    assert await _bonus_of(db_session, duel, opponent) == BONUS
    assert await _bonus_of(db_session, duel, challenger) == 0


@pytest.mark.asyncio
async def test_forfeit_hands_the_bonus_over(db_session: AsyncSession, era: Era):
    duel, challenger, opponent = await make_duel(
        db_session, era, label="forf", challenger_votes=5, opponent_votes=1,
        forfeiter="challenger",
    )
    duel.rival_bonus = True
    await db_session.flush()
    assert await _bonus_of(db_session, duel, opponent) == BONUS
    assert await _bonus_of(db_session, duel, challenger) == 0
