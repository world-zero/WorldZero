"""Mutual votes take their stats rows in one ascending order (#3978).

Needs COMMITTED rows and real connections; the tables are truncated afterwards.
"""
import asyncio

import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

import services.vote as vote_service
from game_config import CURRENT_ERA
from models.character import Character
from models.character_stats import CharacterStats
from models.era import Era
from models.vote import Vote
from seed import upsert_era_factions
from services.vote import cast_vote_on_praxis
from tests.integration.conftest import _TEST_DB_URL
from tests.integration.factories import (
    make_account,
    make_character,
    make_solo_praxis,
    make_task,
)

pytestmark = pytest.mark.asyncio


async def test_a_votes_b_while_b_votes_a_both_commit(monkeypatch) -> None:
    engine = create_async_engine(_TEST_DB_URL, poolclass=NullPool)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with factory() as s:
            await upsert_era_factions(s, CURRENT_ERA)
            owner = await make_account(s, "owner@example.com")
            era = Era(
                name=CURRENT_ERA.name,
                config_key=CURRENT_ERA.config_key,
                started_by_id=owner.id,
            )
            s.add(era)
            await s.flush()
            level = CURRENT_ERA.vote_level_required
            a, b, c = [
                await make_character(s, era, username=n, level=level)
                for n in ("aaa", "bbb", "ccc")
            ]
            task = await make_task(s, a)
            pa = await make_solo_praxis(s, task, a)
            pb = await make_solo_praxis(s, task, b)
            # C's votes unlock voting for A and B (a vote must be received first).
            for p in (pa, pb):
                s.add(Vote(
                    praxis_id=p.id, voter_character_id=c.id,
                    voter_account_id=c.account_id, value=3, era_id=era.id,
                ))
            await s.commit()
            a_id, b_id, pa_id, pb_id = a.id, b.id, pa.id, pb.id

        # Hold each cast at its recalc until both have written their budget row.
        real = vote_service.recalculate_members_stats
        arrived, both = 0, asyncio.Event()

        async def gated(*args, **kwargs):
            nonlocal arrived
            arrived += 1
            if arrived == 2:
                both.set()
            try:
                # With the fix the second cast is parked on the lock and never arrives.
                await asyncio.wait_for(both.wait(), 1)
            except asyncio.TimeoutError:
                pass
            return await real(*args, **kwargs)

        monkeypatch.setattr(vote_service, "recalculate_members_stats", gated)

        async def cast(voter_id: int, praxis_id: int):
            async with factory() as s:
                voter = await s.get(Character, voter_id)
                await cast_vote_on_praxis(voter, praxis_id, 5, s, CURRENT_ERA)
                await s.commit()

        await asyncio.gather(cast(a_id, pb_id), cast(b_id, pa_id))

        async with factory() as s:
            rows = {
                r.character_id: r
                for r in (await s.execute(select(CharacterStats))).scalars()
            }
        assert rows[a_id].votes_spent_this_era == 1
        assert rows[b_id].votes_spent_this_era == 1
        # Each author holds the votes they received (C's 3 plus the new 5).
        assert rows[a_id].score == rows[b_id].score > 0
    finally:
        async with engine.begin() as conn:
            await conn.execute(text(
                "TRUNCATE account, era, faction RESTART IDENTITY CASCADE"
            ))
        await engine.dispose()
