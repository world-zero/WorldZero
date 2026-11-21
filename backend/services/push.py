"""Web push (#3678) and notification email (#2164): the shared ``notify()`` fan-out.

Payloads carry keys and values, never English (ADR-0031): the service worker builds
the text from its strings file. Never put ``account_id``, email, photos or star values
in one. Pushes and mail queue on the session and leave only after the commit that
made the event real.
"""

import asyncio
import base64
import json
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from functools import cache, partial
from typing import Awaitable, Callable, Optional

import requests
from cryptography.hazmat.primitives import serialization
from py_vapid import Vapid
from pywebpush import WebPushException, webpush
from sqlalchemy import delete, distinct, event, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from config import settings
from db import AsyncSessionLocal
from game_config import CURRENT_ERA, EraConfig
from models.account import Account, AccountStatus
from models.character import Character, CharacterStatus
from models.comment import Comment, CommentMention
from models.duel import Duel
from models.praxis import ModerationStatus, Praxis, PraxisInvite, PraxisMember
from models.push_subscription import PushSubscription
from models.relationship import Relationship
from models.task import Task
from models.vote import Vote
from services.activity_feed import (
    FEED_ITEM_TYPE_COLLAB_INVITE,
    FEED_ITEM_TYPE_COMMENT_MENTION,
    FEED_ITEM_TYPE_COMMENT_ON_MINE,
    FEED_ITEM_TYPE_DUEL_CHALLENGE,
    FEED_ITEM_TYPE_DUEL_LIVE,
    FEED_ITEM_TYPE_ERA_ANNOUNCEMENT,
    FEED_ITEM_TYPE_GLOBAL_TASK,
    FEED_ITEM_TYPE_INVITATION_LETTER,
    FEED_ITEM_TYPE_RULES_CHANGE,
    FEED_ITEM_TYPE_VOTE_ON_MINE,
)
from services.block_service import blocked_counterpart_ids
from services.email import (
    catalog,
    build_message,
    email_available,
    send_email,
    unsubscribe_token,
)
from services.era_gates import meets_vote_level
from services.notification_prefs import LEVEL_UP, resolve_prefs

logger = logging.getLogger(__name__)

#: Push-service statuses meaning the device is gone for good.
GONE_STATUSES = frozenset({404, 410})
#: How long a push service holds a push for an offline device.
PUSH_TTL_SECONDS = 86400
#: A stalled push service must not hold the serial batch behind it.
PUSH_TIMEOUT_SECONDS = 10
#: Ratings on one praxis inside this window collapse into one "N new ratings".
RATING_COLLAPSE_WINDOW = timedelta(hours=24)

_OUTBOX = "push_outbox"
_EMAIL_OUTBOX = "email_outbox"
_in_flight: set[asyncio.Task] = set()


@cache
def _vapid_problem(public: str, private: str, contact: str) -> Optional[str]:
    """What is wrong with the VAPID config, or None. Cached: logs once per config."""
    if not (public and private and contact):
        return "VAPID_PUBLIC_KEY, VAPID_PRIVATE_KEY and VAPID_CONTACT must all be set"
    if not contact.startswith(("mailto:", "https:")):
        return "VAPID_CONTACT must start with mailto: or https:"
    try:
        derived = Vapid.from_string(private).public_key.public_bytes(
            serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint
        )
    except Exception as error:
        return f"VAPID_PRIVATE_KEY does not parse ({type(error).__name__})"
    if base64.urlsafe_b64encode(derived).rstrip(b"=").decode() != public.rstrip("="):
        return "VAPID_PUBLIC_KEY is not the public half of VAPID_PRIVATE_KEY"
    return None


def push_available() -> bool:
    """On only when the keys are all set and consistent; a broken set logs an ERROR."""
    cfg = (
        settings.VAPID_PUBLIC_KEY,
        settings.VAPID_PRIVATE_KEY,
        settings.VAPID_CONTACT,
    )
    if not (cfg[0] or cfg[1]):  # keys blank on purpose: push is simply off
        return False
    problem = _vapid_problem(*cfg)
    if problem:
        _log_vapid_once(problem)
    return problem is None


@cache
def _log_vapid_once(problem: str) -> None:
    logger.error("Web push is OFF: %s", problem)


@dataclass(frozen=True)
class Target:
    id: int
    endpoint: str
    p256dh: str
    auth: str



async def subscribe_device(
    session: AsyncSession, account_id: int, endpoint: str, p256dh: str, auth: str
) -> None:
    """Idempotent on endpoint. A device belongs to whoever subscribed last: a browser
    holds one subscription per origin, so a shared phone must not keep pushing the
    previous account's events."""
    existing = await session.scalar(
        select(PushSubscription).where(PushSubscription.endpoint == endpoint)
    )
    if existing is None:
        existing = PushSubscription(endpoint=endpoint)
        session.add(existing)
    existing.account_id = account_id
    existing.p256dh = p256dh
    existing.auth = auth


async def unsubscribe_device(
    session: AsyncSession, account_id: int, endpoint: str
) -> None:
    await session.execute(
        delete(PushSubscription).where(
            PushSubscription.endpoint == endpoint,
            PushSubscription.account_id == account_id,
        )
    )


def _send_one(target: Target, body: str) -> None:
    # Zero redirects allowed: a push service never redirects, an attacker's would.
    session = requests.Session()
    session.max_redirects = 0
    webpush(
        requests_session=session,
        subscription_info={
            "endpoint": target.endpoint,
            "keys": {"p256dh": target.p256dh, "auth": target.auth},
        },
        data=body,
        vapid_private_key=settings.VAPID_PRIVATE_KEY,
        # A fresh dict each call: pywebpush writes the audience into it.
        vapid_claims={"sub": settings.VAPID_CONTACT},
        ttl=PUSH_TTL_SECONDS,
        timeout=PUSH_TIMEOUT_SECONDS,
    )


async def deliver(
    batch: list[tuple[dict, list[Target]]],
    session_factory: Callable[[], AsyncSession] = AsyncSessionLocal,
) -> None:
    """Send each payload to each device; drop devices the push service reports gone."""
    gone: list[int] = []
    for payload, targets in batch:
        body = json.dumps(payload)
        for target in targets:
            try:
                await asyncio.to_thread(_send_one, target, body)
            except WebPushException as error:
                status = getattr(error.response, "status_code", None)
                if status in GONE_STATUSES:
                    gone.append(target.id)
                else:
                    logger.error(
                        "push to subscription %s rejected: status=%s reason=%s",
                        target.id,
                        status,
                        (getattr(error.response, "text", "") or str(error))[:200],
                    )
            except Exception:
                logger.exception("push to subscription %s crashed", target.id)
    if gone:
        async with session_factory() as session:
            await session.execute(
                delete(PushSubscription).where(PushSubscription.id.in_(gone))
            )
            await session.commit()


async def deliver_email(batch: list[tuple[str, str, dict]]) -> None:
    """Send each queued ``(kind, to, message)``. A failure is logged and lost, never retried."""
    for kind, to, message in batch:
        try:
            await send_email(to, **message)
        except Exception:
            # Never log the address: it is the one thing a log must not hold.
            logger.exception("email for %s failed", kind)


@event.listens_for(Session, "after_commit")
def _send_queued(session: Session) -> None:
    for outbox, send in ((_OUTBOX, deliver), (_EMAIL_OUTBOX, deliver_email)):
        batch = session.info.pop(outbox, None)
        if batch:
            task = asyncio.get_running_loop().create_task(send(batch))
            _in_flight.add(task)
            task.add_done_callback(_in_flight.discard)


@event.listens_for(Session, "after_rollback")
def _drop_queued(session: Session) -> None:
    session.info.pop(_OUTBOX, None)
    session.info.pop(_EMAIL_OUTBOX, None)


async def notify(
    session: AsyncSession,
    *,
    kind: str,
    recipient_id: int,
    tag: str,
    url: str,
    actor: Optional[Character] = None,
    task_title: Optional[str] = None,
    count: Optional[int] = None,
    faction: Optional[str] = None,
) -> None:
    """Queue a push and/or an email for a character's account, each if on and wanted."""
    push_on, email_on = push_available(), email_available()
    if not (push_on or email_on):
        return
    recipient = await session.get(Character, recipient_id)
    if recipient is None or recipient.status != CharacterStatus.active:
        return
    if actor is not None and actor.id in set(
        (await session.scalars(blocked_counterpart_ids(recipient_id))).all()
    ):
        return
    account = await session.get(Account, recipient.account_id)
    if account is None or account.status != AccountStatus.active:
        return
    pref = resolve_prefs(account.notification_prefs)[kind]
    # ponytail: only the single-recipient rows have mail wording (email.json); the
    # broadcast rows (era announcement, rules change, global task) stay unwired for
    # email. A mailing to everyone needs batching and rate limits first.
    if email_on and pref.by_email and account.email and kind in catalog()["kinds"]:
        # ponytail: one mail per rating, no collapsing like push; the row is opt-in.
        message = build_message(
            kind=kind,
            token=unsubscribe_token(account.id, kind),
            url=url,
            actor=actor.display_name if actor else None,
            task_title=task_title,
            faction=faction,
        )
        session.sync_session.info.setdefault(_EMAIL_OUTBOX, []).append(
            (kind, account.email, message)
        )
    if push_on and pref.by_push:
        await _queue_push(
            session,
            recipient,
            {
                "kind": kind,
                "tag": tag,
                "url": url,
                "character": recipient.display_name,
                "actor": actor.display_name if actor else None,
                "task": task_title,
                "count": count,
                "faction": faction,
            },
        )


async def _queue_push(
    session: AsyncSession, recipient: Character, payload: dict
) -> None:
    subscriptions = (
        await session.scalars(
            select(PushSubscription).where(
                PushSubscription.account_id == recipient.account_id
            )
        )
    ).all()
    if not subscriptions:
        return
    targets = [Target(s.id, s.endpoint, s.p256dh, s.auth) for s in subscriptions]
    session.sync_session.info.setdefault(_OUTBOX, []).append((payload, targets))


async def _task_title(session: AsyncSession, task_id: int) -> Optional[str]:
    task = await session.get(Task, task_id)
    return task.title if task else None


async def _praxis_owner_ids(session: AsyncSession, praxis: Praxis) -> set[int]:
    members = await session.scalars(
        select(PraxisMember.character_id).where(PraxisMember.praxis_id == praxis.id)
    )
    return {praxis.created_by_id, *members.all()}


async def notify_vote(session: AsyncSession, praxis: Praxis, voter: Character) -> None:
    since = datetime.now(timezone.utc) - RATING_COLLAPSE_WINDOW
    recent = await session.scalar(
        select(func.count())
        .select_from(Vote)
        .where(Vote.praxis_id == praxis.id, Vote.updated_at >= since)
    )
    title = await _task_title(session, praxis.task_id)
    for recipient_id in await _praxis_owner_ids(session, praxis):
        await notify(
            session,
            kind=FEED_ITEM_TYPE_VOTE_ON_MINE,
            recipient_id=recipient_id,
            tag=f"{FEED_ITEM_TYPE_VOTE_ON_MINE}:{praxis.id}",
            url=f"/praxis/{praxis.id}",
            actor=voter,
            task_title=title,
            count=recent if recent and recent > 1 else None,
        )


async def notify_comment(
    session: AsyncSession,
    author: Character,
    *,
    comment_id: int,
    praxis_id: Optional[int],
    task_id: Optional[int],
    mentioned: list[Character],
) -> None:
    """Mentions get the mention row; a praxis's own people get comment-on-mine, once."""
    praxis = await session.get(Praxis, praxis_id) if praxis_id else None
    title = await _task_title(session, praxis.task_id if praxis else task_id)
    page = f"/praxis/{praxis_id}" if praxis_id else f"/tasks/{task_id}"
    url = f"{page}#comment-{comment_id}"
    target = f"praxis:{praxis_id}" if praxis_id else f"task:{task_id}"
    since = datetime.now(timezone.utc) - RATING_COLLAPSE_WINDOW
    on_target = (
        Comment.praxis_id == praxis_id if praxis_id else Comment.task_id == task_id
    )
    live = (
        on_target,
        Comment.created_at >= since,
        Comment.is_withdrawn.is_(False),
        Comment.moderation_status == ModerationStatus.visible,
    )
    recipients = {c.id: FEED_ITEM_TYPE_COMMENT_MENTION for c in mentioned}
    if praxis is not None:
        for owner_id in await _praxis_owner_ids(session, praxis) - {author.id}:
            recipients.setdefault(owner_id, FEED_ITEM_TYPE_COMMENT_ON_MINE)
    for recipient_id, kind in recipients.items():
        if kind == FEED_ITEM_TYPE_COMMENT_MENTION:
            recent = await session.scalar(
                select(func.count(distinct(Comment.created_by_id)))
                .select_from(CommentMention)
                .join(Comment, Comment.id == CommentMention.comment_id)
                .where(CommentMention.mentioned_character_id == recipient_id, *live)
            )
        else:
            recent = await session.scalar(
                select(func.count(distinct(Comment.created_by_id)))
                .select_from(Comment)
                .where(Comment.created_by_id != recipient_id, *live)
            )
        await notify(
            session,
            kind=kind,
            recipient_id=recipient_id,
            tag=f"{kind}:{target}",
            url=url,
            actor=author,
            task_title=title,
            count=recent if recent and recent > 1 else None,
        )


async def notify_collab_invite(
    session: AsyncSession, invite: PraxisInvite, inviter: Character
) -> None:
    praxis = await session.get(Praxis, invite.praxis_id)
    await notify(
        session,
        kind=FEED_ITEM_TYPE_COLLAB_INVITE,
        recipient_id=invite.invitee_id,
        tag=f"{FEED_ITEM_TYPE_COLLAB_INVITE}:{invite.praxis_id}",
        url="/updates",
        actor=inviter,
        task_title=await _task_title(session, praxis.task_id) if praxis else None,
    )


async def notify_duel_challenge(
    session: AsyncSession, duel_id: int, challenger_praxis: Praxis, opponent_id: int
) -> None:
    challenger = await session.get(Character, challenger_praxis.created_by_id)
    await notify(
        session,
        kind=FEED_ITEM_TYPE_DUEL_CHALLENGE,
        recipient_id=opponent_id,
        tag=f"{FEED_ITEM_TYPE_DUEL_CHALLENGE}:{duel_id}",
        url=f"/duel/{duel_id}",
        actor=challenger,
        task_title=await _task_title(session, challenger_praxis.task_id),
    )


async def notify_duel_live(
    session: AsyncSession, duel: Duel, era: EraConfig = CURRENT_ERA
) -> None:
    """Anyone with a friend/foe edge to either duelist, once, as it goes live (#3886).

    The same three exclusions as the ``duel_live`` feed row. ``notify`` checks
    blocks against the challenger only, so the opponent's are checked here.
    """
    challenger_praxis = await session.get(Praxis, duel.challenger_praxis_id)
    challenger = await session.get(Character, challenger_praxis.created_by_id)
    duelist_ids = {challenger.id, duel.opponent_character_id}
    recipients = await session.scalars(
        select(Character)
        .join(Relationship, Relationship.from_character_id == Character.id)
        .where(
            Relationship.to_character_id.in_(duelist_ids),
            Character.account_id.not_in(
                select(Character.account_id).where(Character.id.in_(duelist_ids))
            ),
        )
        .distinct()
        .order_by(Character.id)
    )
    title = await _task_title(session, duel.task_id)
    for recipient in recipients.all():
        if not meets_vote_level(recipient.peak_level, era):
            continue
        blocked = set(
            (await session.scalars(blocked_counterpart_ids(recipient.id))).all()
        )
        if blocked & duelist_ids:
            continue
        await notify(
            session,
            kind=FEED_ITEM_TYPE_DUEL_LIVE,
            recipient_id=recipient.id,
            tag=f"{FEED_ITEM_TYPE_DUEL_LIVE}:{duel.id}",
            url=f"/duel/{duel.id}",
            actor=challenger,
            task_title=title,
        )


async def notify_invitation_letter(
    session: AsyncSession, character: Character, faction_slug: str
) -> None:
    await notify(
        session,
        kind=FEED_ITEM_TYPE_INVITATION_LETTER,
        recipient_id=character.id,
        tag=f"{FEED_ITEM_TYPE_INVITATION_LETTER}:{character.id}:{faction_slug}",
        url="/updates",
        faction=faction_slug,
    )


async def notify_level_up(session: AsyncSession, character: Character) -> None:
    await notify(
        session,
        kind=LEVEL_UP,
        recipient_id=character.id,
        tag=f"{LEVEL_UP}:{character.id}",
        url=f"/characters/{character.id}",
    )


async def notify_broadcast(
    session: AsyncSession, *, kind: str, tag: str, url: str
) -> None:
    """For the ambient rows (era announcement, rules change, global task): every
    character with a device. ponytail: no call site yet; those rows default off."""
    owners = await session.scalars(
        select(func.min(Character.id))
        .where(Character.account_id.in_(select(PushSubscription.account_id)))
        .group_by(Character.account_id)
    )
    for recipient_id in owners.all():
        await notify(session, kind=kind, recipient_id=recipient_id, tag=tag, url=url)


#: Every preference row's sender; a test pins this to ``NOTIFICATION_EVENTS``.
SENDERS: dict[str, Callable[..., Awaitable[None]]] = {
    FEED_ITEM_TYPE_VOTE_ON_MINE: notify_vote,
    FEED_ITEM_TYPE_COMMENT_ON_MINE: notify_comment,
    FEED_ITEM_TYPE_COMMENT_MENTION: notify_comment,
    FEED_ITEM_TYPE_COLLAB_INVITE: notify_collab_invite,
    FEED_ITEM_TYPE_DUEL_CHALLENGE: notify_duel_challenge,
    FEED_ITEM_TYPE_DUEL_LIVE: notify_duel_live,
    FEED_ITEM_TYPE_INVITATION_LETTER: notify_invitation_letter,
    LEVEL_UP: notify_level_up,
    FEED_ITEM_TYPE_ERA_ANNOUNCEMENT: partial(
        notify_broadcast, kind=FEED_ITEM_TYPE_ERA_ANNOUNCEMENT
    ),
    FEED_ITEM_TYPE_RULES_CHANGE: partial(
        notify_broadcast, kind=FEED_ITEM_TYPE_RULES_CHANGE
    ),
    FEED_ITEM_TYPE_GLOBAL_TASK: partial(
        notify_broadcast, kind=FEED_ITEM_TYPE_GLOBAL_TASK
    ),
}
