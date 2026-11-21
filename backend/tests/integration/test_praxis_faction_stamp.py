"""A praxis scores under the faction each side held at submission (#3873)."""
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from game_config import CURRENT_ERA
from models.character import Character
from models.character_stats import CharacterStats
from models.duel import Duel, DuelStatus
from models.era import Era
from models.faction import Faction, FactionStatus
from models.praxis import PraxisMember, PraxisStatus
from services.character_stats import recalculate_character_stats
from services.duel import respond_to_duel_challenge
from tests.integration.factories import (
    attach_proof,
    cast_vote,
    make_character,
    make_duel,
    make_solo_praxis,
    make_task,
    raise_to_duel_level,
)


async def _score(session: AsyncSession, character: Character, era: Era) -> int:
    await recalculate_character_stats(character.id, session, CURRENT_ERA)
    await session.commit()
    return (await session.execute(
        select(CharacterStats.score).where(
            CharacterStats.character_id == character.id,
            CharacterStats.era_id == era.id,
        )
    )).scalar_one()


async def _factions(session: AsyncSession) -> None:
    for slug in ("snide", "ua", "everymen"):
        found = await session.execute(select(Faction).where(Faction.slug == slug))
        if found.scalar_one_or_none() is None:
            session.add(Faction(slug=slug, status=FactionStatus.visible))
    await session.flush()


async def _defect(session: AsyncSession, character: Character) -> None:
    character.faction_slug = "everymen"
    await session.commit()


async def test_winner_defecting_does_not_reprice_the_win(
    db_session: AsyncSession, era: Era
):
    await _factions(db_session)
    duel, snide, ua = await make_duel(
        db_session, era, label="w", challenger_votes=5, opponent_votes=1,
        challenger_faction="snide", opponent_faction="ua", commit=True,
    )
    before = await _score(db_session, snide, era)
    await _defect(db_session, snide)
    assert await _score(db_session, snide, era) == before


async def test_tie_taker_defecting_does_not_reprice_the_opponent(
    db_session: AsyncSession, era: Era
):
    await _factions(db_session)
    duel, snide, ua = await make_duel(
        db_session, era, label="t", challenger_votes=3, opponent_votes=3,
        challenger_faction="snide", opponent_faction="ua", commit=True,
    )
    before = await _score(db_session, ua, era)
    await _defect(db_session, snide)
    assert await _score(db_session, ua, era) == before


async def test_accepter_defecting_does_not_reprice_the_challenger(
    db_session: AsyncSession, era: Era
):
    await _factions(db_session)
    ua = await make_character(db_session, era, username="aua", faction_slug="ua")
    snide = await make_character(db_session, era, username="asn", faction_slug="snide")
    voter = await make_character(db_session, era, username="avo")
    await raise_to_duel_level(db_session, snide.id)
    task = await make_task(db_session, ua)
    ua_praxis = await make_solo_praxis(db_session, task, ua)
    duel = Duel(
        task_id=task.id,
        challenger_praxis_id=ua_praxis.id,
        opponent_character_id=snide.id,
        status=DuelStatus.pending,
    )
    db_session.add(duel)
    await db_session.flush()
    snide_praxis, _ = await respond_to_duel_challenge(
        duel.id, snide.id, True, db_session
    )
    snide_praxis.status = PraxisStatus.submitted
    await db_session.execute(  # the seal's stamp, which this test skips
        update(PraxisMember)
        .where(PraxisMember.praxis_id == snide_praxis.id)
        .values(faction_slug="snide")
    )
    await attach_proof(db_session, snide_praxis)
    await cast_vote(db_session, ua_praxis, voter, 3)
    await cast_vote(db_session, snide_praxis, voter, 3)
    await db_session.commit()

    before = await _score(db_session, ua, era)
    await _defect(db_session, snide)
    assert await _score(db_session, ua, era) == before


async def test_seal_stamps_the_faction_held_then(
    client, db_session: AsyncSession, character: Character, active_task, era: Era,
    auth_headers: dict,
):
    await _factions(db_session)
    character.faction_slug = "ua"
    await db_session.commit()
    created = await client.post(
        "/praxes",
        json={"task_id": active_task.id, "type": "solo", "title": "Sealed"},
        headers=auth_headers,
    )
    praxis_id = created.json()["id"]
    await _defect(db_session, character)  # mid-praxis, before the seal
    submit = await client.post(f"/praxes/{praxis_id}/submit", headers=auth_headers)
    assert submit.status_code == 200

    async def _stamp() -> str:
        return (await db_session.execute(
            select(PraxisMember.faction_slug).where(
                PraxisMember.praxis_id == praxis_id
            )
        )).scalar_one()

    assert await _stamp() == "everymen"
    character.faction_slug = "snide"  # after the seal
    await db_session.commit()
    assert await _stamp() == "everymen"
