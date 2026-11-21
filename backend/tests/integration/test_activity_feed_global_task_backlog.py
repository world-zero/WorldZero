"""#2225: a task that predates the character is not news to that character.

Seam: ``_global_tasks_query``. Scoped to the CHARACTER, not the account. No
"N most recent" cap, and there must not be one. ADR-0036: badges are COUNT over
the same windowed Select, so suppressed rows take their number with them.
"""

from datetime import datetime, timedelta

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from models.account import Account
from models.character import Character
from models.character_stats import CharacterStats
from models.era import Era
from models.task import Task, TaskStatus
from tests.integration.factories import DEFAULT_FACTION_SLUG, make_admin


async def _make_task(
    db_session: AsyncSession, character: Character, title: str, created_at
) -> Task:
    task = Task(
        title=title,
        description="news, or not",
        point_value=10,
        level_required=0,
        status=TaskStatus.active,
        created_by_id=character.id,
        primary_faction_slug=DEFAULT_FACTION_SLUG,
        created_at=created_at,
        activated_at=created_at,
    )
    db_session.add(task)
    await db_session.commit()
    await db_session.refresh(task)
    return task


async def _global_feed(client: AsyncClient, auth_headers: dict) -> dict:
    response = await client.get(
        "/activity-feed",
        params={"filter": "global", "limit": 100},
        headers=auth_headers,
    )
    assert response.status_code == 200, response.text
    return response.json()


def _task_ids(body: dict) -> set[int]:
    return {
        item["payload"]["task_id"]
        for item in body["items"]
        if item["type"] == "global_task"
    }


@pytest_asyncio.fixture
async def board(db_session: AsyncSession, character: Character) -> tuple[Task, Task]:
    born = character.created_at
    old = await _make_task(db_session, character, "Already on the board", born - timedelta(days=1))
    new = await _make_task(db_session, character, "Filed this morning", born + timedelta(minutes=1))
    return old, new


@pytest.mark.asyncio
async def test_a_task_older_than_the_character_is_not_announced_to_them(
    client: AsyncClient,
    character: Character,
    board: tuple[Task, Task],
    auth_headers: dict,
):
    old, new = board
    body = await _global_feed(client, auth_headers)
    ids = _task_ids(body)

    assert new.id in ids, f"a task filed after the character is news; got {ids}"
    assert old.id not in ids, (
        "a task that was already on the board when this character was made is "
        f"not news to them; got {ids}"
    )
    assert body["counts"]["by_type"].get("global_task") == 1, body["counts"]


@pytest.mark.asyncio
async def test_a_task_created_the_same_instant_still_counts_as_news(
    client: AsyncClient,
    db_session: AsyncSession,
    character: Character,
    auth_headers: dict,
):
    """The boundary is ``>=``: Postgres ``now()`` is the transaction timestamp, so a
    character and task written in one transaction share a stamp.
    """
    same_instant = await _make_task(
        db_session, character, "Born together", character.created_at
    )
    assert same_instant.id in _task_ids(await _global_feed(client, auth_headers))


@pytest.mark.asyncio
async def test_a_second_character_on_an_old_account_starts_clean(
    client: AsyncClient,
    db_session: AsyncSession,
    account: Account,
    character: Character,
    era: Era,
    board: tuple[Task, Task],
    auth_headers: dict,
):
    """Same account and token, a newer character: the character's age decides."""
    old, new = board
    second = Character(
        account_id=account.id,
        username="secondlife",
        display_name="Second Life",
        faction_slug=DEFAULT_FACTION_SLUG,
        created_at=new.created_at + timedelta(minutes=1),
    )
    db_session.add(second)
    await db_session.flush()
    db_session.add(
        CharacterStats(
            character_id=second.id,
            era_id=era.id,
            score=0,
            level=0,
            votes_spent_this_era=0,
        )
    )
    account.active_character_id = second.id
    await db_session.commit()

    ids = _task_ids(await _global_feed(client, auth_headers))
    assert ids == set(), (
        "a second character on an existing account starts clean for the same "
        f"reason the first one did; got {ids}"
    )


async def _set_status(client, auth_headers, task_id: int, status: str) -> None:
    resp = await client.put(
        f"/admin/tasks/{task_id}/status", json={"status": status}, headers=auth_headers
    )
    assert resp.status_code == 200, resp.text


def _global_items(body: dict) -> list[dict]:
    return [i for i in body["items"] if i["type"] == "global_task"]


def _pending(character: Character, title: str, created_at) -> Task:
    return Task(
        title=title,
        point_value=10,
        level_required=0,
        status=TaskStatus.pending,
        created_by_id=character.id,
        primary_faction_slug=DEFAULT_FACTION_SLUG,
        created_at=created_at,
    )


@pytest.mark.asyncio
async def test_a_proposal_is_announced_when_approved_not_when_proposed(
    client: AsyncClient,
    db_session: AsyncSession,
    account: Account,
    character: Character,
    auth_headers: dict,
):
    """#3775: stamped on the approval, not the proposal."""
    await make_admin(db_session, account)
    proposed = character.created_at
    task = _pending(character, "Proposed long ago", proposed)
    db_session.add(task)
    await db_session.commit()
    assert _global_items(await _global_feed(client, auth_headers)) == []

    await _set_status(client, auth_headers, task.id, "active")
    items = _global_items(await _global_feed(client, auth_headers))
    await db_session.refresh(task)
    assert [i["payload"]["task_id"] for i in items] == [task.id]
    assert task.activated_at > proposed
    assert datetime.fromisoformat(items[0]["timestamp"]) == task.activated_at


@pytest.mark.asyncio
async def test_a_task_proposed_before_the_character_but_approved_after_is_news(
    client: AsyncClient,
    db_session: AsyncSession,
    account: Account,
    character: Character,
    auth_headers: dict,
):
    await make_admin(db_session, account)
    task = _pending(
        character, "Pending when they joined", character.created_at - timedelta(days=3)
    )
    db_session.add(task)
    await db_session.commit()

    await _set_status(client, auth_headers, task.id, "active")
    assert task.id in _task_ids(await _global_feed(client, auth_headers))


@pytest.mark.asyncio
async def test_retire_then_reactivate_is_not_announced_again(
    client: AsyncClient,
    db_session: AsyncSession,
    account: Account,
    character: Character,
    auth_headers: dict,
):
    await make_admin(db_session, account)
    task = _pending(character, "Back and forth", character.created_at)
    db_session.add(task)
    await db_session.commit()
    await _set_status(client, auth_headers, task.id, "active")
    await db_session.refresh(task)
    first = task.activated_at

    await _set_status(client, auth_headers, task.id, "retired")
    await _set_status(client, auth_headers, task.id, "active")
    await db_session.refresh(task)
    assert task.activated_at == first
    items = _global_items(await _global_feed(client, auth_headers))
    assert len(items) == 1
    assert datetime.fromisoformat(items[0]["timestamp"]) == first


@pytest.mark.asyncio
async def test_a_late_approval_sits_above_what_went_live_meanwhile(
    client: AsyncClient,
    db_session: AsyncSession,
    account: Account,
    character: Character,
    auth_headers: dict,
):
    await make_admin(db_session, account)
    early = await _make_task(
        db_session, character, "Went live meanwhile", character.created_at
    )
    late = _pending(character, "Approved last", character.created_at)
    db_session.add(late)
    await db_session.commit()
    await _set_status(client, auth_headers, late.id, "active")

    items = _global_items(await _global_feed(client, auth_headers))
    assert [i["payload"]["task_id"] for i in items] == [late.id, early.id]
