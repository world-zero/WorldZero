"""Player standing rules (#4237: S1/S2a/S3/S5/S7 + gap 4 of #4204), at the HTTP seam."""
import pytest
from sqlalchemy import select

from errors import ErrorCode
from models.account import Account, AccountStatus
from models.character import CharacterStatus
from models.praxis import PraxisInvite
from models.vote import Vote
from services.character import is_playable
from services.praxis import invite_to_praxis
from services.standing import counts_as_voter, standing_of
from services.vote_ring import get_vote_ring
from services.vote_tally import counted_votes
from tests.integration.factories import make_admin, make_character, make_duel


async def _ban(client, character_id, headers, banned=True):
    return await client.post(
        f"/admin/characters/{character_id}/ban",
        json={"banned": banned},
        headers=headers,
    )


async def _suspend(client, account_id, headers, suspended=True):
    return await client.post(
        f"/admin/accounts/{account_id}/suspend",
        json={"suspended": suspended},
        headers=headers,
    )


async def _pending(db_session):
    return (await db_session.scalars(select(PraxisInvite))).all()


async def test_s1_a_ban_on_one_life_stops_the_whole_account(
    client, db_session, account, account2, auth_headers, auth_headers2,
    character2, era, praxis_collab,
):
    await make_admin(db_session, account)
    sibling = await make_character(
        db_session, era, username="sibling", account=account2
    )
    assert await is_playable(sibling, db_session)

    assert (await _ban(client, character2.id, auth_headers)).status_code == 200

    assert not await is_playable(sibling, db_session)
    resp = await client.post(
        f"/praxes/{praxis_collab.id}/submit", headers=auth_headers2
    )
    assert resp.status_code == 403
    assert resp.json()["detail"]["code"] == ErrorCode.account_banned.value


async def test_s2a_a_banned_member_does_not_block_the_seal(
    client, db_session, character2, praxis_collab, auth_headers
):
    character2.status = CharacterStatus.banned
    await db_session.commit()

    resp = await client.post(f"/praxes/{praxis_collab.id}/submit", headers=auth_headers)

    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "submitted"
    assert character2.id in [m["character_id"] for m in resp.json()["members"]]


@pytest.mark.parametrize("how", ["ban", "suspend"])
async def test_s3_ban_and_suspend_cancel_invites_to_and_from(
    client, db_session, account, account2, auth_headers, era, character,
    character2, character3, praxis_collab, how,
):
    await make_admin(db_session, account)
    await invite_to_praxis(praxis_collab.id, character3.id, character.id, db_session)
    other = await make_character(db_session, era, username="invitee9")
    # Sent BY the player who is about to be moderated.
    await invite_to_praxis(praxis_collab.id, other.id, character2.id, db_session)
    await db_session.commit()
    assert len(await _pending(db_session)) == 2

    if how == "ban":
        resp = await _ban(client, character2.id, auth_headers)
    else:
        resp = await _suspend(client, account2.id, auth_headers)
    assert resp.status_code == 200, resp.text

    assert [i.invitee_id for i in await _pending(db_session)] == [character3.id]


async def test_s3_self_delete_cancels_invites_and_a_stale_invite_is_refused(
    client, db_session, character, character3, praxis_collab, auth_headers,
    auth_headers3,
):
    invite = await invite_to_praxis(
        praxis_collab.id, character3.id, character.id, db_session
    )
    # An inviter that vanished without the cancel (a legacy row): accept is refused.
    character.status = CharacterStatus.banned
    await db_session.commit()
    resp = await client.post(
        f"/praxes/{praxis_collab.id}/invite/{invite.id}/respond",
        json={"accept": True},
        headers=auth_headers3,
    )
    assert resp.status_code == 409
    assert resp.json()["detail"]["code"] == ErrorCode.invite_inviter_gone.value

    character.status = CharacterStatus.active
    await db_session.commit()
    deleted = await client.delete(f"/characters/{character.id}", headers=auth_headers)
    assert deleted.status_code == 204
    assert await _pending(db_session) == []


@pytest.mark.needs_terms
async def test_s5_writes_need_terms_and_reads_and_exempt_routes_do_not(
    client, auth_headers, praxis_collab
):
    resp = await client.post(f"/praxes/{praxis_collab.id}/submit", headers=auth_headers)
    assert resp.status_code == 403
    assert resp.json()["detail"]["code"] == ErrorCode.terms_required.value
    assert (await client.get("/auth/me", headers=auth_headers)).status_code == 200

    accepted = await client.post("/terms/acceptance", headers=auth_headers)
    assert accepted.status_code == 201
    resp = await client.post(f"/praxes/{praxis_collab.id}/submit", headers=auth_headers)
    assert resp.status_code == 200


async def test_s7_unban_and_unsuspend_leave_forfeits(
    client, db_session, account, auth_headers, era, some_faction
):
    await make_admin(db_session, account)
    duel, _, opponent = await make_duel(db_session, era, label="s7")
    await db_session.commit()

    await _ban(client, opponent.id, auth_headers)
    await _ban(client, opponent.id, auth_headers, banned=False)
    await _suspend(client, opponent.account_id, auth_headers)
    await _suspend(client, opponent.account_id, auth_headers, suspended=False)

    await db_session.refresh(duel)
    assert duel.forfeited_by_character_id == opponent.id


async def test_gap4_voter_sql_agrees_with_the_predicate(db_session, era, some_faction):
    duel, _, _ = await make_duel(db_session, era, label="g4")
    suspended = await make_character(db_session, era, username="g4s")
    banned = await make_character(db_session, era, username="g4b")
    suspended_account = await db_session.get(Account, suspended.account_id)
    suspended_account.status = AccountStatus.suspended
    banned.status = CharacterStatus.banned
    for voter in (suspended, banned):
        db_session.add(
            Vote(
                praxis_id=duel.challenger_praxis_id,
                voter_character_id=voter.id,
                voter_account_id=voter.account_id,
                value=3,
            )
        )
    await db_session.flush()

    counted = (
        await db_session.scalars(
            counted_votes(select(Vote.voter_character_id)).where(
                Vote.voter_character_id.in_([suspended.id, banned.id])
            )
        )
    ).all()
    assert counted == []
    assert not counts_as_voter(*standing_of(AccountStatus.suspended, suspended))
    assert not counts_as_voter(*standing_of(AccountStatus.active, banned))


async def test_gap4_vote_ring_and_profile_hide_a_suspended_player(
    client, db_session, account, account2, character, character2
):
    assert (await get_vote_ring(account.id, db_session)).eligible == 1
    assert (await client.get(f"/characters/{character2.id}")).status_code == 200

    account2.status = AccountStatus.suspended
    await db_session.commit()

    assert (await get_vote_ring(account.id, db_session)).eligible == 0
    assert (await client.get(f"/characters/{character2.id}")).status_code == 404
