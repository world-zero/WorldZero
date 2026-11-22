"""The owner-only admin roster (#3258)."""
import dependencies
import pytest
from httpx import AsyncClient
from sqlalchemy import select

from models.account import Account, AccountStatus
from models.mod_action import ModAction
from models.roles import Permission
from tests.integration.factories import make_admin, make_owner


@pytest.fixture
def hdr(auth_headers: dict) -> dict:
    return auth_headers


@pytest.fixture
def hdr2(auth_headers2: dict) -> dict:
    return auth_headers2


@pytest.fixture
def other(character2):
    return character2


@pytest.fixture
def owner_is_account(account: Account) -> Account:
    return account


async def test_is_owner_only_for_the_account_holding_the_owner_role(
    client, db_session, account, account2, character, other,
    hdr, hdr2, owner_is_account,
):
    me = await client.get("/auth/me", headers=hdr)
    assert me.json()["is_owner"] is False
    await make_owner(db_session, account)
    me = await client.get("/auth/me", headers=hdr)
    assert me.json()["is_owner"] is True
    plain = await client.get("/auth/me", headers=hdr2)
    assert plain.json()["is_owner"] is False


PUT_URL = "/admin/admins/{}/permissions/{}"
ON = {"on": True}
OFF = {"on": False}


async def test_non_owner_admin_gets_403_on_all_three_routes(
    client: AsyncClient, db_session, account2, other, hdr2, owner_is_account,
):
    await make_admin(db_session, account2)
    assert (await client.get("/admin/admins", headers=hdr2)).status_code == 403
    r = await client.put(PUT_URL.format("x", "edit_copy"), json=ON, headers=hdr2)
    assert r.status_code == 403
    assert (await client.delete("/admin/admins/x", headers=hdr2)).status_code == 403


async def test_owner_lists_grants_and_revokes(
    client, db_session, account, character, other, hdr, owner_is_account
):
    await make_owner(db_session, account)

    listed = (await client.get("/admin/admins", headers=hdr)).json()
    assert listed == [
        {
            "username": character.username,
            "display_name": character.display_name,
            "is_owner": True,
            "suspended": False,
            "permissions": [],
        }
    ]

    url = PUT_URL.format(other.username, "edit_copy")
    assert (await client.put(url, json=ON, headers=hdr)).status_code == 204
    rows = (await client.get("/admin/admins", headers=hdr)).json()
    assert [r["permissions"] for r in rows] == [[], ["edit_copy"]]
    assert {"account_id", "email"}.isdisjoint(rows[1])

    assert (await client.put(url, json=OFF, headers=hdr)).status_code == 204
    assert len((await client.get("/admin/admins", headers=hdr)).json()) == 1


async def test_grant_and_revoke_write_mod_log_lines(
    client, db_session, account, other, hdr, owner_is_account
):
    await make_owner(db_session, account)
    url = PUT_URL.format(other.username, "roll_era")
    await client.put(url, json=ON, headers=hdr)
    await client.put(url, json=ON, headers=hdr)  # idempotent: no second line
    await client.put(url, json=OFF, headers=hdr)

    lines = (
        await db_session.execute(select(ModAction).order_by(ModAction.id))
    ).scalars().all()
    assert [
        (m.actor_account_id, m.action, m.target_id, m.detail) for m in lines
    ] == [
        (account.id, "permission_grant", other.account_id, "roll_era"),
        (account.id, "permission_revoke", other.account_id, "roll_era"),
    ]


async def test_suspended_holder_stays_on_the_roster_marked(
    client, db_session, account, character, account2, other, hdr, owner_is_account
):
    await make_owner(db_session, account)
    account2.status = AccountStatus.suspended
    await db_session.commit()
    url = PUT_URL.format(other.username, "ban_suspend")
    r = await client.put(url, json=ON, headers=hdr)
    assert r.status_code == 204, r.text

    rows = (await client.get("/admin/admins", headers=hdr)).json()
    assert [(r["username"], r["suspended"]) for r in rows] == [
        (character.username, False),
        (other.username, True),
    ]


def code(response) -> str:
    return response.json()["detail"]["code"]


async def test_refusals_carry_their_codes(
    client, db_session, account, character, other, hdr, owner_is_account
):
    await make_owner(db_session, account)

    r = await client.delete(f"/admin/admins/{character.username}", headers=hdr)
    assert (r.status_code, code(r)) == (409, "ADMIN_CANNOT_REVOKE_OWNER")
    url = PUT_URL.format(character.username, "edit_copy")
    r = await client.put(url, json=OFF, headers=hdr)
    assert (r.status_code, code(r)) == (409, "ADMIN_CANNOT_REVOKE_OWNER")

    url = PUT_URL.format("nobody-here", "edit_copy")
    r = await client.put(url, json=ON, headers=hdr)
    assert (r.status_code, code(r)) == (404, "ADMIN_UNKNOWN_USERNAME")
    r = await client.delete("/admin/admins/nobody-here", headers=hdr)
    assert (r.status_code, code(r)) == (404, "ADMIN_UNKNOWN_USERNAME")
    r = await client.put(PUT_URL.format(other.username, "nope"), json=ON, headers=hdr)
    assert r.status_code == 422

    r = await client.delete(f"/admin/admins/{other.username}", headers=hdr)
    assert (r.status_code, code(r)) == (404, "ADMIN_NOT_AN_ADMIN")


async def test_a_deleted_account_cannot_be_granted_and_is_off_the_roster(
    client, db_session, account, account2, character, other, hdr, owner_is_account,
):
    await make_owner(db_session, account)
    r = await client.put(PUT_URL.format(other.username, "edit_copy"), json=ON, headers=hdr)
    assert r.status_code == 204
    account2.status = AccountStatus.deleted
    await db_session.commit()
    names = [a["username"] for a in (await client.get("/admin/admins", headers=hdr)).json()]
    assert other.username not in names

    r = await client.put(PUT_URL.format(other.username, "read_messages"), json=ON, headers=hdr)
    assert (r.status_code, r.json()["detail"]["code"]) == (409, "ACCOUNT_DELETED")
    held = await dependencies.account_permissions(account2.id, db_session)
    assert held == {Permission.edit_copy}
    r = await client.put(PUT_URL.format(other.username, "edit_copy"), json=OFF, headers=hdr)
    assert r.status_code == 204
