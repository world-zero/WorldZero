"""Player standing rules (#4237: S1/S2a/S3/S5/S7 + gap 4 of #4204), at the HTTP seam."""
from datetime import datetime, timezone

import pytest
from sqlalchemy import select

from errors import ErrorCode
from models.account import Account, AccountStatus
from models.character import CharacterStatus
from models.duel import DuelStatus
from models.praxis import (
    Praxis,
    PraxisInvite,
    PraxisMember,
    PraxisStatus,
    PraxisType,
)
from models.vote import Vote
from services import admin_service, character_stats
from services import praxis as praxis_service
from services.character import has_current_terms, is_playable
from services.praxis import invite_to_praxis
from services.standing import counts_as_voter, standing_of
from services.vote_ring import get_vote_ring
from services.vote_tally import counted_votes
from tests.integration.factories import (
    make_admin,
    make_character,
    make_duel,
    make_solo_praxis,
)


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


async def test_a_ban_that_was_the_last_wait_seals_the_collab(
    client, db_session, account, auth_headers, auth_headers2, character2,
    praxis_collab,
):
    await make_admin(db_session, account)
    url = f"/praxes/{praxis_collab.id}/submit"
    pending = await client.post(url, headers=auth_headers)
    assert pending.json()["status"] != "submitted"

    assert (await _ban(client, character2.id, auth_headers)).status_code == 200

    await db_session.refresh(praxis_collab)
    assert praxis_collab.status == PraxisStatus.submitted


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


async def test_s3_account_delete_cancels_invites(
    client, db_session, character, character3, praxis_collab, auth_headers
):
    await invite_to_praxis(praxis_collab.id, character3.id, character.id, db_session)
    await db_session.commit()
    assert len(await _pending(db_session)) == 1

    assert (await client.delete("/me/account", headers=auth_headers)).status_code == 204
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


async def test_a_ban_forfeits_a_sibling_lifes_duel_and_closes_its_socket(
    client, db_session, account, auth_headers, era, some_faction, monkeypatch
):
    await make_admin(db_session, account)
    duel, _, sibling_b = await make_duel(
        db_session, era, label="sib", status=DuelStatus.pending
    )
    life_a = await make_character(
        db_session, era, username="siba", account=await db_session.get(
            Account, sibling_b.account_id
        )
    )
    await db_session.commit()
    closed = []
    monkeypatch.setattr(admin_service, "close_character_sockets", closed.append)

    assert (await _ban(client, life_a.id, auth_headers)).status_code == 200

    await db_session.refresh(duel)
    assert duel.forfeited_by_character_id == sibling_b.id
    assert sibling_b.id in closed


async def test_a_ban_takes_every_stats_lock_in_one_ascending_pass(
    client, db_session, account, auth_headers, era, character, active_task,
    some_faction, monkeypatch
):
    """#4314: seal recalcs and the vote rescore must not lock out of order."""
    await make_admin(db_session, account)
    solo = await make_solo_praxis(db_session, active_task, character)
    stay = await make_character(db_session, era, username="stay")
    leave = await make_character(db_session, era, username="leave")
    collab = Praxis(
        task_id=active_task.id, created_by_id=stay.id, type=PraxisType.collab,
        title="c", body_text="proof",
    )
    db_session.add(collab)
    await db_session.flush()
    db_session.add_all(
        PraxisMember(praxis_id=collab.id, character_id=m.id) for m in (stay, leave)
    )
    db_session.add(Vote(
        praxis_id=solo.id, voter_character_id=leave.id,
        voter_account_id=leave.account_id, value=3,
    ))
    await db_session.commit()

    taken: list[int] = []
    real = character_stats.lock_character_stats

    async def spy(ids, session):
        ids = sorted(set(ids))
        taken.extend(ids)
        return await real(ids, session)

    monkeypatch.setattr(character_stats, "lock_character_stats", spy)
    monkeypatch.setattr(praxis_service, "lock_character_stats", spy)

    assert (await _ban(client, leave.id, auth_headers)).status_code == 200

    first = list(dict.fromkeys(taken))
    assert {character.id, stay.id, leave.id} <= set(first)
    assert first == sorted(first)


async def test_gap4_voter_sql_agrees_with_the_predicate(db_session, era, some_faction):
    duel, _, _ = await make_duel(db_session, era, label="g4")
    suspended = await make_character(db_session, era, username="g4s")
    banned = await make_character(db_session, era, username="g4b")
    active = await make_character(db_session, era, username="g4a")
    departed = await make_character(db_session, era, username="g4d")
    suspended_account = await db_session.get(Account, suspended.account_id)
    suspended_account.status = AccountStatus.suspended
    banned.status = CharacterStatus.banned
    departed.status = CharacterStatus.banned
    departed.departed_at = datetime.now(timezone.utc)
    voters = {
        suspended: AccountStatus.suspended,
        banned: AccountStatus.active,
        active: AccountStatus.active,
        departed: AccountStatus.active,
    }
    for voter in voters:
        db_session.add(
            Vote(
                praxis_id=duel.challenger_praxis_id,
                voter_character_id=voter.id,
                voter_account_id=voter.account_id,
                value=3,
            )
        )
    await db_session.flush()

    counted = set(
        (
            await db_session.scalars(
                counted_votes(select(Vote.voter_character_id)).where(
                    Vote.voter_character_id.in_([v.id for v in voters])
                )
            )
        ).all()
    )
    assert counted == {
        v.id
        for v, status in voters.items()
        if counts_as_voter(*standing_of(status, v))
    }
    assert counted == {active.id, departed.id}


async def test_gap4_vote_ring_and_profile_hide_a_suspended_player(
    client, db_session, account, account2, character, character2
):
    assert (await get_vote_ring(account.id, db_session)).eligible == 1
    assert (await client.get(f"/characters/{character2.id}")).status_code == 200

    account2.status = AccountStatus.suspended
    await db_session.commit()

    assert (await get_vote_ring(account.id, db_session)).eligible == 0
    assert (await client.get(f"/characters/{character2.id}")).status_code == 404


def _gated(resp, code: ErrorCode) -> bool:
    detail = resp.json().get("detail") if resp.status_code == 403 else None
    return isinstance(detail, dict) and detail.get("code") == code.value


@pytest.mark.needs_terms
async def test_needs_terms_exempt_routes_and_dev_login(
    client, db_session, account, character, auth_headers
):
    refused = await client.post(
        "/characters", json={"display_name": "Nope"}, headers=auth_headers
    )
    assert _gated(refused, ErrorCode.terms_required)

    for path, kwargs in (
        ("/contact", {"json": {"name": "n", "email": "e@x", "message": "m"}}),
        ("/email/unsubscribe?token=bad", {}),
        ("/email/unsubscribe-all?token=bad", {}),
        ("/terms/acceptance", {}),
    ):
        resp = await client.post(path, headers=auth_headers, **kwargs)
        assert not _gated(resp, ErrorCode.terms_required), path


@pytest.mark.needs_terms
async def test_needs_terms_account_delete_is_exempt(client, character, auth_headers):
    resp = await client.delete("/me/account", headers=auth_headers)
    assert resp.status_code == 204


@pytest.mark.needs_terms
async def test_needs_terms_banned_life_keeps_its_own_routes(
    client, db_session, character, auth_headers
):
    accepted = await client.post("/terms/acceptance", headers=auth_headers)
    assert accepted.status_code == 201
    character.status = CharacterStatus.banned
    await db_session.commit()
    for path, body in (
        ("/characters", {"display_name": "Again"}),
        ("/me/active-character", {"character_id": character.id}),
    ):
        resp = await client.post(path, json=body, headers=auth_headers)
        assert not _gated(resp, ErrorCode.account_banned), path


@pytest.mark.needs_terms
async def test_needs_terms_dev_login_stamps_terms_only_with_a_character(
    client, db_session, era, some_faction
):
    named = await client.post("/auth/dev-login?key=nt1&name=Terms%20Bot")
    assert await has_current_terms(named.json()["account_id"], db_session)
    bare = await client.post("/auth/dev-login?key=nt2")
    assert not await has_current_terms(bare.json()["account_id"], db_session)
