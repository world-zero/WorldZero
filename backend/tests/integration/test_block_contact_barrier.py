"""A block is a contact barrier (#3867, ADR-0077 amendment).

``character`` (A) blocks ``character2`` (B). B's requests to A are swallowed, B's
comments are censored for A alone, A can't reach B, and B can't tell.
"""
import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from errors import ErrorCode
from models.character import Character
from models.character_block import CharacterBlock
from models.comment import Comment, CommentMention
from models.duel import Duel, DuelStatus
from models.era import Era
from models.nudge import Nudge
from models.praxis import (
    ModerationStatus,
    Praxis,
    PraxisInvite,
    PraxisInviteStatus,
    PraxisMember,
    PraxisStatus,
    PraxisType,
)
from models.relationship import Relationship, RelationshipType
from models.task import Task
from services.praxis import get_praxis
from services.vote import viewer_can_vote, viewer_can_vote_map
from tests.integration.factories import (
    make_admin,
    make_solo_praxis,
    make_task,
    raise_to_duel_level,
)

REQUEST_TYPES = {"collab_invite", "duel_challenge", "nudge"}


async def _block(session: AsyncSession, blocker: Character, blocked: Character) -> None:
    session.add(
        CharacterBlock(blocker_character_id=blocker.id, blocked_character_id=blocked.id)
    )
    await session.commit()


async def _request_types(client: AsyncClient, headers: dict) -> set[str]:
    """Invites and challenges live on the requests tab, nudges on ``all``."""
    types: set[str] = set()
    for path in ("/activity-feed?filter=requests", "/activity-feed"):
        feed = await client.get(path, headers=headers)
        assert feed.status_code == 200, feed.text
        types |= {item["type"] for item in feed.json()["items"]}
    return types & REQUEST_TYPES


async def _pending_count(client: AsyncClient, headers: dict) -> int:
    sidebar = await client.get("/me/sidebar", headers=headers)
    assert sidebar.status_code == 200, sidebar.text
    return sidebar.json()["pending_requests_count"]


async def _b_requests_a(
    session: AsyncSession, era: Era, a: Character, b: Character, praxis_collab: Praxis
) -> Praxis:
    """B invites, challenges and nudges A; returns B's invite praxis."""
    praxis_collab.status = PraxisStatus.in_progress
    await raise_to_duel_level(session, a.id)
    await raise_to_duel_level(session, b.id)
    other_task = await make_task(session, b, title="b's collab")
    invite_praxis = Praxis(
        task_id=other_task.id, created_by_id=b.id, type=PraxisType.collab, title="B's"
    )
    duel_task = await make_task(session, b, title="b's duel")
    duel_praxis = Praxis(
        task_id=duel_task.id,
        created_by_id=b.id,
        type=PraxisType.solo,
        status=PraxisStatus.in_progress,
    )
    session.add_all([invite_praxis, duel_praxis])
    await session.flush()
    session.add_all(
        [
            PraxisMember(praxis_id=invite_praxis.id, character_id=b.id),
            PraxisMember(praxis_id=duel_praxis.id, character_id=b.id),
            PraxisInvite(
                praxis_id=invite_praxis.id,
                inviter_id=b.id,
                invitee_id=a.id,
                status=PraxisInviteStatus.pending,
            ),
            Duel(
                task_id=duel_task.id,
                challenger_praxis_id=duel_praxis.id,
                opponent_character_id=a.id,
                status=DuelStatus.pending,
            ),
            Nudge(
                from_character_id=b.id, to_character_id=a.id, praxis_id=praxis_collab.id
            ),
        ]
    )
    await session.commit()
    return invite_praxis


@pytest.mark.asyncio
async def test_requests_pending_at_block_time_are_swallowed_and_return_on_unblock(
    client: AsyncClient,
    db_session: AsyncSession,
    era: Era,
    character: Character,
    character2: Character,
    praxis_collab: Praxis,
    auth_headers: dict,
):
    await _b_requests_a(db_session, era, character, character2, praxis_collab)
    assert await _request_types(client, auth_headers) == REQUEST_TYPES
    pending = await _pending_count(client, auth_headers)

    await _block(db_session, character, character2)
    assert await _request_types(client, auth_headers) == set()
    # The invite and the challenge; A's own unfiled part still badges.
    assert await _pending_count(client, auth_headers) == pending - 2

    unblock = await client.delete(
        f"/relationships/blocks/{character2.id}", headers=auth_headers
    )
    assert unblock.status_code == 204, unblock.text
    assert await _request_types(client, auth_headers) == REQUEST_TYPES


@pytest.mark.asyncio
async def test_the_blocked_party_sees_nothing_change(
    client: AsyncClient,
    db_session: AsyncSession,
    era: Era,
    character: Character,
    character2: Character,
    praxis_collab: Praxis,
    auth_headers2: dict,
):
    """Silence: every read B makes is byte-identical with and without the block."""
    invite_praxis = await _b_requests_a(
        db_session, era, character, character2, praxis_collab
    )
    db_session.add(
        Comment(praxis_id=praxis_collab.id, created_by_id=character.id, body_text="hi")
    )
    await db_session.commit()
    reads = (
        f"/praxes/{invite_praxis.id}",
        f"/praxes/{praxis_collab.id}",
        f"/praxes/{praxis_collab.id}/comments",
        "/activity-feed",
        "/me/sidebar",
        f"/characters/{character.id}",
    )

    async def snapshot() -> list:
        responses = [await client.get(path, headers=auth_headers2) for path in reads]
        assert all(response.status_code == 200 for response in responses)
        return [response.json() for response in responses]

    before = await snapshot()
    await _block(db_session, character, character2)
    assert await snapshot() == before


@pytest.mark.asyncio
async def test_a_swallowed_invite_does_not_cost_the_invitee_their_vote(
    client: AsyncClient,
    db_session: AsyncSession,
    character: Character,
    character2: Character,
    active_task: Task,
    auth_headers: dict,
):
    """#2216 counts a pending invite as ownership; a swallowed one must not."""
    praxis = await make_solo_praxis(db_session, active_task, character2)
    praxis.type = PraxisType.collab
    db_session.add(
        PraxisInvite(
            praxis_id=praxis.id,
            inviter_id=character2.id,
            invitee_id=character.id,
            status=PraxisInviteStatus.pending,
        )
    )
    await db_session.commit()
    assert not (await client.get(f"/praxes/{praxis.id}", headers=auth_headers)).json()[
        "viewer_can_vote"
    ]

    await _block(db_session, character, character2)
    detail = await client.get(f"/praxes/{praxis.id}", headers=auth_headers)
    assert detail.json()["viewer_can_vote"] is True
    assert (await viewer_can_vote_map([praxis], character, db_session))[praxis.id]


@pytest.mark.asyncio
async def test_a_swallowed_challenge_does_not_cost_the_opponent_their_vote(
    db_session: AsyncSession,
    character: Character,
    character2: Character,
    active_task: Task,
):
    praxis = await make_solo_praxis(db_session, active_task, character2)
    await raise_to_duel_level(db_session, character.id)
    await raise_to_duel_level(db_session, character2.id)
    db_session.add(
        Duel(
            task_id=active_task.id,
            challenger_praxis_id=praxis.id,
            opponent_character_id=character.id,
            status=DuelStatus.pending,
        )
    )
    await db_session.commit()

    async def can_vote() -> bool:
        loaded = await get_praxis(praxis.id, db_session)
        return await viewer_can_vote(character, loaded, db_session)

    assert not await can_vote()
    await _block(db_session, character, character2)
    assert await can_vote()
    assert (await viewer_can_vote_map([praxis], character, db_session))[praxis.id]


@pytest.mark.asyncio
async def test_comments_and_mentions_are_censored_for_the_blocker_only(
    client: AsyncClient,
    db_session: AsyncSession,
    character: Character,
    character2: Character,
    character3: Character,
    praxis_solo: Praxis,
    auth_headers: dict,
    auth_headers2: dict,
    auth_headers3: dict,
):
    comment = Comment(
        praxis_id=praxis_solo.id,
        created_by_id=character2.id,
        body_text="secret words @testuser",
    )
    db_session.add(comment)
    await db_session.flush()
    db_session.add(
        CommentMention(comment_id=comment.id, mentioned_character_id=character.id)
    )
    await _block(db_session, character, character2)

    thread = f"/praxes/{praxis_solo.id}/comments"
    [censored] = (await client.get(thread, headers=auth_headers)).json()
    assert censored["is_censored"] is True
    assert censored["body_text"] == ""
    assert censored["mentions"] == []
    assert censored["author"]["id"] == character2.id
    assert "secret" not in str(censored)

    for headers in (auth_headers2, auth_headers3):
        [plain] = (await client.get(thread, headers=headers)).json()
        assert plain["body_text"] == "secret words @testuser"
        assert plain["is_censored"] is False

    feed = (await client.get("/activity-feed", headers=auth_headers)).json()["items"]
    [item] = [item for item in feed if item["type"] == "comment_mention"]
    assert item["payload"]["excerpt"] == ""
    assert item["payload"]["is_censored"] is True
    assert item["actor_display_name"] == character2.display_name


@pytest.mark.asyncio
async def test_a_mod_who_blocked_the_author_still_reads_the_real_text(
    client: AsyncClient,
    db_session: AsyncSession,
    account,
    character: Character,
    character2: Character,
    praxis_solo: Praxis,
    auth_headers: dict,
):
    await make_admin(db_session, account)
    db_session.add(
        Comment(
            praxis_id=praxis_solo.id,
            created_by_id=character2.id,
            body_text="flag me",
            moderation_status=ModerationStatus.flagged,
        )
    )
    await _block(db_session, character, character2)

    flagged = await client.get("/admin/comments/flagged", headers=auth_headers)
    assert flagged.status_code == 200, flagged.text
    assert [row["body_text"] for row in flagged.json()] == ["flag me"]


@pytest.mark.asyncio
async def test_completions_from_a_blocked_friend_still_show(
    db_session: AsyncSession,
    character: Character,
    character2: Character,
):
    from services.activity_feed import _get_related_ids

    db_session.add(
        Relationship(
            from_character_id=character.id,
            to_character_id=character2.id,
            type=RelationshipType.friend,
        )
    )
    await _block(db_session, character, character2)
    assert (await _get_related_ids(character.id, db_session))[
        RelationshipType.friend
    ] == [character2.id]


@pytest.mark.asyncio
async def test_the_blocker_cannot_invite_challenge_or_nudge_whom_they_blocked(
    client: AsyncClient,
    db_session: AsyncSession,
    character: Character,
    character2: Character,
    character3: Character,
    praxis_collab: Praxis,
    auth_headers: dict,
):
    await raise_to_duel_level(db_session, character.id)
    await raise_to_duel_level(db_session, character2.id)
    duel_task = await make_task(db_session, character, title="a's duel")
    own_collab_task = await make_task(db_session, character, title="a's collab")
    duel_praxis = Praxis(
        task_id=duel_task.id,
        created_by_id=character.id,
        type=PraxisType.solo,
        status=PraxisStatus.in_progress,
    )
    own_collab = Praxis(
        task_id=own_collab_task.id,
        created_by_id=character.id,
        type=PraxisType.collab,
        title="A's",
    )
    db_session.add_all([duel_praxis, own_collab])
    await db_session.flush()
    db_session.add_all(
        [
            PraxisMember(praxis_id=duel_praxis.id, character_id=character.id),
            PraxisMember(praxis_id=own_collab.id, character_id=character.id),
            PraxisMember(praxis_id=praxis_collab.id, character_id=character3.id),
        ]
    )
    praxis_collab.status = PraxisStatus.in_progress
    for member in await db_session.scalars(
        select(PraxisMember).where(
            PraxisMember.praxis_id == praxis_collab.id,
            PraxisMember.character_id == character.id,
        )
    ):
        member.has_approved = True
    await _block(db_session, character, character2)

    refusals = [
        await client.post(
            f"/praxes/{own_collab.id}/invite",
            json={"invitee_id": character2.id},
            headers=auth_headers,
        ),
        await client.post(
            "/duels/challenge",
            json={
                "challenger_praxis_id": duel_praxis.id,
                "opponent_character_id": character2.id,
            },
            headers=auth_headers,
        ),
        await client.post(
            f"/praxes/{praxis_collab.id}/nudge/{character2.id}", headers=auth_headers
        ),
    ]
    for refusal in refusals:
        assert refusal.status_code == 403, refusal.text
        assert refusal.json()["detail"]["code"] == ErrorCode.contact_blocked.value

    crew = await client.post(f"/praxes/{praxis_collab.id}/nudge", headers=auth_headers)
    assert crew.status_code == 200, crew.text
    assert [row["to_character_id"] for row in crew.json()] == [character3.id]


@pytest.mark.asyncio
async def test_a_blocked_comment_on_my_praxis_is_censored_in_the_feed(
    client: AsyncClient,
    db_session: AsyncSession,
    character: Character,
    character2: Character,
    praxis_solo: Praxis,
    auth_headers: dict,
):
    db_session.add(
        Comment(
            praxis_id=praxis_solo.id,
            created_by_id=character2.id,
            body_text="secret words",
        )
    )
    await _block(db_session, character, character2)

    feed = (await client.get("/activity-feed", headers=auth_headers)).json()["items"]
    [item] = [item for item in feed if item["type"] == "comment_on_mine"]
    assert item["payload"]["excerpt"] == ""
    assert item["payload"]["is_censored"] is True
