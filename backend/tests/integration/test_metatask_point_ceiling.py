"""An unreviewed or over-priced metatask can't mint points (#3918)."""
import pytest
from httpx import AsyncClient
from sqlalchemy import update

from game_config import CURRENT_ERA
from models.character_stats import CharacterStats
from models.meta_task import PraxisMetaTask
from models.praxis import PraxisStatus
from models.task import TaskStatus, TaskType
from services.meta_task import get_meta_task_points_bulk
from tests.integration.factories import make_character, make_solo_praxis, make_task

CAP = CURRENT_ERA.proposed_task_points_max


async def _setup(db_session, account2, era, some_faction, status):
    author = await make_character(
        db_session, era, username="sealer", account=account2,
        level=CURRENT_ERA.metatask_apply_level,
    )
    task = await make_task(db_session, author)
    meta = await make_task(
        db_session, author, title="m", point_value=100,
        task_type=TaskType.metatask, status=status,
    )
    praxis = await make_solo_praxis(
        db_session, task, author, status=PraxisStatus.in_progress
    )
    await db_session.commit()
    return praxis, meta


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "status", [TaskStatus.pending, TaskStatus.retired, TaskStatus.deleted]
)
async def test_only_an_active_metatask_attaches(
    client, db_session, account2, era, some_faction, auth_headers2, status
):
    praxis, meta = await _setup(db_session, account2, era, some_faction, status)

    resp = await client.post(
        f"/praxes/{praxis.id}/metatasks",
        json={"task_id": meta.id},
        headers=auth_headers2,
    )

    assert resp.status_code == 404
    assert resp.json()["detail"]["code"] == "TASK_NOT_FOUND"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "status,paid",
    [
        (TaskStatus.active, 100),
        (TaskStatus.retired, 100),
        (TaskStatus.pending, 0),
        (TaskStatus.deleted, 0),
    ],
)
async def test_only_active_or_retired_metatasks_pay(
    db_session, account2, era, some_faction, status, paid
):
    praxis, meta = await _setup(db_session, account2, era, some_faction, status)
    db_session.add(PraxisMetaTask(praxis_id=praxis.id, task_id=meta.id))
    await db_session.commit()

    totals = await get_meta_task_points_bulk([praxis.id], db_session)

    assert totals.get(praxis.id, 0) == paid


@pytest.mark.asyncio
@pytest.mark.parametrize("points,expected", [(CAP, 201), (CAP + 1, 422)])
async def test_proposal_points_are_capped(
    client: AsyncClient, db_session, character, auth_headers, points, expected
):
    await db_session.execute(
        update(CharacterStats)
        .where(CharacterStats.character_id == character.id)
        .values(level=CURRENT_ERA.level_to_propose_task)
    )
    await db_session.commit()
    body = {"title": "t", "point_value": points, "level_required": 1}

    resp = await client.post("/tasks", json=body, headers=auth_headers)

    assert resp.status_code == expected
    if expected == 422:
        assert resp.json()["detail"]["code"] == "TASK_POINTS_TOO_HIGH"


@pytest.mark.asyncio
async def test_proposal_edit_is_capped(
    client: AsyncClient, db_session, character, auth_headers
):
    await db_session.execute(
        update(CharacterStats)
        .where(CharacterStats.character_id == character.id)
        .values(level=CURRENT_ERA.level_to_propose_task)
    )
    task = await make_task(
        db_session, character, status=TaskStatus.pending, commit=True
    )

    resp = await client.put(
        f"/tasks/{task.id}",
        json={"title": "t", "point_value": CAP + 1, "level_required": 1},
        headers=auth_headers,
    )

    assert resp.status_code == 422
    assert resp.json()["detail"]["code"] == "TASK_POINTS_TOO_HIGH"
