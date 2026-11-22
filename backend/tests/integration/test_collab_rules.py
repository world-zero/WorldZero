"""#4201: collab rules read CollabState; the owner's rulings Q2, Q3, Q6, Q7."""

from datetime import datetime, timedelta, timezone

import pytest
from httpx import AsyncClient
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from game_config import CURRENT_ERA
from models.account import Account
from models.character import Character
from models.praxis import MediaItem, Praxis
from models.task import Task
from services import collab_consensus
from tests.integration.factories import make_admin
from tests.integration.test_collab_solo_conversion import _collab_with_members

pytestmark = pytest.mark.asyncio


def _code(response) -> str:
    return response.json()["detail"]["code"]


async def _trio(client, task, character, character2, character3, h, h2, h3) -> int:
    """Host character2 with members character and character3."""
    return await _collab_with_members(
        client, task, h2, [(character.id, h), (character3.id, h3)]
    )


async def _row(db_session: AsyncSession, praxis_id: int) -> Praxis:
    return await db_session.scalar(
        select(Praxis)
        .where(Praxis.id == praxis_id)
        .execution_options(populate_existing=True)
    )


async def test_last_member_cannot_leave(
    client: AsyncClient,
    character2: Character,
    active_task: Task,
    auth_headers2: dict,
    db_session: AsyncSession,
):
    praxis_id = await _collab_with_members(client, active_task, auth_headers2, [])
    refused = await client.post(f"/praxes/{praxis_id}/leave", headers=auth_headers2)
    assert refused.status_code == 409
    assert _code(refused) == "COLLAB_LAST_MEMBER"
    assert len((await _row(db_session, praxis_id)).members) == 1


async def test_sole_member_after_last_decline_still_converts(
    client: AsyncClient,
    character: Character,
    character2: Character,
    active_task: Task,
    auth_headers: dict,
    auth_headers2: dict,
):
    """Q2 meets #4185: conversion is not a leave, so the refusal does not touch it."""
    praxis_id = await _collab_with_members(client, active_task, auth_headers2, [])
    invite = await client.post(
        f"/praxes/{praxis_id}/invite",
        json={"invitee_id": character.id},
        headers=auth_headers2,
    )
    declined = await client.post(
        f"/praxes/{praxis_id}/invite/{invite.json()['id']}/respond",
        json={"accept": False},
        headers=auth_headers,
    )
    assert declined.status_code == 200
    view = await client.get(f"/praxes/{praxis_id}", headers=auth_headers2)
    assert view.json()["type"] == "solo"


async def test_accept_while_proposed_resets_window_and_approvals(
    client: AsyncClient,
    praxis_collab: Praxis,
    character3: Character,
    auth_headers: dict,
    auth_headers3: dict,
    db_session: AsyncSession,
):
    await client.post(f"/praxes/{praxis_collab.id}/submit", headers=auth_headers)
    invite = await client.post(
        f"/praxes/{praxis_collab.id}/invite",
        json={"invitee_id": character3.id},
        headers=auth_headers,
    )
    accepted = await client.post(
        f"/praxes/{praxis_collab.id}/invite/{invite.json()['id']}/respond",
        json={"accept": True},
        headers=auth_headers3,
    )
    assert accepted.status_code == 200
    body = (
        await client.get(f"/praxes/{praxis_collab.id}", headers=auth_headers)
    ).json()
    assert body["status"] == "in_progress"
    assert body["submit_proposed_at"] is None
    assert len((await _row(db_session, praxis_collab.id)).members) == 3
    assert not any(m["has_approved"] for m in body["members"])


async def test_leave_while_proposed_keeps_the_window(
    client: AsyncClient,
    character: Character,
    character2: Character,
    character3: Character,
    active_task: Task,
    auth_headers: dict,
    auth_headers2: dict,
    auth_headers3: dict,
    db_session: AsyncSession,
):
    praxis_id = await _trio(
        client,
        active_task,
        character,
        character2,
        character3,
        auth_headers,
        auth_headers2,
        auth_headers3,
    )
    await client.post(f"/praxes/{praxis_id}/submit", headers=auth_headers2)
    proposed_at = (await _row(db_session, praxis_id)).submit_proposed_at
    left = await client.post(f"/praxes/{praxis_id}/leave", headers=auth_headers3)
    assert left.status_code == 200
    row = await _row(db_session, praxis_id)
    assert row.status.value == "pending"
    assert row.submit_proposed_at == proposed_at


async def _go_live(client, praxis_id, *headers) -> None:
    for h in headers:
        assert (
            await client.post(f"/praxes/{praxis_id}/submit", headers=h)
        ).status_code == 200


async def test_live_collab_media_is_locked(
    client: AsyncClient,
    praxis_collab: Praxis,
    auth_headers: dict,
    auth_headers2: dict,
    db_session: AsyncSession,
):
    await _go_live(client, praxis_collab.id, auth_headers, auth_headers2)
    media_id = await db_session.scalar(
        select(MediaItem.id).where(MediaItem.praxis_id == praxis_collab.id)
    )
    deleted = await client.delete(
        f"/praxes/{praxis_collab.id}/media/{media_id}", headers=auth_headers
    )
    added = await client.post(
        f"/praxes/{praxis_collab.id}/media/batch",
        files=[("files", ("a.png", b"x", "image/png"))],
        headers=auth_headers,
    )
    for refused in (deleted, added):
        assert refused.status_code == 409
        assert _code(refused) == "COLLAB_LIVE_LOCKED"
    assert (await _row(db_session, praxis_collab.id)).status.value == "submitted"


@pytest.mark.parametrize("exit_by", ["leave", "kick"])
async def test_host_exit_passes_the_host_role_to_a_seeded_member(
    client: AsyncClient,
    character: Character,
    character2: Character,
    character3: Character,
    active_task: Task,
    auth_headers: dict,
    auth_headers2: dict,
    auth_headers3: dict,
    db_session: AsyncSession,
    monkeypatch,
    exit_by: str,
):
    praxis_id = await _trio(
        client,
        active_task,
        character,
        character2,
        character3,
        auth_headers,
        auth_headers2,
        auth_headers3,
    )
    monkeypatch.setattr(collab_consensus, "pick_new_host", lambda praxis: character3.id)
    if exit_by == "leave":
        done = await client.post(f"/praxes/{praxis_id}/leave", headers=auth_headers2)
    else:
        done = await client.post(
            f"/praxes/{praxis_id}/kick/{character2.id}", headers=auth_headers
        )
    assert done.status_code == 200, done.text
    assert (await _row(db_session, praxis_id)).created_by_id == character3.id
    deleted = await client.delete(f"/praxes/{praxis_id}", headers=auth_headers3)
    assert deleted.status_code == 204


async def test_live_collab_cannot_be_resealed(
    client: AsyncClient,
    praxis_collab: Praxis,
    auth_headers: dict,
    auth_headers2: dict,
    db_session: AsyncSession,
):
    await _go_live(client, praxis_collab.id, auth_headers, auth_headers2)
    sealed_at = (await _row(db_session, praxis_collab.id)).submitted_at
    again = await client.post(
        f"/praxes/{praxis_collab.id}/submit", headers=auth_headers
    )
    assert again.status_code == 409
    assert _code(again) == "PRAXIS_ALREADY_LIVE"
    assert (await _row(db_session, praxis_collab.id)).submitted_at == sealed_at


async def test_reopen_nulls_approved_at_like_edit_and_kick(
    client: AsyncClient,
    praxis_collab: Praxis,
    auth_headers: dict,
    auth_headers2: dict,
):
    await _go_live(client, praxis_collab.id, auth_headers, auth_headers2)
    reopened = await client.post(
        f"/praxes/{praxis_collab.id}/unsubmit", headers=auth_headers
    )
    assert reopened.status_code == 200
    assert all(m["approved_at"] is None for m in reopened.json()["members"])


@pytest.mark.proof_rule
async def test_clock_seal_gets_no_admin_exemption(
    client: AsyncClient,
    praxis_collab: Praxis,
    account: Account,
    auth_headers: dict,
    db_session: AsyncSession,
):
    await db_session.execute(
        delete(MediaItem).where(MediaItem.praxis_id == praxis_collab.id)
    )
    await make_admin(db_session, account)
    assert (
        await client.post(f"/praxes/{praxis_collab.id}/submit", headers=auth_headers)
    ).status_code == 200
    row = await _row(db_session, praxis_collab.id)
    row.submit_proposed_at = datetime.now(timezone.utc) - timedelta(
        days=CURRENT_ERA.collab_auto_submit_days, seconds=1
    )
    await db_session.commit()
    assert (
        await client.get(f"/praxes/{praxis_collab.id}", headers=auth_headers)
    ).json()["status"] == "pending"


@pytest.mark.proof_rule
async def test_leave_seal_exempts_only_a_leaver_who_is_admin(
    client: AsyncClient,
    praxis_collab: Praxis,
    account: Account,
    auth_headers: dict,
    auth_headers2: dict,
    db_session: AsyncSession,
):
    await db_session.execute(
        delete(MediaItem).where(MediaItem.praxis_id == praxis_collab.id)
    )
    await make_admin(db_session, account)
    await client.post(f"/praxes/{praxis_collab.id}/submit", headers=auth_headers)
    await client.post(f"/praxes/{praxis_collab.id}/leave", headers=auth_headers2)
    assert (await _row(db_session, praxis_collab.id)).status.value != "submitted"


async def test_kick_on_a_praxis_converted_to_solo_is_a_400(
    client: AsyncClient,
    character: Character,
    character2: Character,
    active_task: Task,
    auth_headers: dict,
    auth_headers2: dict,
):
    praxis_id = await _collab_with_members(
        client, active_task, auth_headers2, [(character.id, auth_headers)]
    )
    left = await client.post(f"/praxes/{praxis_id}/leave", headers=auth_headers)
    assert left.status_code == 200
    stale = await client.post(
        f"/praxes/{praxis_id}/kick/{character.id}", headers=auth_headers2
    )
    assert stale.status_code == 400
