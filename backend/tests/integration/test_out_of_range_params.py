"""Out-of-range numbers are a 422/404, never a 500 or a roster dump (#3923)."""
import pytest
from sqlalchemy import update

from game_config import CURRENT_ERA
from models.character_stats import CharacterStats
from models.task import TaskStatus
from tests.integration.factories import make_admin, make_task

BAD = ["-1", "0", str(2**31), str(2**63), "abc"]
ID_PATHS = [
    "/praxes/{}", "/tasks/{}", "/duels/{}/detail", "/characters/{}",
    "/tasks/{}/signups", "/tasks/{}/comments", "/praxes/{}/comments",
]
ID_QUERIES = [
    "/praxes?task_id={}", "/praxes?member_id={}", "/praxes?character_id={}",
    "/tasks?created_by={}", "/tasks?exclude_character_id={}",
    "/characters?exclude_active_task_id={}", "/tasks?min_points={}",
    "/tasks?max_points={}",
]
LIST_PATHS = ["/characters", "/leaderboard", "/praxes", "/tasks"]


@pytest.mark.asyncio
@pytest.mark.parametrize("value", BAD)
@pytest.mark.parametrize("template", ID_PATHS + ID_QUERIES)
async def test_bad_numbers_never_500(client, template, value):
    resp = await client.get(template.format(value))

    assert resp.status_code < 500


@pytest.mark.asyncio
@pytest.mark.parametrize("path", LIST_PATHS)
@pytest.mark.parametrize(
    "query", ["limit=-1", "limit=0", "limit=501", "offset=-1", "offset=abc"]
)
async def test_lists_reject_bad_paging(client, path, query):
    resp = await client.get(f"{path}?{query}")

    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_public_list_has_a_ceiling_but_leaderboard_keeps_500(client):
    assert (await client.get("/characters?limit=201")).status_code == 422
    assert (await client.get("/leaderboard?limit=201")).status_code == 200
    assert (await client.get("/leaderboard?limit=500")).status_code == 200


@pytest.mark.asyncio
@pytest.mark.parametrize("value", ["FRIEND", "", "enemy"])
async def test_relationship_type_is_an_enum(client, auth_headers, character, value):
    resp = await client.get(f"/relationships?type={value}", headers=auth_headers)

    assert resp.status_code == 422


async def _proposer(db_session, character):
    await db_session.execute(
        update(CharacterStats)
        .where(CharacterStats.character_id == character.id)
        .values(level=CURRENT_ERA.level_to_propose_task)
    )
    await db_session.commit()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "body",
    [
        {"level_required": len(CURRENT_ERA.level_thresholds)},
        {"level_required": 2**31},
        {"point_value": 2**31},
    ],
)
async def test_proposal_numbers_out_of_range_are_422(
    client, db_session, character, auth_headers, body
):
    await _proposer(db_session, character)

    resp = await client.post(
        "/tasks",
        json={"title": "t", "point_value": 1, "level_required": 1, **body},
        headers=auth_headers,
    )

    assert resp.status_code == 422


@pytest.mark.asyncio
@pytest.mark.parametrize("field", ["primary_faction_slug", "metatask_faction_slug"])
async def test_proposal_unknown_faction_is_coded_422(
    client, db_session, character, auth_headers, field
):
    await _proposer(db_session, character)

    resp = await client.post(
        "/tasks",
        json={"title": "t", "point_value": 1, "level_required": 1, field: "zzz"},
        headers=auth_headers,
    )

    assert resp.status_code == 422
    assert resp.json()["detail"]["code"] == "TASK_FACTION_UNKNOWN"


@pytest.mark.asyncio
async def test_admin_patch_point_value_is_capped(
    client, db_session, account, character, auth_headers
):
    await make_admin(db_session, account)
    task = await make_task(
        db_session, character, status=TaskStatus.pending, commit=True
    )
    cap = CURRENT_ERA.proposed_task_points_max

    over = await client.patch(
        f"/admin/tasks/{task.id}", json={"point_value": cap + 1}, headers=auth_headers
    )
    huge = await client.patch(
        f"/admin/tasks/{task.id}", json={"point_value": 2**31}, headers=auth_headers
    )

    assert over.status_code == 422
    assert over.json()["detail"]["code"] == "TASK_POINTS_TOO_HIGH"
    assert huge.status_code == 422
