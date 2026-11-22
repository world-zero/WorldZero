"""Anyone who can see a task can comment on it (#4151); deleted/backdoor stay closed."""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from errors import ErrorCode
from game_config import CURRENT_ERA
from models.era import Era
from models.faction import Faction
from models.task import TaskStatus
from tests.integration.factories import DEFAULT_FACTION_SLUG
from tests.integration.test_task_visibility_gates import (
    FRESH_AGE,
    RIPE_AGE,
    _gated_task,
    _set_level_and_faction,
)

COMMENT_LEVEL = CURRENT_ERA.comment_level_required


async def _commenter(session: AsyncSession, character, era: Era) -> None:
    await _set_level_and_faction(
        session,
        character,
        era,
        COMMENT_LEVEL,
        DEFAULT_FACTION_SLUG,
    )


async def _comment(client: AsyncClient, task_id: int, headers: dict):
    return await client.post(
        f"/tasks/{task_id}/comments", json={"body_text": "I want this"}, headers=headers
    )


@pytest.mark.asyncio
async def test_a_viewer_of_a_pending_task_can_comment(
    client: AsyncClient,
    character,
    character2,
    era: Era,
    some_faction: Faction,
    auth_headers: dict,
    db_session: AsyncSession,
):
    task = await _gated_task(db_session, character2, TaskStatus.pending, RIPE_AGE)
    await _set_level_and_faction(
        db_session,
        character,
        era,
        max(CURRENT_ERA.level_to_see_pending_tasks, COMMENT_LEVEL),
        DEFAULT_FACTION_SLUG,
    )
    assert (await _comment(client, task.id, auth_headers)).status_code == 201


@pytest.mark.asyncio
async def test_the_author_can_comment_on_their_own_fresh_pending_task(
    client: AsyncClient,
    character,
    era: Era,
    some_faction: Faction,
    auth_headers: dict,
    db_session: AsyncSession,
):
    await _commenter(db_session, character, era)
    task = await _gated_task(db_session, character, TaskStatus.pending, FRESH_AGE)
    assert (await _comment(client, task.id, auth_headers)).status_code == 201


@pytest.mark.asyncio
async def test_a_player_outside_the_pending_window_gets_404(
    client: AsyncClient,
    character,
    character2,
    era: Era,
    some_faction: Faction,
    auth_headers: dict,
    db_session: AsyncSession,
):
    task = await _gated_task(db_session, character2, TaskStatus.pending, FRESH_AGE)
    await _set_level_and_faction(
        db_session,
        character,
        era,
        max(CURRENT_ERA.level_to_see_pending_tasks, COMMENT_LEVEL),
        DEFAULT_FACTION_SLUG,
    )
    r = await _comment(client, task.id, auth_headers)
    assert r.status_code == 404
    assert r.json()["detail"]["code"] == ErrorCode.task_not_found.value


@pytest.mark.asyncio
async def test_any_viewer_of_a_retired_task_can_comment(
    client: AsyncClient,
    character,
    character2,
    era: Era,
    some_faction: Faction,
    auth_headers: dict,
    db_session: AsyncSession,
):
    await _commenter(db_session, character, era)
    task = await _gated_task(db_session, character2, TaskStatus.retired)
    assert (await _comment(client, task.id, auth_headers)).status_code == 201


async def _assert_same_as_missing(client, task_id, auth_headers):
    gone = await _comment(client, 999_999_999, auth_headers)
    r = await _comment(client, task_id, auth_headers)
    assert gone.status_code == 404
    assert (r.status_code, r.json()) == (gone.status_code, gone.json())


@pytest.mark.asyncio
async def test_a_deleted_task_is_indistinguishable_from_missing(
    client: AsyncClient,
    character,
    era: Era,
    some_faction: Faction,
    auth_headers: dict,
    db_session: AsyncSession,
):
    await _commenter(db_session, character, era)
    task = await _gated_task(db_session, character, TaskStatus.deleted)
    await _assert_same_as_missing(client, task.id, auth_headers)


@pytest.mark.asyncio
async def test_a_backdoor_the_viewer_cannot_see_is_indistinguishable_from_missing(
    client: AsyncClient,
    character,
    character2,
    era: Era,
    some_faction: Faction,
    auth_headers: dict,
    db_session: AsyncSession,
):
    await _commenter(db_session, character, era)
    task = await _gated_task(db_session, character2, TaskStatus.backdoor)
    await _assert_same_as_missing(client, task.id, auth_headers)
