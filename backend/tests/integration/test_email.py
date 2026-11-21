"""Notification email (#2164): what ``notify`` queues, when it leaves, and unsubscribe.

Seam: ``services.push.notify`` queues on the session (``_EMAIL_OUTBOX``); the commit
sends via ``push.send_email``, patched here so nothing touches the network. Every test
sets email availability itself and never reads the container's environment.
"""

import asyncio

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from models.account import Account, AccountStatus
from models.character import Character, CharacterStatus
from models.character_block import CharacterBlock
from services import push
from services.email import unsubscribe_token
from services.notification_prefs import NOTIFICATION_EVENTS, resolve_prefs
from tests.integration.factories import make_solo_praxis, make_task


@pytest.fixture
def mail_on(monkeypatch):
    monkeypatch.setattr(settings, "RESEND_API_KEY", "re_test")
    monkeypatch.setattr(settings, "EMAIL_FROM", "hi@mail.worldzero.org")


@pytest.fixture
def sent(monkeypatch):
    out = []

    async def fake(to, **message):
        out.append((to, message))

    monkeypatch.setattr(push, "send_email", fake)
    return out


def _queued(db_session: AsyncSession) -> list:
    return db_session.sync_session.info.get(push._EMAIL_OUTBOX, [])


async def _comment_on_mine(db_session, character, character2):
    task = await make_task(db_session, character, title="Feed a stranger")
    praxis = await make_solo_praxis(db_session, task, character)
    await push.notify_comment(
        db_session,
        character2,
        comment_id=1,
        praxis_id=praxis.id,
        task_id=None,
        mentioned=[],
    )


@pytest.mark.asyncio
async def test_a_comment_on_mine_queues_one_mail_and_the_commit_sends_it(
    db_session, character, character2, mail_on, sent
):
    await _comment_on_mine(db_session, character, character2)
    ((kind, to, _),) = _queued(db_session)
    assert (kind, to) == ("comment_on_mine", "test@example.com")
    assert sent == []

    await db_session.commit()
    await asyncio.gather(*push._in_flight)
    assert [address for address, _ in sent] == ["test@example.com"]
    assert "Comments on my praxis" in sent[0][1]["text"]


@pytest.mark.asyncio
async def test_a_rollback_drops_the_mail(
    db_session, character, character2, mail_on, sent
):
    await _comment_on_mine(db_session, character, character2)
    await db_session.rollback()
    await asyncio.gather(*push._in_flight)
    assert sent == []


@pytest.mark.asyncio
async def test_no_key_queues_no_mail(
    db_session, character, character2, monkeypatch
):
    monkeypatch.setattr(settings, "RESEND_API_KEY", "")
    await _comment_on_mine(db_session, character, character2)
    assert _queued(db_session) == []


@pytest.mark.asyncio
async def test_a_switched_off_row_queues_no_mail(
    db_session, account, character, character2, mail_on
):
    account.notification_prefs = {"comment_on_mine": {"by_email": False}}
    await _comment_on_mine(db_session, character, character2)
    assert _queued(db_session) == []


@pytest.mark.asyncio
async def test_a_banned_recipient_gets_no_mail(
    db_session, character, character2, mail_on
):
    character.status = CharacterStatus.banned
    await db_session.flush()
    await _comment_on_mine(db_session, character, character2)
    assert _queued(db_session) == []


@pytest.mark.asyncio
async def test_a_deleted_account_gets_no_mail(
    db_session, account, character, character2, mail_on
):
    account.status = AccountStatus.deleted
    await db_session.flush()
    await _comment_on_mine(db_session, character, character2)
    assert _queued(db_session) == []


@pytest.mark.asyncio
async def test_a_blocked_actor_sends_no_mail(
    db_session, character, character2, mail_on
):
    db_session.add(
        CharacterBlock(
            blocker_character_id=character.id, blocked_character_id=character2.id
        )
    )
    await db_session.flush()
    await _comment_on_mine(db_session, character, character2)
    assert _queued(db_session) == []


@pytest.mark.asyncio
async def test_a_broadcast_row_is_never_mailed(
    db_session, account, character, mail_on
):
    account.notification_prefs = {"era_announcement": {"by_email": True}}
    await push.notify(
        db_session,
        kind="era_announcement",
        recipient_id=character.id,
        tag="era",
        url="/updates",
    )
    assert _queued(db_session) == []


@pytest.mark.asyncio
async def test_prefs_report_whether_email_is_available(
    client: AsyncClient, auth_headers: dict, mail_on, monkeypatch
):
    body = (await client.get("/me/notification-prefs", headers=auth_headers)).json()
    assert body["email_available"] is True
    monkeypatch.setattr(settings, "RESEND_API_KEY", "")
    body = (await client.get("/me/notification-prefs", headers=auth_headers)).json()
    assert body["email_available"] is False


@pytest.mark.asyncio
async def test_one_click_turns_off_only_that_row_and_is_idempotent(
    client: AsyncClient, db_session: AsyncSession, account: Account
):
    token = unsubscribe_token(account.id, "comment_on_mine")
    for _ in range(2):  # no auth header: the token is the key
        resp = await client.post(f"/email/unsubscribe?token={token}")
        assert resp.status_code == 200
        assert resp.json() == {"event": "comment_on_mine"}
    await db_session.refresh(account)
    prefs = resolve_prefs(account.notification_prefs)
    assert prefs["comment_on_mine"].by_email is False
    assert prefs["comment_mention"].by_email is True  # default on, untouched


@pytest.mark.asyncio
async def test_all_off_turns_off_every_row(
    client: AsyncClient, db_session: AsyncSession, account: Account
):
    token = unsubscribe_token(account.id, "comment_on_mine")
    assert (await client.post(f"/email/unsubscribe-all?token={token}")).status_code == 200
    await db_session.refresh(account)
    prefs = resolve_prefs(account.notification_prefs)
    assert [e.key for e in NOTIFICATION_EVENTS if prefs[e.key].by_email] == []


@pytest.mark.asyncio
@pytest.mark.parametrize("path", ["unsubscribe", "unsubscribe-all"])
async def test_a_bad_token_is_a_400_not_a_500(client: AsyncClient, path: str):
    resp = await client.post(f"/email/{path}?token=forged")
    assert resp.status_code == 400
    assert resp.json()["detail"]["code"] == "EMAIL_UNSUBSCRIBE_BAD_TOKEN"
