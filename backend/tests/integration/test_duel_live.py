"""#3886: a duel going live tells both duelists' friends and foes.

Seams: ``maybe_settle_duel`` (every path into ``settled`` runs through it) for the
stamp and the push; ``get_activity_feed`` for the read-time ``duel_live`` row.
"""

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from models.account import Account
from models.character_block import CharacterBlock
from models.duel import DuelStatus
from models.praxis import Praxis, PraxisStatus
from models.push_subscription import PushSubscription
from models.relationship import Relationship, RelationshipType
from services import push
from services.activity_feed import (
    FEED_ITEM_TYPE_DUEL_LIVE,
    FILTER_FOES,
    FILTER_FRIENDS,
    FeedCursor,
    get_activity_feed,
)
from services.duel import get_duel_detail
from services.praxis_duel import maybe_settle_duel
from tests.integration.conftest import CURRENT_ERA_VOTE_LEVEL
from tests.integration.factories import make_character, make_duel
from tests.integration.test_push import PRIVATE, PUBLIC


@pytest.fixture(autouse=True)
def _factions(some_faction):
    """Seeds the faction rows the factory characters' FK needs."""


async def _viewer(db_session, era, username, **kwargs):
    kwargs.setdefault("peak_level", CURRENT_ERA_VOTE_LEVEL)
    return await make_character(db_session, era, username=username, **kwargs)


def _edge(source, target, rel_type=RelationshipType.friend) -> Relationship:
    return Relationship(
        from_character_id=source.id, to_character_id=target.id, type=rel_type
    )


async def _active_duel(db_session: AsyncSession, era, label: str):
    """An accepted duel whose opponent hasn't cast yet."""
    duel, challenger, opponent = await make_duel(
        db_session, era, label=label, status=DuelStatus.active
    )
    (await db_session.get(Praxis, duel.opponent_praxis_id)).status = (
        PraxisStatus.in_progress
    )
    await db_session.flush()
    return duel, challenger, opponent


async def _go_live(db_session: AsyncSession, duel) -> None:
    (await db_session.get(Praxis, duel.opponent_praxis_id)).status = (
        PraxisStatus.submitted
    )
    await maybe_settle_duel(duel.opponent_praxis_id, db_session)


async def _duel_live_items(db_session, character_id, feed_filter=None):
    feed = await get_activity_feed(character_id, db_session, feed_filter=feed_filter)
    return [item for item in feed.items if item.type == FEED_ITEM_TYPE_DUEL_LIVE]


@pytest.mark.asyncio
async def test_friends_and_foes_each_see_one_row_once_the_duel_goes_live(
    db_session: AsyncSession, era
):
    duel, challenger, opponent = await _active_duel(db_session, era, "dl1")
    friend = await _viewer(db_session, era, "dl1f")
    foe = await _viewer(db_session, era, "dl1x")
    both = await _viewer(db_session, era, "dl1b")
    db_session.add_all([
        _edge(friend, challenger),
        _edge(foe, opponent, RelationshipType.foe),
        _edge(both, challenger),
        _edge(both, opponent, RelationshipType.foe),
    ])
    await db_session.flush()

    for viewer in (friend, foe, both):
        assert await _duel_live_items(db_session, viewer.id) == []

    await _go_live(db_session, duel)

    for viewer in (friend, foe, both):
        (item,) = await _duel_live_items(db_session, viewer.id)
        assert item.item_key == f"duel_live:{duel.id}"
        assert item.timestamp == duel.live_at
        assert item.actor_display_name == challenger.display_name
        assert item.payload.opponent_display_name == opponent.display_name
    assert await _duel_live_items(db_session, friend.id, FILTER_FRIENDS)
    assert await _duel_live_items(db_session, foe.id, FILTER_FOES)


@pytest.mark.asyncio
async def test_live_at_is_stamped_once_and_votes_do_not_move_it(
    db_session: AsyncSession, era
):
    duel, challenger, _ = await _active_duel(db_session, era, "dl2")
    assert duel.live_at is None
    await _go_live(db_session, duel)
    stamped = duel.live_at
    assert duel.status == DuelStatus.settled and stamped is not None

    await maybe_settle_duel(duel.challenger_praxis_id, db_session)
    assert duel.live_at == stamped


@pytest.mark.asyncio
async def test_no_row_for_duelists_alts_low_levels_or_across_a_block(
    db_session: AsyncSession, era
):
    duel, challenger, opponent = await _active_duel(db_session, era, "dl3")
    alt = await _viewer(
        db_session, era, "dl3alt", account=await _account_of(db_session, opponent)
    )
    newbie = await _viewer(db_session, era, "dl3new", peak_level=0)
    blocked = await _viewer(db_session, era, "dl3blk")
    db_session.add_all([
        _edge(challenger, opponent, RelationshipType.foe),
        _edge(opponent, challenger, RelationshipType.foe),
        _edge(alt, challenger),
        _edge(newbie, challenger),
        _edge(blocked, challenger),
        CharacterBlock(
            blocker_character_id=opponent.id, blocked_character_id=blocked.id
        ),
    ])
    await db_session.flush()
    await _go_live(db_session, duel)

    for viewer in (challenger, opponent, alt, newbie, blocked):
        assert await _duel_live_items(db_session, viewer.id) == [], viewer.username


async def _account_of(db_session, character):
    return await db_session.get(Account, character.account_id)


@pytest.fixture
def keys_on(monkeypatch):
    monkeypatch.setattr(settings, "VAPID_PUBLIC_KEY", PUBLIC)
    monkeypatch.setattr(settings, "VAPID_PRIVATE_KEY", PRIVATE)
    monkeypatch.setattr(settings, "VAPID_CONTACT", "mailto:hi@worldzero.org")


async def _subscribed(db_session, era, username, *, by_push=True, **kwargs):
    character = await _viewer(db_session, era, username, **kwargs)
    account = await _account_of(db_session, character)
    account.notification_prefs = {"duel_live": {"by_push": by_push}}
    db_session.add(
        PushSubscription(
            account_id=account.id,
            endpoint=f"https://fcm.googleapis.com/fcm/send/{username}",
            p256dh="k",
            auth="a",
        )
    )
    await db_session.flush()
    return character


@pytest.mark.asyncio
async def test_push_goes_once_to_each_eligible_recipient(
    db_session: AsyncSession, era, keys_on
):
    duel, challenger, opponent = await _active_duel(db_session, era, "dl4")
    friend = await _subscribed(db_session, era, "dl4f")
    both = await _subscribed(db_session, era, "dl4b")
    muted = await _subscribed(db_session, era, "dl4m", by_push=False)
    newbie = await _subscribed(db_session, era, "dl4n", peak_level=0)
    blocked = await _subscribed(db_session, era, "dl4k")
    alt = await _subscribed(
        db_session, era, "dl4alt", account=await _account_of(db_session, opponent)
    )
    db_session.add_all([
        _edge(alt, challenger),
        _edge(friend, challenger),
        _edge(both, challenger),
        _edge(both, opponent, RelationshipType.foe),
        _edge(muted, opponent),
        _edge(newbie, opponent),
        _edge(blocked, challenger),
        CharacterBlock(
            blocker_character_id=blocked.id, blocked_character_id=opponent.id
        ),
    ])
    await db_session.flush()

    await _go_live(db_session, duel)
    await maybe_settle_duel(duel.opponent_praxis_id, db_session)

    outbox = db_session.sync_session.info.get(push._OUTBOX, [])
    queued = [payload for payload, _ in outbox]
    assert sorted(p["character"] for p in queued) == sorted(
        [friend.display_name, both.display_name]
    )
    assert {p["tag"] for p in queued} == {f"duel_live:{duel.id}"}
    assert {p["url"] for p in queued} == {f"/duel/{duel.id}"}


@pytest.mark.asyncio
async def test_block_with_either_duelist_hides_the_row_from_an_edge_to_the_other(
    db_session: AsyncSession, era
):
    duel, challenger, opponent = await _active_duel(db_session, era, "dl6")
    viewer = await _viewer(db_session, era, "dl6viewer")
    db_session.add_all([
        _edge(viewer, opponent),
        CharacterBlock(
            blocker_character_id=viewer.id, blocked_character_id=challenger.id
        ),
    ])
    await db_session.flush()
    await _go_live(db_session, duel)
    assert await _duel_live_items(db_session, viewer.id) == []


@pytest.mark.asyncio
async def test_a_duel_forfeited_after_going_live_still_shows(
    db_session: AsyncSession, era
):
    duel, challenger, opponent = await _active_duel(db_session, era, "dl7")
    viewer = await _viewer(db_session, era, "dl7viewer")
    db_session.add(_edge(viewer, challenger))
    await db_session.flush()
    await _go_live(db_session, duel)
    duel.forfeited_by_character_id = opponent.id
    duel.forfeited_at = datetime.now(timezone.utc)
    await db_session.flush()
    assert len(await _duel_live_items(db_session, viewer.id)) == 1


@pytest.mark.asyncio
async def test_rows_order_and_page_on_live_at(db_session: AsyncSession, era):
    older, challenger_a, _ = await _active_duel(db_session, era, "dl5a")
    newer, challenger_b, _ = await _active_duel(db_session, era, "dl5b")
    viewer = await _viewer(db_session, era, "dl5v")
    db_session.add_all([_edge(viewer, challenger_a), _edge(viewer, challenger_b)])
    await db_session.flush()
    await _go_live(db_session, older)
    await _go_live(db_session, newer)
    older.live_at = datetime.now(timezone.utc) - timedelta(days=2)
    await db_session.flush()

    keys = [i.item_key for i in await _duel_live_items(db_session, viewer.id)]
    assert keys == [f"duel_live:{newer.id}", f"duel_live:{older.id}"]
    page = await get_activity_feed(
        viewer.id,
        db_session,
        before_cursor=FeedCursor(
            datetime.now(timezone.utc) - timedelta(days=1), FEED_ITEM_TYPE_DUEL_LIVE, 0
        ),
    )
    assert [i.item_key for i in page.items if i.type == FEED_ITEM_TYPE_DUEL_LIVE] == [
        f"duel_live:{older.id}"
    ]


@pytest.mark.asyncio
async def test_feed_challenge_state_matches_duel_detail(db_session: AsyncSession, era):
    duel, challenger, opponent = await _active_duel(db_session, era, "dl9")
    for casts in ("one_cast", "live"):
        if casts == "one_cast":
            (await db_session.get(Praxis, duel.challenger_praxis_id)).status = (
                PraxisStatus.submitted
            )
        else:
            (await db_session.get(Praxis, duel.opponent_praxis_id)).status = (
                PraxisStatus.submitted
            )
        await db_session.flush()
        feed = await get_activity_feed(opponent.id, db_session)
        (item,) = [i for i in feed.items if i.type == "duel_challenge"]
        detail = await get_duel_detail(duel.id, opponent, db_session)
        assert item.payload.duel_state == detail.state
        assert detail.state.value == casts
