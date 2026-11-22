"""Copy overrides: public read, admin-only write, delete as revert.

Trust boundary: a PUT ``value`` lands on every visitor's screen.
"""
import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.account import Account
from models.copy_override import CopyOverride
from schemas.copy import MAX_VALUE_LENGTH
from tests.integration.factories import make_admin


@pytest.mark.asyncio
async def test_list_overrides_is_public(
    client: AsyncClient, db_session: AsyncSession, account: Account
):
    db_session.add(
        CopyOverride(
            ns="common",
            key="nav.adminMode.badge",
            value="Backstage",
            updated_by_id=account.id,
        )
    )
    await db_session.commit()

    resp = await client.get("/copy-overrides")
    assert resp.status_code == 200
    assert resp.json() == [
        {"ns": "common", "key": "nav.adminMode.badge", "value": "Backstage"}
    ]


@pytest.mark.asyncio
async def test_write_requires_admin(client: AsyncClient, auth_headers: dict):
    put = await client.put(
        "/copy-overrides",
        json={"ns": "common", "key": "nav.home", "value": "Hearth"},
        headers=auth_headers,
    )
    assert put.status_code == 403

    delete = await client.delete(
        "/copy-overrides?ns=common&key=nav.home", headers=auth_headers
    )
    assert delete.status_code == 403


@pytest.mark.asyncio
async def test_put_twice_updates_in_place(
    client: AsyncClient,
    db_session: AsyncSession,
    account: Account,
    auth_headers: dict,
):
    await make_admin(db_session, account)

    first = await client.put(
        "/copy-overrides",
        json={"ns": "common", "key": "nav.home", "value": "Hearth"},
        headers=auth_headers,
    )
    assert first.status_code == 200
    assert first.json() == {"ns": "common", "key": "nav.home", "value": "Hearth"}

    second = await client.put(
        "/copy-overrides",
        json={"ns": "common", "key": "nav.home", "value": "Homestead"},
        headers=auth_headers,
    )
    assert second.status_code == 200
    assert second.json()["value"] == "Homestead"

    rows = (await db_session.execute(select(CopyOverride))).scalars().all()
    assert len(rows) == 1
    assert rows[0].value == "Homestead"
    assert rows[0].updated_by_id == account.id


@pytest.mark.asyncio
async def test_delete_reverts_then_404s(
    client: AsyncClient,
    db_session: AsyncSession,
    account: Account,
    auth_headers: dict,
):
    await make_admin(db_session, account)
    await client.put(
        "/copy-overrides",
        json={"ns": "common", "key": "nav.home", "value": "Hearth"},
        headers=auth_headers,
    )

    first = await client.delete(
        "/copy-overrides?ns=common&key=nav.home", headers=auth_headers
    )
    assert first.status_code == 204
    assert (await client.get("/copy-overrides")).json() == []

    second = await client.delete(
        "/copy-overrides?ns=common&key=nav.home", headers=auth_headers
    )
    assert second.status_code == 404


@pytest.mark.parametrize(
    "body",
    [
        {"ns": "common", "key": "nav home", "value": "Hearth"},          # space
        {"ns": "common", "key": "nav.home[0]", "value": "Hearth"},       # brackets
        {"ns": "common", "key": "", "value": "Hearth"},                  # empty key
        {"ns": "", "key": "nav.home", "value": "Hearth"},                # empty ns
        {"ns": "common", "key": "nav.home", "value": "   "},             # blank value
        {"ns": "common", "key": "nav.home", "value": "x" * (MAX_VALUE_LENGTH + 1)},
    ],
)
@pytest.mark.asyncio
async def test_bad_payloads_are_rejected(
    client: AsyncClient,
    db_session: AsyncSession,
    account: Account,
    auth_headers: dict,
    body: dict,
):
    """Refused outright, never truncated."""
    await make_admin(db_session, account)

    resp = await client.put("/copy-overrides", json=body, headers=auth_headers)
    assert resp.status_code == 422
    assert (await db_session.execute(select(CopyOverride))).first() is None


@pytest.mark.asyncio
async def test_a_stale_base_is_refused_and_names_the_live_wording(
    client: AsyncClient,
    db_session: AsyncSession,
    account: Account,
    auth_headers: dict,
):
    """Two editors open the same line; the second save must not wipe the first."""
    await make_admin(db_session, account)
    line = {"ns": "common", "key": "nav.home"}

    first = await client.put(
        "/copy-overrides",
        json={**line, "value": "Hearth", "base": None},
        headers=auth_headers,
    )
    assert first.status_code == 200

    # Second editor opened the page before "Hearth" existed: base is still null.
    stale = await client.put(
        "/copy-overrides",
        json={**line, "value": "Den", "base": None},
        headers=auth_headers,
    )
    assert stale.status_code == 409
    detail = stale.json()["detail"]
    assert detail["code"] == "COPY_OVERRIDE_CHANGED"
    assert detail["params"] == {"current": "Hearth"}

    # Starting from what's live now, the save lands.
    fresh = await client.put(
        "/copy-overrides",
        json={**line, "value": "Den", "base": "Hearth"},
        headers=auth_headers,
    )
    assert fresh.status_code == 200
    assert fresh.json()["value"] == "Den"

    # A save that started from a reverted override sees null as the live wording.
    await client.delete("/copy-overrides?ns=common&key=nav.home", headers=auth_headers)
    after_revert = await client.put(
        "/copy-overrides",
        json={**line, "value": "Nest", "base": "Den"},
        headers=auth_headers,
    )
    assert after_revert.status_code == 409
    assert after_revert.json()["detail"]["params"] == {"current": None}


@pytest.mark.asyncio
async def test_a_base_that_is_not_the_live_wording_leaves_the_row_alone(
    client: AsyncClient,
    db_session: AsyncSession,
    account: Account,
    auth_headers: dict,
):
    """The row holds "Den"; an editor who last saw "Hearth" must not overwrite it."""
    await make_admin(db_session, account)
    line = {"ns": "common", "key": "nav.home"}
    db_session.add(CopyOverride(**line, value="Den", updated_by_id=account.id))
    await db_session.flush()

    resp = await client.put(
        "/copy-overrides",
        json={**line, "value": "Nest", "base": "Hearth"},
        headers=auth_headers,
    )
    assert resp.status_code == 409
    assert resp.json()["detail"]["params"] == {"current": "Den"}
    row = (await db_session.execute(select(CopyOverride))).scalar_one()
    await db_session.refresh(row)
    assert row.value == "Den"


@pytest.mark.asyncio
async def test_omitting_base_still_saves_unconditionally(
    client: AsyncClient,
    db_session: AsyncSession,
    account: Account,
    auth_headers: dict,
):
    """An editor bundle from before the guard keeps working through a deploy."""
    await make_admin(db_session, account)
    for value in ("Hearth", "Den"):
        resp = await client.put(
            "/copy-overrides",
            json={"ns": "common", "key": "nav.home", "value": value},
            headers=auth_headers,
        )
        assert resp.status_code == 200
    assert resp.json()["value"] == "Den"
