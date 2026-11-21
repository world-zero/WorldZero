"""#328: account-scoped flag guards (anti-self-flag + anti-gang), praxes and comments."""
import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from game_config import CURRENT_ERA
from models.account import Account
from models.character import Character, CharacterStatus
from models.character_stats import CharacterStats
from models.duel import Duel, DuelStatus
from models.era import Era
from models.faction import Faction
from models.praxis import Praxis, PraxisMember, PraxisStatus, PraxisType
from models.task import Task
from services.auth import create_jwt
from tests.integration.factories import DEFAULT_FACTION_SLUG

FLAG_LEVEL = CURRENT_ERA.flag_level_required


async def _seed_life(
    db_session: AsyncSession,
    account: Account,
    era: Era,
    *,
    username: str,
    level: int = FLAG_LEVEL,
) -> Character:
    ch = Character(
        account_id=account.id,
        username=username,
        display_name=username.title(),
        faction_slug=DEFAULT_FACTION_SLUG,
        status=CharacterStatus.active,
    )
    db_session.add(ch)
    await db_session.flush()
    db_session.add(
        CharacterStats(character_id=ch.id, era_id=era.id, level=level, votes_spent_this_era=0)
    )
    await db_session.commit()
    await db_session.refresh(ch)
    return ch


async def _submit_solo(client: AsyncClient, task: Task, headers: dict) -> int:
    create = await client.post(
        "/praxes",
        json={"task_id": task.id, "type": "solo", "title": "Work"},
        headers=headers,
    )
    assert create.status_code == 201, create.text
    praxis_id = create.json()["id"]
    assert (await client.post(f"/praxes/{praxis_id}/submit", headers=headers)).status_code == 200
    return praxis_id


async def _carry(client: AsyncClient, character_id: int, headers: dict) -> None:
    resp = await client.post(
        "/me/active-character", json={"character_id": character_id}, headers=headers
    )
    assert resp.status_code == 200, resp.text


async def _set_level(db_session: AsyncSession, character: Character, era: Era, level: int) -> None:
    stats = (
        await db_session.execute(
            select(CharacterStats).where(
                CharacterStats.character_id == character.id,
                CharacterStats.era_id == era.id,
            )
        )
    ).scalar_one()
    stats.level = level
    await db_session.commit()


@pytest.mark.asyncio
async def test_sibling_cannot_flag_own_accounts_praxis(
    client: AsyncClient,
    db_session: AsyncSession,
    account: Account,
    character: Character,
    active_task: Task,
    era: Era,
    some_faction: Faction,
    auth_headers: dict,
):
    praxis_id = await _submit_solo(client, active_task, auth_headers)
    puppet_b = await _seed_life(db_session, account, era, username="puppetb")

    await _carry(client, puppet_b.id, auth_headers)
    resp = await client.post(
        f"/praxes/{praxis_id}/flag", json={"reason": "spam"}, headers=auth_headers
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_account_flag_uniqueness_and_non_sibling_still_allowed(
    client: AsyncClient,
    db_session: AsyncSession,
    account: Account,
    account2: Account,
    character: Character,
    character2: Character,
    active_task: Task,
    era: Era,
    some_faction: Faction,
    auth_headers: dict,
    auth_headers2: dict,
):
    target_pid = await _submit_solo(client, active_task, auth_headers2)

    await _set_level(db_session, character, era, FLAG_LEVEL)
    puppet_b = await _seed_life(db_session, account, era, username="puppetb")

    await _carry(client, character.id, auth_headers)
    first = await client.post(
        f"/praxes/{target_pid}/flag", json={"reason": "other", "reason_detail": "genuine concern here"}, headers=auth_headers
    )
    assert first.status_code == 200

    await _carry(client, puppet_b.id, auth_headers)
    gang = await client.post(
        f"/praxes/{target_pid}/flag", json={"reason": "spam"}, headers=auth_headers
    )
    assert gang.status_code == 409

    account3 = Account(email="third-flagger@example.com")
    db_session.add(account3)
    await db_session.flush()
    non_sibling = await _seed_life(db_session, account3, era, username="nonsibling")
    ns_headers = {"Authorization": f"Bearer {create_jwt(account3.id)}"}
    assert non_sibling.id
    ns_flag = await client.post(
        f"/praxes/{target_pid}/flag", json={"reason": "harassment"}, headers=ns_headers
    )
    assert ns_flag.status_code == 200


async def _post_comment(client: AsyncClient, praxis_id: int, headers: dict) -> int:
    resp = await client.post(
        f"/praxes/{praxis_id}/comments",
        json={"body_text": "worth discussing"},
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


@pytest.mark.asyncio
async def test_sibling_cannot_flag_own_accounts_comment(
    client: AsyncClient,
    db_session: AsyncSession,
    account: Account,
    character: Character,
    praxis_solo: Praxis,
    era: Era,
    some_faction: Faction,
    auth_headers: dict,
):
    await _set_level(db_session, character, era, FLAG_LEVEL)
    comment_id = await _post_comment(client, praxis_solo.id, auth_headers)
    puppet_b = await _seed_life(db_session, account, era, username="puppetb")

    await _carry(client, puppet_b.id, auth_headers)
    resp = await client.post(
        f"/comments/{comment_id}/flag", json={"reason": "spam"}, headers=auth_headers
    )
    assert resp.status_code == 403

    # Review threshold is 1: a leaky guard would have hidden it already.
    listed = await client.get(f"/praxes/{praxis_solo.id}/comments")
    assert [c["id"] for c in listed.json()] == [comment_id]


@pytest.mark.asyncio
async def test_account_comment_flag_uniqueness_and_non_sibling_still_allowed(
    client: AsyncClient,
    db_session: AsyncSession,
    account: Account,
    account2: Account,
    character: Character,
    character2: Character,
    praxis_solo: Praxis,
    era: Era,
    some_faction: Faction,
    auth_headers: dict,
    auth_headers2: dict,
):
    comment_id = await _post_comment(client, praxis_solo.id, auth_headers2)

    await _set_level(db_session, character, era, FLAG_LEVEL)
    puppet_b = await _seed_life(db_session, account, era, username="puppetb")

    await _carry(client, character.id, auth_headers)
    first = await client.post(
        f"/comments/{comment_id}/flag",
        json={"reason": "other", "reason_detail": "genuine concern here"},
        headers=auth_headers,
    )
    assert first.status_code == 200, first.text

    await _carry(client, puppet_b.id, auth_headers)
    gang = await client.post(
        f"/comments/{comment_id}/flag", json={"reason": "spam"}, headers=auth_headers
    )
    assert gang.status_code == 409

    account3 = Account(email="third-comment-flagger@example.com")
    db_session.add(account3)
    await db_session.flush()
    await _seed_life(db_session, account3, era, username="commentnonsibling")
    ns_headers = {"Authorization": f"Bearer {create_jwt(account3.id)}"}
    ns_flag = await client.post(
        f"/comments/{comment_id}/flag",
        json={"reason": "harassment"},
        headers=ns_headers,
    )
    assert ns_flag.status_code == 200, ns_flag.text


@pytest.mark.asyncio
async def test_keep_closes_flags_and_flagger_can_report_again(
    client: AsyncClient,
    db_session: AsyncSession,
    account: Account,
    character: Character,
    character2: Character,
    active_task: Task,
    era: Era,
    some_faction: Faction,
    auth_headers: dict,
    auth_headers2: dict,
):
    """#3726: a ruling closes open flags: out of the queue and the per-account check."""
    from tests.integration.factories import make_admin

    pid = await _submit_solo(client, active_task, auth_headers2)
    await _set_level(db_session, character, era, FLAG_LEVEL)
    await make_admin(db_session, account)
    flag = {"reason": "spam"}
    first = await client.post(f"/praxes/{pid}/flag", json=flag, headers=auth_headers)
    assert first.status_code == 200
    kept = await client.patch(
        f"/admin/praxes/{pid}/moderate",
        json={"status": "visible"},
        headers=auth_headers,
    )
    assert kept.status_code == 200
    emptied = await client.get("/admin/praxes/flagged", headers=auth_headers)
    assert emptied.json() == []

    again = await client.post(
        f"/praxes/{pid}/flag", json={"reason": "harassment"}, headers=auth_headers
    )
    assert again.status_code == 200
    queue = (await client.get("/admin/praxes/flagged", headers=auth_headers)).json()
    assert [f["reason"] for f in queue[0]["flags"]] == ["harassment"]
    repeat = await client.post(f"/praxes/{pid}/flag", json=flag, headers=auth_headers)
    assert repeat.status_code == 409
    overview = await client.get("/admin/overview", headers=auth_headers)
    assert overview.json()["flagged_praxis"] == len(queue)


@pytest.mark.asyncio
async def test_keep_closes_comment_flags_and_flagger_can_report_again(
    client: AsyncClient,
    db_session: AsyncSession,
    account: Account,
    character: Character,
    character2: Character,
    praxis_solo: Praxis,
    era: Era,
    some_faction: Faction,
    auth_headers: dict,
    auth_headers2: dict,
):
    """#3726: Keep on a comment closes its flags; the threshold counts only new ones."""
    from tests.integration.factories import make_admin

    comment_id = await _post_comment(client, praxis_solo.id, auth_headers2)
    await _set_level(db_session, character, era, FLAG_LEVEL)
    await make_admin(db_session, account)
    url = f"/comments/{comment_id}/flag"
    first = await client.post(url, json={"reason": "spam"}, headers=auth_headers)
    assert first.status_code == 200
    kept = await client.patch(
        f"/admin/comments/{comment_id}/moderate",
        json={"status": "visible"},
        headers=auth_headers,
    )
    assert kept.status_code == 200, kept.text
    queue = await client.get("/admin/comments/flagged", headers=auth_headers)
    assert queue.json() == []

    again = await client.post(url, json={"reason": "harassment"}, headers=auth_headers)
    assert again.status_code == 200
    queue = (await client.get("/admin/comments/flagged", headers=auth_headers)).json()
    assert [f["reason"] for f in queue[0]["flags"]] == ["harassment"]


@pytest.mark.asyncio
async def test_comment_threshold_counts_only_unresolved_flags(
    client: AsyncClient,
    db_session: AsyncSession,
    account: Account,
    character: Character,
    character2: Character,
    praxis_solo: Praxis,
    era: Era,
    some_faction: Faction,
    auth_headers: dict,
    auth_headers2: dict,
):
    """#3968: every era's threshold is 1, so only a higher one proves the filter."""
    import dataclasses

    from eras.era_1 import ERA_1
    from models.comment import Comment
    from models.flag import FlagReason
    from models.praxis import ModerationStatus
    from services.comment import flag_comment
    from tests.integration.factories import make_admin

    comment_id = await _post_comment(client, praxis_solo.id, auth_headers2)
    await _set_level(db_session, character, era, FLAG_LEVEL)
    await make_admin(db_session, account)
    url = f"/comments/{comment_id}/flag"
    first = await client.post(url, json={"reason": "spam"}, headers=auth_headers)
    assert first.status_code == 200
    await client.patch(
        f"/admin/comments/{comment_id}/moderate",
        json={"status": "visible"},
        headers=auth_headers,
    )

    era_two = dataclasses.replace(ERA_1, comment_flag_review_threshold=2)
    await flag_comment(
        comment_id, character, FlagReason.harassment, db_session, era=era_two
    )

    comment = await db_session.get(Comment, comment_id)
    await db_session.refresh(comment)
    assert comment.moderation_status != ModerationStatus.flagged


@pytest.mark.asyncio
async def test_stranger_cannot_flag_a_draft(
    client: AsyncClient,
    db_session: AsyncSession,
    character: Character,
    character2: Character,
    active_task: Task,
    era: Era,
    auth_headers: dict,
    auth_headers2: dict,
):
    create = await client.post(
        "/praxes",
        json={"task_id": active_task.id, "type": "solo", "title": "PRIVATE"},
        headers=auth_headers,
    )
    praxis_id = create.json()["id"]
    await _set_level(db_session, character2, era, FLAG_LEVEL)

    resp = await client.post(
        f"/praxes/{praxis_id}/flag", json={"reason": "spam"}, headers=auth_headers2
    )
    assert resp.status_code == 404
    assert "PRIVATE" not in resp.text
    praxis = await db_session.get(Praxis, praxis_id)
    await db_session.refresh(praxis)
    assert praxis.moderation_status.value == "visible"
    assert praxis.flagged_at is None


@pytest.mark.asyncio
async def test_stranger_cannot_flag_an_unsealed_duel_side(
    client: AsyncClient,
    db_session: AsyncSession,
    character: Character,
    character2: Character,
    character3: Character,
    active_task: Task,
    era: Era,
    auth_headers3: dict,
):
    side = Praxis(
        task_id=active_task.id,
        created_by_id=character.id,
        type=PraxisType.solo,
        status=PraxisStatus.submitted,
        title="Side",
    )
    other = Praxis(
        task_id=active_task.id,
        created_by_id=character2.id,
        type=PraxisType.solo,
        status=PraxisStatus.in_progress,
        title="Other",
    )
    db_session.add_all([side, other])
    await db_session.flush()
    db_session.add_all(
        [
            PraxisMember(
                praxis_id=side.id, character_id=character.id, has_approved=True
            ),
            PraxisMember(
                praxis_id=other.id, character_id=character2.id, has_approved=False
            ),
        ]
    )
    db_session.add(
        Duel(
            task_id=active_task.id,
            challenger_praxis_id=side.id,
            opponent_praxis_id=other.id,
            opponent_character_id=character2.id,
            status=DuelStatus.active,
        )
    )
    await db_session.commit()
    await _set_level(db_session, character3, era, FLAG_LEVEL)

    resp = await client.post(
        f"/praxes/{side.id}/flag", json={"reason": "spam"}, headers=auth_headers3
    )
    assert resp.status_code == 404
