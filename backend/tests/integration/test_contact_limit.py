"""Per-IP limit and honeypot on the anonymous POST /contact."""
import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.contact import ContactMessage
from services import contact_limit


def _post(client: AsyncClient, ip: str, **extra):
    body = {"name": "Ada", "email": "a@example.com", "message": "Hi", **extra}
    return client.post("/contact", json=body, headers={"X-Forwarded-For": ip})


async def _rows(db_session: AsyncSession) -> list[ContactMessage]:
    return list((await db_session.execute(select(ContactMessage))).scalars().all())


@pytest.mark.asyncio
async def test_contact_rate_limited_per_ip(
    client: AsyncClient, db_session: AsyncSession
):
    contact_limit._hits.clear()
    for _ in range(5):
        assert (await _post(client, "9.9.9.9, 10.0.0.1")).status_code == 201
    over = await _post(client, "9.9.9.9")
    assert over.status_code == 429
    assert int(over.headers["Retry-After"]) > 0
    assert len(await _rows(db_session)) == 5
    assert (await _post(client, "8.8.8.8")).status_code == 201


@pytest.mark.asyncio
async def test_contact_honeypot_stores_nothing(
    client: AsyncClient, db_session: AsyncSession
):
    contact_limit._hits.clear()
    resp = await _post(client, "7.7.7.7", website="http://spam")
    assert resp.status_code == 201
    assert {"id", "created_at"} <= resp.json().keys()
    assert await _rows(db_session) == []


@pytest.mark.asyncio
async def test_contact_limit_keys_ipv6_by_slash_64(client: AsyncClient):
    contact_limit._hits.clear()
    for i in range(5):
        assert (await _post(client, f"2001:db8:1:2::{i + 1}")).status_code == 201
    assert (await _post(client, "2001:db8:1:2:ffff::9")).status_code == 429
    assert (await _post(client, "2001:db8:1:3::1")).status_code == 201


def test_contact_limit_drops_expired_entries(monkeypatch):
    contact_limit._hits.clear()
    contact_limit._hits["1.1.1.1"].append(0.0)
    monkeypatch.setattr(contact_limit.time, "monotonic", lambda: 10_000.0)
    client = type("C", (), {"host": "2.2.2.2"})()
    request = type("R", (), {"headers": {}, "client": client})()
    contact_limit.hit_contact_limit(request)
    assert "1.1.1.1" not in contact_limit._hits
