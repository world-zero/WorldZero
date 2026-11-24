"""Copy proposals (#4280): token-only filing, edit_copy settling.

Seam: the HTTP routes over ``services.copy_proposal``; the push is read off the
session outbox (no network).
"""

import asyncio

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from models.account import Account
from models.copy_override import CopyOverride
from models.copy_proposal import CopyProposal
from models.roles import Permission
from services import push
from services.copy_override import current_value
from tests.integration.factories import make_admin
from tests.integration.test_push import PRIVATE, PUBLIC, SUBSCRIPTION

TOKEN = "s3cret-proposal-token"
LINE = {
    "ns": "common",
    "key": "nav.home",
    "owner_value": "Hearth",
    "proposed_value": "Home",
}
BODY = {
    "pr_number": 7,
    "pr_url": "https://github.com/world-zero/WorldZero/pull/7",
    "lines": [LINE],
}


@pytest.fixture
def keys_on(monkeypatch):
    monkeypatch.setattr(settings, "VAPID_PUBLIC_KEY", PUBLIC)
    monkeypatch.setattr(settings, "VAPID_PRIVATE_KEY", PRIVATE)
    monkeypatch.setattr(settings, "VAPID_CONTACT", "mailto:hi@worldzero.org")


@pytest.fixture
def token_on(monkeypatch):
    monkeypatch.setattr(settings, "COPY_PROPOSAL_TOKEN", TOKEN)


async def _file(client: AsyncClient, body: dict = BODY, token: str | None = TOKEN):
    headers = {} if token is None else {"X-Copy-Proposal-Token": token}
    return await client.post("/copy-proposals", json=body, headers=headers)


async def _own(db_session: AsyncSession, account: Account, value: str = "Hearth"):
    await make_admin(db_session, account)
    db_session.add(
        CopyOverride(ns="common", key="nav.home", value=value, updated_by_id=account.id)
    )
    await db_session.commit()


async def _approve(client, proposal_id, headers, action="approve"):
    return await client.post(
        f"/copy-proposals/{proposal_id}/{action}",
        json={"ns": "common", "key": "nav.home"},
        headers=headers,
    )


@pytest.mark.asyncio
async def test_unset_token_refuses_even_an_empty_header(client: AsyncClient):
    assert settings.COPY_PROPOSAL_TOKEN == ""
    assert (await _file(client, token="")).status_code == 503
    assert (await _file(client, token=None)).status_code == 503


@pytest.mark.asyncio
async def test_wrong_or_missing_token_is_401(client: AsyncClient, token_on):
    assert (await _file(client, token="nope")).status_code == 401
    assert (await _file(client, token=None)).status_code == 401
    assert (await _file(client, token="")).status_code == 401


@pytest.mark.asyncio
async def test_right_token_files_and_a_rerun_replaces(
    client: AsyncClient, db_session: AsyncSession, token_on, monkeypatch
):
    monkeypatch.setattr(settings, "VAPID_PRIVATE_KEY", "")  # the env may carry keys
    first = await _file(client)
    assert first.status_code == 201
    assert first.json()["pushed"] is False
    assert first.json()["lines"] == [{**LINE, "status": "open"}]

    second = await _file(
        client, {**BODY, "lines": [{**LINE, "proposed_value": "Base"}]}
    )
    assert second.json()["id"] == first.json()["id"]
    rows = (await db_session.execute(CopyProposal.__table__.select())).all()
    assert len(rows) == 1
    assert rows[0].lines[0]["proposed_value"] == "Base"


@pytest.mark.asyncio
async def test_reading_needs_edit_copy(
    client: AsyncClient, auth_headers: dict, token_on
):
    await _file(client)
    assert (
        await client.get("/copy-proposals", headers=auth_headers)
    ).status_code == 403
    assert (await _approve(client, 1, auth_headers)).status_code == 403
    assert (await _approve(client, 1, auth_headers, "reject")).status_code == 403
    assert (await client.get("/copy-proposals")).status_code in (401, 403)


@pytest.mark.asyncio
async def test_approve_writes_the_override(
    client: AsyncClient,
    db_session: AsyncSession,
    account: Account,
    auth_headers: dict,
    token_on,
):
    await _own(db_session, account)
    proposal_id = (await _file(client)).json()["id"]

    listed = await client.get("/copy-proposals", headers=auth_headers)
    assert [p["id"] for p in listed.json()] == [proposal_id]

    resp = await _approve(client, proposal_id, auth_headers)
    assert resp.status_code == 200
    assert resp.json()["lines"][0]["status"] == "approved"
    assert await current_value("common", "nav.home", db_session) == "Home"
    assert (await client.get("/copy-proposals", headers=auth_headers)).json() == []
    assert (await _approve(client, proposal_id, auth_headers)).status_code == 404


@pytest.mark.asyncio
async def test_approve_null_deletes_the_row(
    client: AsyncClient,
    db_session: AsyncSession,
    account: Account,
    auth_headers: dict,
    token_on,
):
    await _own(db_session, account)
    removal = {**BODY, "lines": [{**LINE, "proposed_value": None}]}
    proposal_id = (await _file(client, removal)).json()["id"]

    assert (await _approve(client, proposal_id, auth_headers)).status_code == 200
    assert await current_value("common", "nav.home", db_session) is None


@pytest.mark.asyncio
@pytest.mark.parametrize("proposed", ["Home", None])
async def test_approve_409_when_the_row_changed(
    client: AsyncClient,
    db_session: AsyncSession,
    account: Account,
    auth_headers: dict,
    token_on,
    proposed,
):
    await _own(db_session, account, value="Edited since")
    body = {**BODY, "lines": [{**LINE, "proposed_value": proposed}]}
    proposal_id = (await _file(client, body)).json()["id"]

    resp = await _approve(client, proposal_id, auth_headers)
    assert resp.status_code == 409
    assert await current_value("common", "nav.home", db_session) == "Edited since"
    still_open = await client.get("/copy-proposals", headers=auth_headers)
    assert still_open.json()[0]["lines"][0]["status"] == "open"


@pytest.mark.asyncio
async def test_reject_leaves_the_override_alone(
    client: AsyncClient,
    db_session: AsyncSession,
    account: Account,
    auth_headers: dict,
    token_on,
):
    await _own(db_session, account)
    proposal_id = (await _file(client)).json()["id"]

    resp = await _approve(client, proposal_id, auth_headers, "reject")
    assert resp.json()["lines"][0]["status"] == "rejected"
    assert await current_value("common", "nav.home", db_session) == "Hearth"


@pytest.mark.asyncio
async def test_filing_pushes_every_edit_copy_holder(
    client: AsyncClient,
    db_session: AsyncSession,
    account: Account,
    token_on,
    keys_on,
    monkeypatch,
):
    delivered: list = []

    async def capture(batch):
        delivered.extend(batch)

    monkeypatch.setattr(push, "deliver", capture)
    await make_admin(db_session, account, permissions=[Permission.edit_copy])
    await push.subscribe_device(
        db_session, account.id, SUBSCRIPTION["endpoint"], "k", "a"
    )
    await db_session.commit()

    resp = await _file(client)
    assert resp.json()["pushed"] is True
    await _file(client)  # a re-run while open does not push again
    await asyncio.sleep(0)
    assert len(delivered) == 1
    payload, targets = delivered[0]
    assert (payload["kind"], payload["task"], payload["count"]) == (
        "copy_proposal",
        "#7",
        1,
    )
    assert [t.endpoint for t in targets] == [SUBSCRIPTION["endpoint"]]


@pytest.mark.asyncio
async def test_rerun_keeps_an_unchanged_rejected_line_rejected(
    client: AsyncClient,
    db_session: AsyncSession,
    account: Account,
    auth_headers: dict,
    token_on,
):
    await _own(db_session, account)
    proposal_id = (await _file(client)).json()["id"]
    await _approve(client, proposal_id, auth_headers, "reject")

    again = await _file(client)
    assert again.json()["lines"][0]["status"] == "rejected"
    assert again.json()["pushed"] is False

    changed = await _file(
        client, {**BODY, "lines": [{**LINE, "proposed_value": "Base"}]}
    )
    assert changed.json()["lines"][0]["status"] == "open"


@pytest.mark.asyncio
async def test_empty_lines_without_a_proposal_store_nothing(
    client: AsyncClient, db_session: AsyncSession, token_on
):
    resp = await _file(client, {**BODY, "lines": []})
    assert resp.status_code == 201
    assert resp.json()["pushed"] is False
    assert (await db_session.execute(CopyProposal.__table__.select())).all() == []


@pytest.mark.asyncio
async def test_empty_lines_withdraw_the_proposal(
    client: AsyncClient,
    db_session: AsyncSession,
    account: Account,
    auth_headers: dict,
    token_on,
):
    await _own(db_session, account)
    await _file(client)
    resp = await _file(client, {**BODY, "lines": []})
    assert resp.status_code == 201
    assert resp.json()["pushed"] is False
    assert (await client.get("/copy-proposals", headers=auth_headers)).json() == []
