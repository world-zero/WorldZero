"""A mod ban outlives account deletion for the tombstone's 90 days (ADR-0081, #3929)."""
from datetime import datetime, timedelta, timezone

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from errors import ErrorCode
from models.account import Account, AccountTombstone, AuthProvider, OAuthProvider
from models.character import CharacterStatus
from services.account_deletion import TOMBSTONE_RETENTION_DAYS, delete_account
from services.character import load_account_eligibility
from tests.integration.factories import make_character
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
