"""/activity-feed end to end; ORM query errors only show up at runtime."""

from datetime import datetime, timedelta, timezone

import pytest
from httpx import AsyncClient
from sqlalchemy import func
from sqlalchemy.ext.asyncio import AsyncSession

from models.character import Character
from models.era import Era
from models.task import Task, TaskStatus
from tests.integration.factories import DEFAULT_FACTION_SLUG

_TAB_TO_COUNT_KEY = {
    "all": "all",
    "friends": "friends",
    "foes": "foes",
    "your_stuff": "your_stuff",
    "global": "global_count",
    "requests": "requests",
}


@pytest.mark.asyncio
async def test_activity_feed_shows_collaborator_submitted(
    client: AsyncClient,
    character: Character,
    character2: Character,
    active_task: Task,
    auth_headers: dict,
    auth_headers2: dict,
):
    """#571."""
    create = await client.post(
        "/praxes",
        json={"task_id": active_task.id, "type": "collab", "title": "Team"},
        headers=auth_headers2,
    )
    praxis_id = create.json()["id"]
    inv = await client.post(
        f"/praxes/{praxis_id}/invite",
        json={"invitee_id": character.id},
        headers=auth_headers2,
    )
    await client.post(
        f"/praxes/{praxis_id}/invite/{inv.json()['id']}/respond",
        json={"accept": True},
        headers=auth_headers,
    )
    await client.post(f"/praxes/{praxis_id}/submit", headers=auth_headers2)

    feed = await client.get(
        "/activity-feed", params={"filter": "your_stuff"}, headers=auth_headers
    )
    assert feed.status_code == 200
    items = [i for i in feed.json()["items"] if i["type"] == "collaborator_submitted"]
    assert len(items) == 1, feed.json()["items"]
    entry = items[0]
    assert entry["payload"]["praxis_id"] == praxis_id
    assert entry["payload"]["character_id"] == character2.id
    assert entry["actor_display_name"] == character2.display_name

    own = await client.get(
        "/activity-feed", params={"filter": "your_stuff"}, headers=auth_headers2
    )
    assert not [
        i for i in own.json()["items"] if i["type"] == "collaborator_submitted"
    ]


@pytest.mark.asyncio
async def test_collaborator_submitted_carries_the_viewers_own_state(
    client: AsyncClient,
    character: Character,
    character2: Character,
    active_task: Task,
    auth_headers: dict,
    auth_headers2: dict,
):
    """#2284: the row says whether the READER still owes their part (drives the CTA).

    The row stays either way; only the CTA changes, so it is a payload field.
    """
    create = await client.post(
        "/praxes",
        json={"task_id": active_task.id, "type": "collab", "title": "Team"},
        headers=auth_headers2,
    )
    praxis_id = create.json()["id"]
    inv = await client.post(
        f"/praxes/{praxis_id}/invite",
        json={"invitee_id": character.id},
        headers=auth_headers2,
    )
    await client.post(
        f"/praxes/{praxis_id}/invite/{inv.json()['id']}/respond",
        json={"accept": True},
        headers=auth_headers,
    )
    await client.post(f"/praxes/{praxis_id}/submit", headers=auth_headers2)

    async def viewer_row() -> dict:
        feed = await client.get(
            "/activity-feed", params={"filter": "your_stuff"}, headers=auth_headers
        )
        assert feed.status_code == 200
        rows = [
            i for i in feed.json()["items"] if i["type"] == "collaborator_submitted"
        ]
        assert len(rows) == 1, feed.json()["items"]
        return rows[0]

    still_owed = await viewer_row()
    assert still_owed["payload"]["viewer_has_approved"] is False, (
        "the viewer has not filed their part, so the CTA is still live"
    )

    await client.post(f"/praxes/{praxis_id}/submit", headers=auth_headers)

    filed = await viewer_row()
    assert filed["payload"]["viewer_has_approved"] is True, (
        "the viewer has filed, so the CTA must drop"
    )


@pytest.mark.asyncio
async def test_activity_feed_awaiting_submission_in_requests(
    client: AsyncClient,
    character: Character,
    character2: Character,
    active_task: Task,
    auth_headers: dict,
    auth_headers2: dict,
):
    create = await client.post(
        "/praxes",
        json={"task_id": active_task.id, "type": "collab", "title": "Team"},
        headers=auth_headers2,
    )
    praxis_id = create.json()["id"]
    inv = await client.post(
        f"/praxes/{praxis_id}/invite",
        json={"invitee_id": character.id},
        headers=auth_headers2,
    )
    await client.post(
        f"/praxes/{praxis_id}/invite/{inv.json()['id']}/respond",
        json={"accept": True},
        headers=auth_headers,
    )

    async def requests_for_invitee() -> dict:
        return (
            await client.get(
                "/activity-feed", params={"filter": "requests", "limit": 100},
                headers=auth_headers,
            )
        ).json()

    joined = await requests_for_invitee()
    assert not [i for i in joined["items"] if i["type"] == "awaiting_submission"], (
        "#4296: nobody has submitted yet, so nobody is waiting on the invitee"
    )

    await client.post(f"/praxes/{praxis_id}/submit", headers=auth_headers2)
    requests = await requests_for_invitee()
    awaiting = [i for i in requests["items"] if i["type"] == "awaiting_submission"]
    assert len(awaiting) == 1, requests["items"]
    assert awaiting[0]["payload"]["praxis_id"] == praxis_id
    assert awaiting[0]["payload"]["praxis_type"] == "collab"
    # ADR-0036 invariant.
    assert requests["counts"]["requests"] == len(requests["items"])

    await client.post(f"/praxes/{praxis_id}/submit", headers=auth_headers)
    after = (
        await client.get(
            "/activity-feed", params={"filter": "requests", "limit": 100},
            headers=auth_headers,
        )
    ).json()
    assert not [i for i in after["items"] if i["type"] == "awaiting_submission"]


@pytest.mark.asyncio
async def test_one_member_collab_owes_nobody_until_someone_joins(
    client: AsyncClient,
    character: Character,
    character2: Character,
    active_task: Task,
    auth_headers: dict,
    auth_headers2: dict,
):
    """A one-member collab is not an obligation (#1980); queue and ``/me/sidebar`` badge
    must agree."""
    create = await client.post(
        "/praxes",
        json={"task_id": active_task.id, "type": "collab", "title": "Just me"},
        headers=auth_headers2,
    )
    assert create.status_code in (200, 201), create.text
    praxis_id = create.json()["id"]

    async def awaiting_for_creator() -> list[dict]:
        requests = (
            await client.get(
                "/activity-feed", params={"filter": "requests", "limit": 100},
                headers=auth_headers2,
            )
        ).json()
        sidebar = await client.get("/me/sidebar", headers=auth_headers2)
        assert sidebar.json()["pending_requests_count"] == len(requests["items"])
        return [i for i in requests["items"] if i["type"] == "awaiting_submission"]

    assert await awaiting_for_creator() == [], (
        "a collab with only its creator in it is a solo draft in every respect "
        "the rule cares about — nobody is waiting on anybody"
    )

    inv = await client.post(
        f"/praxes/{praxis_id}/invite",
        json={"invitee_id": character.id},
        headers=auth_headers2,
    )
    await client.post(
        f"/praxes/{praxis_id}/invite/{inv.json()['id']}/respond",
        json={"accept": True},
        headers=auth_headers,
    )

    assert await awaiting_for_creator() == [], (
        "#4296: a joined collab where nobody has submitted owes nobody either"
    )

    await client.post(f"/praxes/{praxis_id}/submit", headers=auth_headers)
    appeared = await awaiting_for_creator()
    assert len(appeared) == 1, appeared
    assert appeared[0]["payload"]["praxis_id"] == praxis_id


@pytest.mark.asyncio
async def test_solo_praxis_never_awaits_its_own_author(
    client: AsyncClient,
    active_task: Task,
    auth_headers: dict,
):
    """Also covers duel sides, which are one-member solo praxes (ADR-0011)."""
    create = await client.post(
        "/praxes",
        json={"task_id": active_task.id, "type": "solo", "title": "Mine"},
        headers=auth_headers,
    )
    assert create.status_code in (200, 201), create.text

    requests = (
        await client.get(
            "/activity-feed", params={"filter": "requests", "limit": 100},
            headers=auth_headers,
        )
    ).json()
    assert not [i for i in requests["items"] if i["type"] == "awaiting_submission"]


# Type axis and cursor at the HTTP seam (#1420).

@pytest.mark.asyncio
async def test_types_intersects_with_the_filter_rather_than_replacing_it(
    client: AsyncClient,
    db_session: AsyncSession,
    character: Character,
    character2: Character,
    active_task: Task,
    auth_headers: dict,
):
    """``filter=friends&types=...`` narrows; a friend signing up adds no row (#4323)."""
    from models.praxis import Praxis, PraxisMember, PraxisStatus, PraxisType
    from models.relationship import Relationship, RelationshipType

    db_session.add(
        Relationship(
            from_character_id=character.id,
            to_character_id=character2.id,
            type=RelationshipType.friend,
        )
    )
    # friend_completion
    db_session.add(
        Praxis(
            task_id=active_task.id,
            created_by_id=character2.id,
            type=PraxisType.solo,
            status=PraxisStatus.submitted,
            title="Friend did it",
            body_text="proof",
        )
    )
    # Both in progress on one task: used to be a friend_signup row, now nothing.
    mine = Praxis(
        task_id=active_task.id,
        created_by_id=character.id,
        type=PraxisType.solo,
        status=PraxisStatus.in_progress,
        title="Mine",
        body_text="proof",
    )
    theirs = Praxis(
        task_id=active_task.id,
        created_by_id=character2.id,
        type=PraxisType.solo,
        status=PraxisStatus.in_progress,
        title="Theirs",
        body_text="proof",
    )
    db_session.add_all([mine, theirs])
    await db_session.flush()
    db_session.add_all(
        [
            PraxisMember(praxis_id=mine.id, character_id=character.id),
            PraxisMember(praxis_id=theirs.id, character_id=character2.id),
        ]
    )
    await db_session.commit()

    unfiltered = await client.get(
        "/activity-feed",
        params={"filter": "friends", "limit": 100},
        headers=auth_headers,
    )
    assert {i["type"] for i in unfiltered.json()["items"]} == {"friend_completion"}

    narrowed = await client.get(
        "/activity-feed",
        params={"filter": "friends", "limit": 100, "types": ["friend_completion"]},
        headers=auth_headers,
    )
    assert narrowed.status_code == 200, narrowed.text
    assert [i["type"] for i in narrowed.json()["items"]] == ["friend_completion"]

    # Outside the rail: intersection, so empty.
    outside = await client.get(
        "/activity-feed",
        params={"filter": "friends", "limit": 100, "types": ["vote_on_mine"]},
        headers=auth_headers,
    )
    assert outside.json()["items"] == []


@pytest.mark.asyncio
async def test_types_accepts_more_than_one_value(
    client: AsyncClient, character: Character, active_task: Task, auth_headers: dict
):
    """Repeated bare key only; ``types[]=a`` is silently ignored by FastAPI (200,
    unfiltered)."""
    response = await client.get(
        "/activity-feed",
        params={"limit": 100, "types": ["global_task", "era_announcement"]},
        headers=auth_headers,
    )
    assert response.status_code == 200, response.text
    types = {item["type"] for item in response.json()["items"]}
    assert types == {"global_task", "era_announcement"}


@pytest.mark.asyncio
async def test_an_unknown_type_is_ignored_and_an_empty_list_filters_nothing(
    client: AsyncClient, character: Character, active_task: Task, auth_headers: dict
):
    """A stale bookmark must not hard-fail; empty never means "match nothing"."""
    baseline = await client.get(
        "/activity-feed", params={"limit": 100}, headers=auth_headers
    )
    baseline_types = {item["type"] for item in baseline.json()["items"]}
    assert baseline_types, "the fixture must put something in the feed"

    for params in (
        {"limit": 100, "types": ["no_such_type"]},
        {"limit": 100, "types": []},
        {"limit": 100, "types": [""]},
    ):
        response = await client.get(
            "/activity-feed", params=params, headers=auth_headers
        )
        assert response.status_code == 200, (params, response.text)
        assert {
            item["type"] for item in response.json()["items"]
        } == baseline_types, params

    mixed = await client.get(
        "/activity-feed",
        params={"limit": 100, "types": ["no_such_type", "global_task"]},
        headers=auth_headers,
    )
    assert {item["type"] for item in mixed.json()["items"]} == {"global_task"}


@pytest.mark.asyncio
async def test_a_malformed_before_cursor_is_a_422_not_a_500(
    client: AsyncClient, character: Character, auth_headers: dict
):
    for bad in (
        "not-a-date",
        f"2999-01-01T00:00:00+00:00|global_task|{2**63}",
        "2999-01-01T00:00:00+00:00|global_task|-1",
    ):
        response = await client.get(
            "/activity-feed", params={"before": bad}, headers=auth_headers
        )
        assert response.status_code == 422, response.text

    for ok in (1, 2**31):
        good = await client.get(
            "/activity-feed",
            params={"before": f"2999-01-01T00:00:00+00:00|global_task|{ok}"},
            headers=auth_headers,
        )
        assert good.status_code == 200, good.text


@pytest.mark.asyncio
async def test_a_malformed_payload_is_dropped_and_its_siblings_still_serve(
    client: AsyncClient,
    db_session: AsyncSession,
    character: Character,
    active_task: Task,
    auth_headers: dict,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
):
    """One drifted payload costs one card, never the page (#1402).

    Survivors from the same source (per-item drop) and another source. The drift
    is an undeclared key, which only ``extra="forbid"`` catches.
    """
    import logging
    from dataclasses import replace as replace_dataclass

    import services.activity_feed as feed_service
    from models.task import TaskStatus
    from schemas.activity_feed import GlobalTaskPayload

    sibling_task = Task(
        title="Sibling Task",
        description="Survives the drop",
        point_value=5,
        level_required=0,
        status=TaskStatus.active,
        activated_at=func.now(),
        created_by_id=character.id,
        primary_faction_slug=DEFAULT_FACTION_SLUG,
    )
    db_session.add(sibling_task)
    await db_session.commit()
    await db_session.refresh(sibling_task)

    poisoned_task_id = active_task.id
    global_source = next(
        source
        for source in feed_service.FEED_SOURCES
        if source.item_type == feed_service.FEED_ITEM_TYPE_GLOBAL_TASK
    )
    healthy_to_item = global_source.to_item

    def drifted_to_item(row):
        """The global_task producer, drifted for exactly one row."""
        if row.id == poisoned_task_id:
            GlobalTaskPayload(
                task_id=row.id,
                task_title=row.title,
                task_point_value=row.point_value,
                task_level_required=row.level_required,
                task_faction_slug=row.primary_faction_slug,
                task_banner_url="/media/undeclared.png",
            )
        return healthy_to_item(row)

    monkeypatch.setattr(
        feed_service,
        "FEED_SOURCES",
        tuple(
            replace_dataclass(source, to_item=drifted_to_item)
            if source is global_source
            else source
            for source in feed_service.FEED_SOURCES
        ),
    )

    with caplog.at_level(logging.ERROR, logger="services.activity_feed"):
        response = await client.get(
            "/activity-feed", params={"filter": "global"}, headers=auth_headers
        )

    assert response.status_code == 200, response.text
    items = response.json()["items"]

    global_task_ids = [
        item["payload"]["task_id"] for item in items if item["type"] == "global_task"
    ]
    assert poisoned_task_id not in global_task_ids, "the malformed item was served"
    assert sibling_task.id in global_task_ids, "a same-source sibling was dropped too"
    assert any(item["type"] == "era_announcement" for item in items), (
        "a sibling from another source was dropped too"
    )

    assert f"global_task:{poisoned_task_id}" in caplog.text
    assert "task_banner_url" in caplog.text


def test_every_registry_type_has_a_schema_variant():
    """Type strings are spelled twice (``Literal`` can't take a variable); this keeps
    them equal."""
    from typing import get_args

    from schemas.activity_feed import ActivityFeedItem
    from services.activity_feed import FEED_ITEM_TYPES

    variants = get_args(get_args(ActivityFeedItem)[0])
    tags = {get_args(variant.model_fields["type"].annotation)[0] for variant in variants}
    assert tags == set(FEED_ITEM_TYPES)


@pytest.mark.asyncio
async def test_accepted_invite_from_a_non_friend_is_one_row(
    client: AsyncClient,
    db_session: AsyncSession,
    character: Character,
    character2: Character,
    active_task: Task,
    auth_headers: dict,
):
    """#4323: no friendship needed; the invitee's joined_at is the time."""
    from models.praxis import (
        Praxis,
        PraxisInvite,
        PraxisInviteStatus,
        PraxisMember,
        PraxisStatus,
        PraxisType,
    )

    collab = Praxis(
        task_id=active_task.id,
        created_by_id=character.id,
        type=PraxisType.collab,
        status=PraxisStatus.in_progress,
        title="Together",
        body_text="proof",
    )
    db_session.add(collab)
    await db_session.flush()
    member = PraxisMember(praxis_id=collab.id, character_id=character2.id)
    db_session.add_all(
        [
            PraxisMember(praxis_id=collab.id, character_id=character.id),
            member,
            PraxisInvite(
                praxis_id=collab.id,
                inviter_id=character.id,
                invitee_id=character2.id,
                status=PraxisInviteStatus.accepted,
            ),
        ]
    )
    await db_session.commit()
    await db_session.refresh(member)

    response = await client.get(
        "/activity-feed",
        params={"filter": "your_stuff", "limit": 100, "types": ["collab_accepted"]},
        headers=auth_headers,
    )
    assert response.status_code == 200, response.text
    items = response.json()["items"]
    assert len(items) == 1, items
    assert items[0]["actor_display_name"] == character2.display_name
    assert items[0]["payload"]["praxis_id"] == collab.id
    assert items[0]["timestamp"].startswith(member.joined_at.isoformat()[:19])


async def _walk(client: AsyncClient, headers: dict, limit: int) -> list[str]:
    keys: list[str] = []
    cursor = None
    for _ in range(50):
        params = {"filter": "global", "limit": limit}
        if cursor:
            params["before"] = cursor
        response = await client.get("/activity-feed", params=params, headers=headers)
        body = response.json()
        keys += [item["item_key"] for item in body["items"]]
        cursor = body["next_cursor"]
        if cursor is None:
            return keys
    raise AssertionError("cursor never ended")


@pytest.mark.asyncio
@pytest.mark.parametrize("limit", [3, 5, 10])
@pytest.mark.parametrize("with_era_tie", [False, True])
async def test_load_more_walks_items_sharing_one_timestamp(
    client: AsyncClient,
    db_session: AsyncSession,
    character: Character,
    auth_headers: dict,
    limit: int,
    with_era_tie: bool,
):
    """Seam: /activity-feed cursor; a batch activation shares one `now()`."""
    moment = datetime.now(timezone.utc) + timedelta(hours=1)
    db_session.add_all(
        Task(
            title=f"Batch {n}",
            description="d",
            point_value=10,
            level_required=0,
            status=TaskStatus.active,
            activated_at=moment,
            created_by_id=character.id,
            primary_faction_slug=DEFAULT_FACTION_SLUG,
        )
        for n in range(12)
    )
    if with_era_tie:
        db_session.add(
            Era(
                name="Tie",
                config_key="era_1",
                started_at=moment,
                started_by_id=character.account_id,
            )
        )
    await db_session.commit()

    everything = await _walk(client, auth_headers, 100)
    assert len(everything) == len(set(everything)) >= 12 + with_era_tie
    assert await _walk(client, auth_headers, limit) == everything
