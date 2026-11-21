"""Deleting a praxis refunds its voters' spent votes (#3933).

Seam: ``DELETE /praxes/{id}`` (and ``delete_praxis`` for the earlier-era case).
"""
import pytest
from sqlalchemy import select, update

from models.character_stats import CharacterStats
from models.praxis import PraxisStatus
from models.vote import Vote
from services.character_stats import recompute_votes_spent_this_era
from services.praxis import delete_praxis
from tests.integration.factories import cast_vote, make_solo_praxis, make_task
from tests.integration.test_vote_era_followups import _live_era_after

pytestmark = pytest.mark.asyncio


async def _spent(db_session, character_id, era_id) -> int:
    row = await db_session.execute(
        select(CharacterStats.votes_spent_this_era)
        .where(
            CharacterStats.character_id == character_id, CharacterStats.era_id == era_id
        )
        .execution_options(populate_existing=True)
    )
    return row.scalar_one()


async def _unsubmit_delete(client, praxis_id, author_headers):
    resp = await client.post(f"/praxes/{praxis_id}/unsubmit", headers=author_headers)
    assert resp.status_code == 200, resp.text
    resp = await client.delete(f"/praxes/{praxis_id}", headers=author_headers)
    assert resp.status_code == 204, resp.text


async def _vote(client, praxis_id, headers):
    resp = await client.post(
        f"/praxes/{praxis_id}/vote", json={"value": 4}, headers=headers
    )
    assert resp.status_code == 200, resp.text


async def test_delete_refunds_the_voter_and_the_recompute_finds_no_drift(
    client, db_session, character2, praxis_solo, era, auth_headers, auth_headers2
):
    await _vote(client, praxis_solo.id, auth_headers2)
    assert await _spent(db_session, character2.id, era.id) == 1

    await _unsubmit_delete(client, praxis_solo.id, auth_headers)

    assert await _spent(db_session, character2.id, era.id) == 0
    repairs = await recompute_votes_spent_this_era(
        db_session, era_row=era, dry_run=True
    )
    assert repairs == []


async def test_each_of_several_voters_is_refunded_exactly_one(
    client, db_session, character2, character3, praxis_solo, era,
    auth_headers, auth_headers2, auth_headers3,
):
    await _vote(client, praxis_solo.id, auth_headers2)
    await _vote(client, praxis_solo.id, auth_headers3)
    await db_session.execute(
        update(CharacterStats)
        .where(CharacterStats.character_id == character3.id)
        .values(votes_spent_this_era=3)
    )
    await db_session.commit()

    await _unsubmit_delete(client, praxis_solo.id, auth_headers)

    assert await _spent(db_session, character2.id, era.id) == 0
    assert await _spent(db_session, character3.id, era.id) == 2


async def test_delete_without_votes_changes_no_budget(
    client, db_session, character2, praxis_solo, era, auth_headers
):
    await _unsubmit_delete(client, praxis_solo.id, auth_headers)

    assert await _spent(db_session, character2.id, era.id) == 0


async def test_a_prior_era_vote_refunds_that_eras_row_only(
    db_session, account, character, character2, era
):
    live = await _live_era_after(db_session, era, account)
    db_session.add(
        CharacterStats(
            character_id=character2.id, era_id=live.id, votes_spent_this_era=1
        )
    )
    task = await make_task(db_session, character)
    praxis = await make_solo_praxis(
        db_session, task, character, status=PraxisStatus.in_progress
    )
    await cast_vote(db_session, praxis, character2, 4)
    await db_session.execute(update(Vote).values(era_id=era.id))
    await db_session.execute(
        update(CharacterStats)
        .where(
            CharacterStats.character_id == character2.id,
            CharacterStats.era_id == era.id,
        )
        .values(votes_spent_this_era=1)
    )
    await db_session.commit()

    await delete_praxis(praxis.id, character.id, db_session)
    await db_session.commit()

    assert await _spent(db_session, character2.id, era.id) == 0
    assert await _spent(db_session, character2.id, live.id) == 1
