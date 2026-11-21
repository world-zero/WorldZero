"""A praxis scores under the faction each side held at submission (#3873)."""
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from game_config import CURRENT_ERA
from models.character import Character
from models.character_stats import CharacterStats
from models.era import Era
from models.faction import Faction, FactionStatus
from services.character_stats import recalculate_character_stats
from tests.integration.factories import make_duel


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
