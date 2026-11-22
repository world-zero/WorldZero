"""A mod ban outlives account deletion for the tombstone's 90 days (ADR-0081, #3929)."""
from datetime import datetime, timedelta, timezone

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from errors import ErrorCode
from models.account import Account, AccountTombstone, AuthProvider, OAuthProvider
from models.character import CharacterStatus
from models.roles import Permission
from services.account_deletion import TOMBSTONE_RETENTION_DAYS, delete_account
from services.character import load_account_eligibility
from tests.integration.factories import make_admin, make_character
from tests.integration.query_capture import capture_selects
from tests.integration.test_returning_player_gate import (
    _RETURNING_EMAIL,
    _SUB,
    _stub_google,
)

_GOOGLE = AuthProvider.GOOGLE


async def _delete_then_sign_back_in(
    client, db_session, monkeypatch, era, *, banned: bool
) -> Account:
    old = Account(email="before@example.com")
    db_session.add(old)
    await db_session.flush()
    db_session.add(
        OAuthProvider(account_id=old.id, provider=_GOOGLE, provider_user_id=_SUB)
    )
    life = await make_character(db_session, era, username="evader", account=old)
    if banned:
        life.status = CharacterStatus.banned
    await db_session.flush()
    await delete_account(old.id, db_session, era)
    tombstone = (await db_session.execute(select(AccountTombstone))).scalar_one()
    assert tombstone.mod_banned is banned
    await db_session.commit()

    _stub_google(monkeypatch)
    await client.get("/auth/google/callback")
    assert (await client.post("/auth/returning-player")).status_code == 200
    return (
        await db_session.execute(
            select(Account).where(Account.email == _RETURNING_EMAIL)
        )
    ).scalar_one()


@pytest.mark.asyncio
async def test_a_banned_player_who_deletes_and_returns_still_cannot_create(
    client: AsyncClient, db_session: AsyncSession, monkeypatch, era, some_faction
) -> None:
    fresh = await _delete_then_sign_back_in(
        client, db_session, monkeypatch, era, banned=True
    )

    eligibility = await load_account_eligibility(fresh.id, era.id, db_session)
    assert eligibility.character_creation_banned is True
    resp = await client.post("/characters", json={"display_name": "Again"})
    assert resp.status_code == 403
    assert resp.json()["detail"]["code"] == ErrorCode.character_creation_banned.value


@pytest.mark.asyncio
async def test_the_ban_carries_through_a_second_deletion(
    client: AsyncClient, db_session: AsyncSession, monkeypatch, era, some_faction
) -> None:
    fresh = await _delete_then_sign_back_in(
        client, db_session, monkeypatch, era, banned=True
    )
    await delete_account(fresh.id, db_session, era)
    tombstone = (await db_session.execute(select(AccountTombstone))).scalar_one()
    assert tombstone.mod_banned is True


@pytest.mark.asyncio
async def test_an_unbanned_player_who_deletes_and_returns_can_create(
    client: AsyncClient, db_session: AsyncSession, monkeypatch, era, some_faction
) -> None:
    await _delete_then_sign_back_in(client, db_session, monkeypatch, era, banned=False)

    resp = await client.post("/characters", json={"display_name": "Again"})
    assert resp.status_code == 201


@pytest.mark.asyncio
async def test_the_ban_expires_with_the_tombstone(
    client: AsyncClient, db_session: AsyncSession, monkeypatch, era, some_faction
) -> None:
    fresh = await _delete_then_sign_back_in(
        client, db_session, monkeypatch, era, banned=True
    )
    tombstone = (await db_session.execute(select(AccountTombstone))).scalar_one()
    tombstone.created_at = datetime.now(timezone.utc) - timedelta(
        days=TOMBSTONE_RETENTION_DAYS + 1
    )
    await db_session.commit()

    eligibility = await load_account_eligibility(fresh.id, era.id, db_session)
    assert eligibility.character_creation_banned is False


@pytest.mark.asyncio
async def test_a_mod_clears_the_carried_ban_and_the_player_can_create(
    client: AsyncClient, db_session: AsyncSession, monkeypatch, era, some_faction,
    account, auth_headers,
) -> None:
    await make_admin(db_session, account, permissions=[Permission.ban_suspend])
    fresh = await _delete_then_sign_back_in(
        client, db_session, monkeypatch, era, banned=True
    )
    people = (await client.get("/admin/characters", headers=auth_headers)).json()
    banned_row = next(p for p in people if p["status"] == "banned")
    assert banned_row["carried_ban_until"] is not None
    assert banned_row["account_id"] != fresh.id

    resp = await client.post(
        f"/admin/accounts/{banned_row['account_id']}/clear-carried-ban",
        headers=auth_headers,
    )
    assert resp.status_code == 200
    created = await client.post("/characters", json={"display_name": "Again"})
    assert created.status_code == 201
    people = (await client.get("/admin/characters", headers=auth_headers)).json()
    assert all(p["carried_ban_until"] is None for p in people)


@pytest.mark.asyncio
async def test_clearing_a_carried_ban_needs_the_ban_permission(
    client: AsyncClient, db_session: AsyncSession, account, auth_headers
) -> None:
    await make_admin(db_session, account, permissions=[Permission.handle_reports])
    resp = await client.post(
        "/admin/accounts/1/clear-carried-ban", headers=auth_headers
    )
    assert (resp.status_code, resp.json()["detail"]["code"]) == (
        403,
        "ADMIN_PERMISSION_REQUIRED",
    )


async def _tombstoned(db_session, era, n: int, tag: str) -> None:
    for i in range(n):
        old = Account(email=f"{tag}{i}@example.com")
        db_session.add(old)
        await db_session.flush()
        db_session.add(
            AccountTombstone(
                account_id=old.id,
                provider=_GOOGLE,
                provider_user_hash=f"{tag}{i}",
                mod_banned=True,
            )
        )
        await make_character(db_session, era, username=f"{tag}{i}", account=old)
    await db_session.commit()


@pytest.mark.asyncio
async def test_the_admin_roster_resolves_carried_bans_in_a_fixed_query_count(
    client: AsyncClient, db_session: AsyncSession, era, some_faction, account,
    auth_headers,
) -> None:
    await make_admin(db_session, account, permissions=[Permission.ban_suspend])

    async def selects() -> tuple[int, list]:
        with capture_selects() as seen:
            resp = await client.get("/admin/characters", headers=auth_headers)
        assert resp.status_code == 200
        return len(seen), resp.json()

    await _tombstoned(db_session, era, 2, "few")
    few, rows = await selects()
    await _tombstoned(db_session, era, 5, "many")
    many, rows = await selects()

    assert sum(r["carried_ban_until"] is not None for r in rows) == 7
    assert many == few
