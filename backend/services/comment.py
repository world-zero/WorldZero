"""Service layer for comments (ADR-0006).

Flat (replies via @mention), not votable, on exactly one praxis or task.
"""
import re
from typing import Optional

from fastapi import HTTPException
from sqlalchemy import and_, delete, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from dependencies import account_has_admin_role
from errors import DETAIL_CONTEXT_PARAM, ErrorCode, raise_coded
from game_config import CURRENT_ERA, EraConfig
from models.character import Character
from models.comment import (
    MAX_COMMENT_BODY,
    MAX_MENTIONS_PER_COMMENT,
    Comment,
    CommentMention,
)
from models.flag import Flag, FlagReason
from models.praxis import ModerationStatus, Praxis
from models.task import TaskStatus
from schemas.comment import CommentAuthor, CommentMentionOut, CommentOut
from services.block_service import blocked_by
from services.era import get_current_era_row, get_or_create_stats
from services.era_gates import may_comment
from services.mod_log import log_mod_action
from services.praxis import (
    account_already_flagged,
    can_view_praxis,
    refuse_if_under_review,
    resolve_flags,
)
from services.push import notify_comment
from services.standing import public_identity
from services.task import get_task_for_viewer

# Unresolved handles stay plain text; render linkifies the resolved set only.
MENTION_RE = re.compile(r"@([A-Za-z0-9_]+)")

_COMMENT_LOADERS = (
    selectinload(Comment.created_by),
    selectinload(Comment.mentions).selectinload(CommentMention.mentioned_character),
)


async def _character_level(character_id: int, session: AsyncSession) -> int:
    era_row = await get_current_era_row(session)
    stats = await get_or_create_stats(session, character_id, era_row.id)
    return stats.level


async def can_comment(
    viewer: Optional[Character],
    session: AsyncSession,
    era: EraConfig = CURRENT_ERA,
) -> bool:
    """Enforcement half of ``/auth/me``'s ``can_comment``: the same predicate,
    so flag and enforcement cannot drift (#2868)."""
    if viewer is None:
        return False
    return may_comment(
        await _character_level(viewer.id, session),
        viewer.faction_slug,
        await account_has_admin_role(viewer.account_id, session),
        era,
    )


async def _viewer_sees_target(
    viewer: Character, comment: Comment, session: AsyncSession
) -> bool:
    if comment.praxis_id is None:
        return True
    praxis = await session.get(Praxis, comment.praxis_id)
    return praxis is not None and await can_view_praxis(viewer, praxis, session)


async def get_comment(
    comment_id: int,
    session: AsyncSession,
    *,
    removed_is_missing: bool = False,
    viewer: Optional[Character] = None,
) -> Comment:
    result = await session.execute(
        select(Comment)
        .options(*_COMMENT_LOADERS)
        # So an edit's reconciled mentions replace the stale loaded collection.
        .execution_options(populate_existing=True)
        .where(Comment.id == comment_id)
    )
    comment = result.scalar_one_or_none()
    # A removed or hidden-praxis comment answers as a missing one, so a flagger
    # can't tell them apart.
    removed = (
        comment is not None
        and removed_is_missing
        and comment.moderation_status
        in (ModerationStatus.hidden, ModerationStatus.deleted)
    )
    if (
        comment is None
        or removed
        or (viewer and not await _viewer_sees_target(viewer, comment, session))
    ):
        raise HTTPException(status_code=404, detail="Comment not found.")
    return comment


async def _resolve_mentions(
    body_text: str, author: Character, session: AsyncSession
) -> list[Character]:
    """Resolve @username handles to Characters, case-insensitive, excluding self."""
    ordered = dict.fromkeys(h.lower() for h in MENTION_RE.findall(body_text))
    handles = set(list(ordered)[:MAX_MENTIONS_PER_COMMENT])
    if not handles:
        return []
    result = await session.execute(
        select(Character).where(func.lower(Character.username).in_(handles))
    )
    return [c for c in result.scalars().all() if c.id != author.id]


async def _reconcile_mentions(
    comment: Comment, mentioned: list[Character], session: AsyncSession
) -> None:
    """Bulk DELETE + re-insert: mutating an unloaded async relationship would
    lazy-load illegally. Caller re-queries with populate_existing."""
    await session.execute(
        delete(CommentMention)
        .where(CommentMention.comment_id == comment.id)
        .execution_options(synchronize_session=False)
    )
    for character in mentioned:
        session.add(
            CommentMention(
                comment_id=comment.id, mentioned_character_id=character.id
            )
        )


def _author_out(character: Character) -> CommentAuthor:
    identity = public_identity(character)
    return CommentAuthor(
        id=character.id,
        username=identity.username,
        display_name=identity.display_name,
        avatar_url=identity.avatar_url,
        faction_slug=character.faction_slug,
        name_state=identity.name_state,
    )


def _clean_body(body_text: str) -> str:
    body_text = body_text.strip()
    if not body_text:
        raise HTTPException(status_code=422, detail="Comment cannot be empty.")
    if len(body_text) > MAX_COMMENT_BODY:
        raise HTTPException(
            status_code=422,
            detail=f"Comment exceeds {MAX_COMMENT_BODY} characters.",
        )
    return body_text


async def _assert_commentable_target(
    praxis_id: Optional[int],
    task_id: Optional[int],
    session: AsyncSession,
    author: Optional[Character] = None,
    era: EraConfig = CURRENT_ERA,
) -> None:
    """Exactly one target, open for comments: a visible praxis or task."""
    if (praxis_id is None) == (task_id is None):
        raise_coded(
            422,
            ErrorCode.comment_target_ambiguous,
            "A comment targets exactly one of a praxis or a task.",
        )
    if praxis_id is not None:
        # Same can_view_praxis gate as the read path (ADR-0024, #999). Absent and
        # invisible share ONE raise so it is not an existence oracle.
        praxis = await session.get(Praxis, praxis_id)
        if praxis is None or (
            author is not None and not await can_view_praxis(author, praxis, session)
        ):
            raise_coded(404, ErrorCode.praxis_not_found, "Praxis not found.")
        if praxis.moderation_status != ModerationStatus.visible:
            raise_coded(
                403,
                ErrorCode.praxis_not_open_for_comments,
                "This praxis is not open for comments.",
            )
    else:
        # Same visibility gate as GET /tasks/{id}; withheld answers 404 like absent.
        task = await get_task_for_viewer(session, task_id, author, era=era)
        if task is None:
            raise_coded(404, ErrorCode.task_not_found, "Task not found.")
        if task.status is TaskStatus.backdoor:
            raise_coded(
                403,
                ErrorCode.task_not_open_for_comments,
                "This task is not open for comments.",
            )


async def create_comment(
    author: Character,
    *,
    praxis_id: Optional[int] = None,
    task_id: Optional[int] = None,
    body_text: str,
    session: AsyncSession,
    era: EraConfig = CURRENT_ERA,
) -> Comment:
    if not await can_comment(author, session, era):
        raise_coded(
            403,
            ErrorCode.comment_level_too_low,
            f"Must be level {era.comment_level_required} or above to comment.",
            {"level": era.comment_level_required},
        )
    body_text = _clean_body(body_text)
    await _assert_commentable_target(
        praxis_id, task_id, session, author=author, era=era
    )

    comment = Comment(
        praxis_id=praxis_id,
        task_id=task_id,
        created_by_id=author.id,
        body_text=body_text,
    )
    session.add(comment)
    await session.flush()

    mentioned = await _resolve_mentions(body_text, author, session)
    await _reconcile_mentions(comment, mentioned, session)
    await session.flush()
    await notify_comment(
        session,
        author,
        comment_id=comment.id,
        praxis_id=praxis_id,
        task_id=task_id,
        mentioned=mentioned,
    )
    return await get_comment(comment.id, session)


async def edit_comment(
    comment_id: int, author: Character, body_text: str, session: AsyncSession
) -> Comment:
    comment = await get_comment(comment_id, session)
    if comment.created_by_id != author.id:
        raise HTTPException(
            status_code=403, detail="Cannot edit another character's comment."
        )
    refuse_if_under_review(comment)
    body_text = _clean_body(body_text)

    comment.body_text = body_text
    comment.is_edited = True
    await _reconcile_mentions(
        comment, await _resolve_mentions(body_text, author, session), session
    )
    await session.flush()
    return await get_comment(comment_id, session)


async def withdraw_comment(
    comment_id: int, author: Character, session: AsyncSession
) -> None:
    """Author soft-delete."""
    comment = await get_comment(comment_id, session)
    if comment.created_by_id != author.id:
        raise HTTPException(
            status_code=403, detail="Cannot delete another character's comment."
        )
    comment.is_withdrawn = True
    await session.flush()


async def list_comments(
    *,
    praxis_id: Optional[int] = None,
    task_id: Optional[int] = None,
    session: AsyncSession,
    viewer_id: Optional[int] = None,
) -> list[Comment]:
    """Visible, non-withdrawn, oldest first; plus the viewer's own removed
    comments that carry a reason, so the author is told why."""
    own_removed = and_(
        Comment.created_by_id == viewer_id,
        Comment.moderation_status.in_(
            (ModerationStatus.hidden, ModerationStatus.deleted)
        ),
        Comment.admin_note.is_not(None),
    )
    query = (
        select(Comment)
        .options(*_COMMENT_LOADERS)
        .where(
            Comment.is_withdrawn.is_(False),
            or_(Comment.moderation_status == ModerationStatus.visible, own_removed),
        )
        .order_by(Comment.created_at.asc())
    )
    if praxis_id is not None:
        query = query.where(Comment.praxis_id == praxis_id)
    if task_id is not None:
        query = query.where(Comment.task_id == task_id)
    result = await session.execute(query)
    return list(result.scalars().all())


async def flag_comment(
    comment_id: int,
    flagged_by: Character,
    reason: FlagReason,
    session: AsyncSession,
    reason_detail: Optional[str] = None,
    era: EraConfig = CURRENT_ERA,
) -> Comment:
    """Flag for moderation; mirrors :func:`services.praxis.flag_praxis`."""
    comment = await get_comment(
        comment_id, session, removed_is_missing=True, viewer=flagged_by
    )

    # Account-scoped (#328): the review threshold is 1, so a second life could
    # otherwise queue its own account's comment.
    author = comment.created_by
    if author is not None and author.account_id == flagged_by.account_id:
        raise HTTPException(status_code=403, detail="Cannot flag your own comment.")
    if await account_already_flagged(
        flagged_by.account_id, session, comment_id=comment.id
    ):
        raise_coded(
            409,
            ErrorCode.comment_already_flagged,
            "Your account has already flagged this comment.",
        )

    if await _character_level(flagged_by.id, session) < era.flag_level_required:
        raise_coded(
            403,
            ErrorCode.flag_level_too_low,
            f"Must be level {era.flag_level_required} or above to flag a comment.",
            {"level": era.flag_level_required, DETAIL_CONTEXT_PARAM: "comment"},
        )
    session.add(
        Flag(
            comment_id=comment.id,
            flagged_by_id=flagged_by.id,
            reason=reason.value,
            reason_detail=reason_detail,
        )
    )
    await session.flush()

    count_result = await session.execute(
        select(func.count())
        .select_from(Flag)
        .where(Flag.comment_id == comment.id, Flag.resolved_at.is_(None))
    )
    if count_result.scalar_one() >= era.comment_flag_review_threshold:
        comment.moderation_status = ModerationStatus.flagged
        await session.flush()
    return await get_comment(comment_id, session)


async def moderate_comment(
    comment_id: int,
    new_status: str,
    session: AsyncSession,
    *,
    actor_id: int,
    admin_note: Optional[str] = None,
) -> Comment:
    """Admin moderation: hidden (reversible hold) / deleted (tombstone) / visible."""
    comment = await get_comment(comment_id, session)
    try:
        status = ModerationStatus(new_status)
    except ValueError:
        raise HTTPException(
            status_code=422, detail=f"Invalid moderation status: {new_status}"
        )
    if comment.moderation_status == ModerationStatus.deleted:
        raise_coded(
            409,
            ErrorCode.comment_already_deleted,
            "That comment was already deleted. Nothing was changed.",
        )
    comment.moderation_status = status
    if status != ModerationStatus.flagged:
        await resolve_flags(session, Flag.comment_id == comment_id)
    removed = comment.moderation_status in (
        ModerationStatus.hidden,
        ModerationStatus.deleted,
    )
    note = (admin_note or "").strip() or None if removed else None
    comment.admin_note = note
    await session.flush()
    await log_mod_action(
        session, actor_id, f"comment_{new_status}", "comment", comment_id, note
    )
    return await get_comment(comment_id, session)


async def list_flagged_comments(session: AsyncSession) -> list[Comment]:
    result = await session.execute(
        select(Comment)
        .options(*_COMMENT_LOADERS)
        .where(Comment.moderation_status == ModerationStatus.flagged)
        .order_by(Comment.created_at.desc())
    )
    return list(result.scalars().all())


async def list_comment_outs(
    *,
    praxis_id: Optional[int] = None,
    task_id: Optional[int] = None,
    session: AsyncSession,
    viewer_id: Optional[int] = None,
) -> list[CommentOut]:
    """A thread as the viewer reads it: authors they blocked come back censored."""
    comments = await list_comments(
        praxis_id=praxis_id, task_id=task_id, session=session, viewer_id=viewer_id
    )
    blocked = await blocked_by(viewer_id, session) if viewer_id is not None else set()
    return [
        build_comment_out(comment, viewer_id, censored=comment.created_by_id in blocked)
        for comment in comments
    ]


def build_comment_out(
    comment: Comment, viewer_id: Optional[int] = None, *, censored: bool = False
) -> CommentOut:
    """API shape; needs created_by + mentions loaded. Shared by both routers.

    The moderator's reason goes to the author alone. ``censored`` (#3867) drops
    the body server-side: blanking it in the client would still ship it.
    """
    return CommentOut(
        id=comment.id,
        praxis_id=comment.praxis_id,
        task_id=comment.task_id,
        body_text="" if censored else comment.body_text,
        is_censored=censored,
        is_edited=comment.is_edited,
        created_at=comment.created_at,
        updated_at=comment.updated_at,
        author=_author_out(comment.created_by),
        admin_note=comment.admin_note if viewer_id == comment.created_by_id else None,
        mentions=[
            CommentMentionOut(
                character_id=mention.mentioned_character.id,
                username=public_identity(mention.mentioned_character).username,
                display_name=public_identity(mention.mentioned_character).display_name,
                name_state=public_identity(mention.mentioned_character).name_state,
            )
            for mention in comment.mentions
            if not censored
        ],
    )
