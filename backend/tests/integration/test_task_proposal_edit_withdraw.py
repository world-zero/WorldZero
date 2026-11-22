"""A proposer edits or withdraws their own pending proposal (#3771)."""
import re

import pytest
import pytest_asyncio
from fastapi import HTTPException
from httpx import AsyncClient
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from errors import ErrorCode
from game_config import CURRENT_ERA
from models.character import Character
from models.character_stats import CharacterStats
from models.mod_action import ModAction
from models.roles import Permission
from models.task import Task, TaskStatus
from schemas.admin import AdminTaskPatch
from schemas.task import TaskCreate
from services.admin_service import admin_edit_task, update_task_status
from services.task import edit_proposal, withdraw_proposal
from tests.integration.factories import make_task
from tests.integration.query_capture import capture_selects

BODY = {"title": "Better title", "point_value": 12, "level_required": 1}
BODY_MODEL = TaskCreate(**BODY)


@pytest_asyncio.fixture
async def proposer(db_session: AsyncSession, character: Character) -> Character:
    await db_session.execute(
        update(CharacterStats)
        .where(CharacterStats.character_id == character.id)
        .values(level=CURRENT_ERA.level_to_propose_task)
    )
    await db_session.commit()
    return character


async def _pending(db_session: AsyncSession, who: Character) -> Task:
    return await make_task(db_session, who, status=TaskStatus.pending, commit=True)


def _code(resp) -> str:
    return resp.json()["detail"]["code"]


@pytest.mark.asyncio
async def test_proposer_edits_every_field_without_restarting_the_window(
    client: AsyncClient, db_session: AsyncSession, proposer, auth_headers
):
    task = await _pending(db_session, proposer)
    created = task.created_at

    resp = await client.put(
        f"/tasks/{task.id}",
        json={**BODY, "description": "d", "notes": "n"},
        headers=auth_headers,
    )

    assert resp.status_code == 200
    await db_session.refresh(task)
    assert (task.title, task.description, task.notes, task.point_value) == (
        "Better title", "d", "n", 12,
    )
    assert task.status == TaskStatus.pending
    assert task.created_at == created


@pytest.mark.asyncio
async def test_edit_reruns_the_level_gate(
    client: AsyncClient, db_session: AsyncSession, proposer, auth_headers
):
    task = await _pending(db_session, proposer)

    resp = await client.put(
        f"/tasks/{task.id}",
        json={**BODY, "task_type": "metatask"},
        headers=auth_headers,
    )

    assert resp.status_code == 403
    assert _code(resp) == ErrorCode.metatask_proposal_level_too_low.value


@pytest.mark.asyncio
async def test_edit_refuses_another_character(
    client: AsyncClient, db_session: AsyncSession, proposer, character2, auth_headers2
):
    task = await _pending(db_session, proposer)

    for resp in (
        await client.put(f"/tasks/{task.id}", json=BODY, headers=auth_headers2),
        await client.delete(f"/tasks/{task.id}", headers=auth_headers2),
    ):
        assert resp.status_code == 403
        assert _code(resp) == ErrorCode.task_not_yours.value


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [TaskStatus.active, TaskStatus.deleted])
async def test_refused_once_no_longer_pending(
    client: AsyncClient, db_session: AsyncSession, proposer, auth_headers, status
):
    task = await _pending(db_session, proposer)
    task.status = status
    await db_session.commit()

    for resp in (
        await client.put(f"/tasks/{task.id}", json=BODY, headers=auth_headers),
        await client.delete(f"/tasks/{task.id}", headers=auth_headers),
    ):
        assert resp.status_code == 409
        assert _code(resp) == ErrorCode.task_not_pending.value


@pytest.mark.asyncio
async def test_withdraw_deletes_and_logs_with_the_proposer_as_actor(
    client: AsyncClient, db_session: AsyncSession, proposer, account, auth_headers
):
    task = await _pending(db_session, proposer)

    resp = await client.delete(f"/tasks/{task.id}", headers=auth_headers)

    assert resp.status_code == 204
    await db_session.refresh(task)
    assert task.status == TaskStatus.deleted
    rows = (await db_session.execute(select(ModAction))).scalars().all()
    logged = [(r.action, r.target_type, r.target_id, r.actor_account_id) for r in rows]
    assert logged == [("task_withdraw", "task", task.id, account.id)]


@pytest.mark.asyncio
async def test_proposer_reads_their_proposal_with_notes_and_nobody_else_does(
    client: AsyncClient,
    db_session: AsyncSession,
    proposer,
    auth_headers,
    character2,
    auth_headers2,
):
    task = await _pending(db_session, proposer)
    task.notes = "for the mods"
    await db_session.commit()

    mine = await client.get(f"/tasks/{task.id}/proposal", headers=auth_headers)
    theirs = await client.get(f"/tasks/{task.id}/proposal", headers=auth_headers2)

    assert mine.json()["notes"] == "for the mods"
    assert theirs.status_code == 403


# A second session on the same connection has its own identity map, so a stale
# cached copy shows up without needing real concurrent transactions.
async def _stale_session(db_session: AsyncSession, task: Task):
    other = AsyncSession(bind=db_session.bind, expire_on_commit=False)
    other.info["loaded"] = await other.get(Task, task.id)  # the identity map is weak
    return other


@pytest.mark.asyncio
@pytest.mark.parametrize("act", [edit_proposal, withdraw_proposal])
async def test_proposer_sees_a_mods_approval_made_after_they_loaded_it(
    db_session: AsyncSession, proposer, act
):
    task = await _pending(db_session, proposer)
    stale = await _stale_session(db_session, task)
    await update_task_status(
        task.id, TaskStatus.active, db_session,
        actor_id=proposer.account_id, held=frozenset({Permission.review_proposals}),
    )
    await db_session.commit()

    args = (BODY_MODEL,) if act is edit_proposal else ()
    with pytest.raises(HTTPException) as exc:
        await act(task.id, proposer, *args, stale)

    assert exc.value.status_code == 409
    assert exc.value.detail["code"] == ErrorCode.task_not_pending.value


@pytest.mark.asyncio
async def test_mod_approval_sees_a_withdrawal_made_after_they_loaded_it(
    db_session: AsyncSession, proposer
):
    task = await _pending(db_session, proposer)
    stale = await _stale_session(db_session, task)
    await withdraw_proposal(task.id, proposer, db_session)
    await db_session.commit()

    with pytest.raises(HTTPException) as exc:
        await update_task_status(
            task.id, TaskStatus.active, stale,
            actor_id=proposer.account_id,
            held=frozenset({Permission.review_proposals}),
        )

    # Seen as deleted, leaving it needs a different permission than pending does.
    assert exc.value.status_code == 403


def _assert_row_locked(sql: list[str]) -> None:
    assert any(
        re.search(r"FROM task\b", statement) and "FOR UPDATE" in statement
        for statement in sql
    ), sql


@pytest.mark.asyncio
async def test_the_writers_lock_the_task_row(db_session: AsyncSession, proposer):
    held = frozenset({Permission.review_proposals, Permission.manage_tasks})
    for call in (
        lambda task: edit_proposal(task.id, proposer, BODY_MODEL, db_session),
        lambda task: update_task_status(
            task.id, TaskStatus.active, db_session,
            actor_id=proposer.account_id, held=held,
        ),
        lambda task: admin_edit_task(
            task.id, AdminTaskPatch(title="Edited"), db_session, proposer.account_id
        ),
        lambda task: withdraw_proposal(task.id, proposer, db_session),
    ):
        task = await _pending(db_session, proposer)
        with capture_selects() as sql:
            await call(task)
        _assert_row_locked(sql)


@pytest.mark.asyncio
async def test_mod_edit_sees_an_activation_made_after_they_loaded_it(
    db_session: AsyncSession, proposer
):
    task = await _pending(db_session, proposer)
    stale = await _stale_session(db_session, task)
    await update_task_status(
        task.id, TaskStatus.active, db_session,
        actor_id=proposer.account_id, held=frozenset({Permission.review_proposals}),
    )
    await db_session.commit()

    with pytest.raises(HTTPException) as exc:
        await admin_edit_task(
            task.id, AdminTaskPatch(title="Edited"), stale, proposer.account_id
        )

    assert exc.value.status_code == 400
