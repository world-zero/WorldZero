"""Per-admin permissions and the admin-on-admin guard (#3847, #3821)."""
import re

import pytest

import dependencies
from models.account import AccountStatus
from models.roles import Permission
from models.task import TaskStatus
from routers import admin
from tests.integration.factories import make_admin, make_owner, make_task
from tests.unit.test_admin_routes_declare_a_permission import required_permissions

pytestmark = pytest.mark.asyncio

REFUSED = (403, "ADMIN_PERMISSION_REQUIRED")


def code(response) -> str:
    return response.json()["detail"]["code"]


def outcome(response) -> tuple[int, str]:
    return response.status_code, code(response)


async def suspend(client, target_id: int, headers: dict, suspended: bool = True):
    return await client.post(
        f"/admin/accounts/{target_id}/suspend",
        json={"suspended": suspended},
        headers=headers,
    )


async def test_one_permission_opens_only_its_routes(
    client, db_session, account, auth_headers
):
    await make_admin(db_session, account, permissions=[Permission.handle_reports])
    flagged = await client.get("/admin/praxes/flagged", headers=auth_headers)
    overview = await client.get("/admin/overview", headers=auth_headers)
    assert (flagged.status_code, overview.status_code) == (200, 200)

    not_refused = []
    for route in admin.router.routes:
        required = required_permissions(route)
        if required is None or Permission.handle_reports in required:
            continue
        url = "/admin" + re.sub(r"\{[^}]+\}", "1", route.path)
        for method in route.methods:
            response = await client.request(method, url, headers=auth_headers)
            if outcome(response) != REFUSED:
                not_refused.append((method, url, response.status_code))
    assert not not_refused


async def test_admin_is_owner_or_any_permission(db_session, account, account2):
    assert not await dependencies.account_has_admin_role(account.id, db_session)
    await make_admin(db_session, account, permissions=[Permission.edit_copy])
    assert await dependencies.account_has_admin_role(account.id, db_session)
    held = await dependencies.account_permissions(account.id, db_session)
    assert held == {Permission.edit_copy}
    await make_owner(db_session, account2)
    held = await dependencies.account_permissions(account2.id, db_session)
    assert held == set(Permission)


async def test_a_non_owner_admin_cannot_suspend_another_admin(
    client, db_session, account, account2, auth_headers
):
    await make_admin(db_session, account)
    await make_admin(db_session, account2)
    r = await suspend(client, account2.id, auth_headers)
    assert outcome(r) == (403, "ADMIN_TARGET_NEEDS_OWNER")


async def test_the_owner_can_suspend_an_admin(
    client, db_session, account, account2, auth_headers
):
    await make_owner(db_session, account)
    await make_admin(db_session, account2)
    r = await suspend(client, account2.id, auth_headers)
    assert r.status_code == 200
    assert r.json()["status"] == AccountStatus.suspended.value


async def test_nobody_suspends_an_owner_but_unsuspend_still_works(
    client, db_session, account, account2, auth_headers2
):
    await make_owner(db_session, account)
    await make_owner(db_session, account2)
    r = await suspend(client, account.id, auth_headers2)
    assert outcome(r) == (409, "ADMIN_CANNOT_TARGET_OWNER")
    await db_session.refresh(account)
    assert account.status == AccountStatus.active

    account.status = AccountStatus.suspended
    await db_session.commit()
    r = await suspend(client, account.id, auth_headers2, suspended=False)
    assert r.status_code == 200


async def test_nobody_targets_themselves(client, db_session, account, auth_headers):
    await make_admin(db_session, account)
    r = await suspend(client, account.id, auth_headers)
    assert outcome(r) == (409, "ADMIN_CANNOT_TARGET_SELF")


async def test_the_ban_door_has_the_same_guard(
    client, db_session, account, account2, character2, auth_headers
):
    await make_admin(db_session, account)
    await make_owner(db_session, account2)
    r = await client.post(
        f"/admin/characters/{character2.id}/ban",
        json={"banned": True},
        headers=auth_headers,
    )
    assert outcome(r) == (409, "ADMIN_CANNOT_TARGET_OWNER")


async def test_the_stats_route_is_gone(
    client, db_session, account, character, auth_headers
):
    await make_owner(db_session, account)
    r = await client.patch(
        f"/admin/characters/{character.id}/stats",
        json={"score": 5},
        headers=auth_headers,
    )
    assert r.status_code in (404, 405)


async def test_task_status_needs_the_box_for_its_transition(
    client, db_session, account, character, auth_headers
):
    proposal = await make_task(
        db_session, character, status=TaskStatus.pending, commit=True
    )
    await make_admin(db_session, account, permissions=[Permission.manage_tasks])
    url = f"/admin/tasks/{proposal.id}/status"
    r = await client.put(url, json={"status": "active"}, headers=auth_headers)
    assert outcome(r) == REFUSED

    await make_admin(db_session, account, permissions=[Permission.review_proposals])
    for status, expected in (("active", 200), ("retired", 200), ("deleted", 403)):
        r = await client.put(url, json={"status": status}, headers=auth_headers)
        assert r.status_code == expected, (status, r.text)


P = TaskStatus
RP, MT, DT = Permission.review_proposals, Permission.manage_tasks, Permission.delete_import_tasks


@pytest.mark.parametrize(
    ("held", "start", "target", "expected"),
    [
        ([RP], P.pending, "backdoor", 403),
        ([RP], P.pending, "deleted", 403),
        ([RP], P.pending, "active", 200),
        ([RP], P.pending, "retired", 200),
        ([MT], P.pending, "backdoor", 403),
        ([MT, RP], P.pending, "backdoor", 200),
        ([DT], P.pending, "deleted", 200),
        ([DT], P.deleted, "pending", 200),
        ([RP], P.deleted, "pending", 403),
        ([MT], P.active, "retired", 200),
        ([RP], P.active, "retired", 403),
    ],
)
async def test_task_status_permission_follows_the_pair(
    client, db_session, account, character, auth_headers, held, start, target, expected
):
    task = await make_task(db_session, character, status=start, commit=True)
    await make_admin(db_session, account, permissions=held)
    r = await client.put(
        f"/admin/tasks/{task.id}/status", json={"status": target}, headers=auth_headers
    )
    assert r.status_code == expected, r.text
    if expected == 403:
        assert code(r) == "ADMIN_PERMISSION_REQUIRED"


async def test_me_carries_the_permissions_the_client_gates_on(
    client, db_session, account, auth_headers
):
    me = await client.get("/auth/me", headers=auth_headers)
    assert me.json()["permissions"] == []
    await make_admin(db_session, account, permissions=[Permission.handle_reports])
    me = await client.get("/auth/me", headers=auth_headers)
    body = me.json()
    assert (body["permissions"], body["is_owner"]) == (["handle_reports"], False)
    await make_owner(db_session, account)
    me = await client.get("/auth/me", headers=auth_headers)
    assert me.json()["permissions"] == [p.value for p in Permission]
