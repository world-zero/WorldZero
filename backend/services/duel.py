"""Duel service — challenge flow for two-linked-praxes duels (ADR-0011).

Two solo praxes linked by a Duel row: pending → active → settled, or declined.
Praxis-id-keyed helpers live in ``services.praxis_duel`` (#2872).
"""

from datetime import datetime, timedelta, timezone
from typing import Iterable, Optional

from fastapi import HTTPException
from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from errors import DETAIL_CONTEXT_PARAM, ErrorCode, raise_coded
from faction_slugs import UNAFFILIATED_FACTION_SLUG
from game_config import CURRENT_ERA, EraConfig
from models.character import Character, NameState
from models.duel import Duel, DuelStatus
from models.praxis import (
    ModerationStatus,
    Praxis,
    PraxisMember,
    PraxisStatus,
    PraxisType,
)
from models.task import Task, TaskStatus
from services.standing import public_identity
from schemas.duel import DuelDetailOut, DuelSideOut
from services.block_service import refuse_if_blocked
from services.backdoor import settle_closed_backdoors
from services.character import is_playable
from services.relationship_service import are_rivals
from services.scoring import compute_duel_multiplier
from services.character_stats import recalculate_character_stats
from services.nudge import latest_nudge_at, nudge_again_at
from services.vote_tally import get_tally, tally_votes
from services.era import get_current_era_row, get_or_create_stats
from services.duel_state import ALLOWED_FROM, DuelState, challenge_lapsed, duel_state
from services.era_gates import may_create_duel
from services.praxis import _lock_signups_for_character, get_praxis
from services.praxis_duel import (
    duel_state_of,
    forfeit_duel,
    get_duel_for_praxis,
    maybe_settle_duel,
)
from services.push import notify_duel_challenge
from services.signup_eligibility import (
    count_in_progress_praxes,
    is_active_member_of_task,
    task_status_closed,
)


# ADR-0041, #1237: shared by the challenge and accept guards.
SELF_DUEL_DETAIL = "You cannot duel your own character."


async def _characters_share_account(
    first_character_id: int,
    second_character_id: int,
    session: AsyncSession,
) -> bool:
    """Whether two characters belong to the same account (ADR-0041).

    A missing character returns False so callers raise their own 404.
    """
    if first_character_id == second_character_id:
        return True
    first = await session.get(Character, first_character_id)
    second = await session.get(Character, second_character_id)
    if first is None or second is None:
        return False
    return first.account_id == second.account_id


async def forfeit_duels_for_character(
    character_id: int,
    session: AsyncSession,
    era: EraConfig = CURRENT_ERA,
) -> None:
    """Self-delete's duel forfeit (ADR-0011, #3766): forfeit, then re-score.

    Admin ban/suspend use ``forfeit_duels_collect`` plus
    ``recalculate_for_account_votes`` instead, silently (no taunts). Sticky: the
    first forfeit stands.
    """
    await _rescore(
        await forfeit_duels_collect([character_id], session),
        session,
        era,
        emit_taunts=True,
    )


async def forfeit_duels_collect(
    character_ids: Iterable[int], session: AsyncSession
) -> set[int]:
    """Forfeit without re-scoring; the caller re-scores the returned ids in one pass."""
    rescore_ids: set[int] = set()
    for character_id in sorted(set(character_ids)):
        rescore_ids |= await _forfeit_duels(character_id, session)
    return rescore_ids


async def _rescore(
    character_ids: set[int],
    session: AsyncSession,
    era: EraConfig,
    *,
    emit_taunts: bool,
) -> None:
    if not character_ids:
        return
    era_row = await get_current_era_row(session)
    # Ascending: votes lock stats in id order; another order can deadlock.
    for character_id in sorted(character_ids):
        await recalculate_character_stats(
            character_id, session, era, era_row=era_row, emit_taunts=emit_taunts
        )
    await session.flush()


async def _forfeit_duels(character_id: int, session: AsyncSession) -> set[int]:
    """Forfeit one character's duels; return the ids that need re-scoring."""
    own_praxis_ids = select(Praxis.id).where(Praxis.created_by_id == character_id)
    duels = (await session.execute(
        select(Duel).where(
            Duel.status.in_(
                [DuelStatus.pending, DuelStatus.active, DuelStatus.settled]
            ),
            Duel.forfeited_by_character_id.is_(None),
            or_(
                Duel.opponent_character_id == character_id,
                Duel.challenger_praxis_id.in_(own_praxis_ids),
            ),
        )
    )).scalars().all()
    return await _apply_forfeits([(duel, character_id) for duel in duels], session)


async def _apply_forfeits(
    forfeits: list[tuple[Duel, int]], session: AsyncSession
) -> set[int]:
    """The one forfeit path: ``(duel, forfeiter)`` pairs; returns ids to re-score."""
    now = datetime.now(timezone.utc)
    rescore_ids: set[int] = set()
    for duel, forfeiter_id in forfeits:
        forfeit_duel(duel, forfeiter_id, now)
        if duel.status == DuelStatus.pending:
            duel.status = DuelStatus.declined
            duel.declined_at = now
            continue
        challenger_praxis = await session.get(Praxis, duel.challenger_praxis_id)
        challenger_character_id = (
            challenger_praxis.created_by_id if challenger_praxis else None
        )
        winner_id = (
            duel.opponent_character_id
            if challenger_character_id == forfeiter_id
            else challenger_character_id
        )
        rescore_ids |= {forfeiter_id} | ({winner_id} - {None})
        if duel.status == DuelStatus.active:
            await maybe_settle_duel(duel.challenger_praxis_id, session)
    await session.flush()
    return rescore_ids


async def _challenge_unanswerable(
    duel: Duel, session: AsyncSession, era: EraConfig
) -> bool:
    """A pending challenge the opponent could no longer accept (#3875)."""
    opponent = await session.get(Character, duel.opponent_character_id)
    task = await session.get(Task, duel.task_id)
    if opponent is None or task is None:
        return True
    if task_status_closed(task, opponent, era):
        return True
    if await is_active_member_of_task(opponent, task, session, era):
        return True
    era_row = await get_current_era_row(session)
    stats = await get_or_create_stats(session, opponent.id, era_row.id)
    return not may_create_duel(stats.level, None, False, era)


async def _opponent_praxis(duel: Duel, session: AsyncSession) -> Optional[Praxis]:
    if duel.opponent_praxis_id is None:
        return None
    return await session.get(Praxis, duel.opponent_praxis_id)


def _cast_clock(
    duel: Duel, challenger: Optional[Praxis], opponent: Optional[Praxis]
) -> Optional[tuple[Praxis, datetime]]:
    """``(the side that cast, when the other's clock started)``: only while an
    accepted duel has exactly one side cast. Unsubmitting stops it; the next
    cast restarts it, since ``submitted_at`` is re-stamped on every seal."""
    if duel.status != DuelStatus.active or duel.accepted_at is None:
        return None
    cast = [
        p for p in (challenger, opponent)
        if p is not None and p.status == PraxisStatus.submitted
    ]
    if len(cast) != 1:
        return None
    return cast[0], max(duel.accepted_at, cast[0].submitted_at or duel.accepted_at)


async def settle_lapsed_duels(
    session: AsyncSession, era: EraConfig = CURRENT_ERA
) -> bool:
    """Lazy-on-read timeouts, like the collab window (#3875). **This one writes.**

    A pending challenge lapses to declined (unanswered for
    ``duel_challenge_lapse_days``, or no longer acceptable). In an accepted duel
    the cast clock starts at the first cast (or acceptance, if later); the side
    that hasn't cast ``duel_cast_lapse_days`` later forfeits, whichever side it
    is. Neither side cast, or both: no clock. A ``None`` window never lapses.
    Candidates are picked lock-free; only those lock, in ascending id order (#3877),
    and are re-checked. Returns whether any row was re-read (callers reload).

    ponytail: scans every live duel per call; add a deadline-column index or a
    sweep job if the live-duel count ever stops being small.
    """
    now = datetime.now(timezone.utc)

    async def lapse(duel: Duel) -> Optional[tuple[str, Optional[int]]]:
        if duel.status == DuelStatus.pending:
            if challenge_lapsed(duel, now, era) or await _challenge_unanswerable(
                duel, session, era
            ):
                return "decline", None
        elif (
            duel.status == DuelStatus.active
            and duel.accepted_at is not None
            and era.duel_cast_lapse_days is not None
        ):
            challenger = await session.get(Praxis, duel.challenger_praxis_id)
            opponent = await _opponent_praxis(duel, session)
            if duel_state(duel, challenger, opponent, now, era) != DuelState.ONE_CAST:
                return None
            clock = _cast_clock(duel, challenger, opponent)
            if clock and now >= clock[1] + timedelta(days=era.duel_cast_lapse_days):
                late = (
                    duel.opponent_character_id
                    if clock[0] is challenger
                    else challenger.created_by_id
                )
                return "forfeit", late
        return None

    live = (await session.execute(
        select(Duel).where(Duel.status.in_([DuelStatus.pending, DuelStatus.active]))
    )).scalars().all()
    candidate_ids = [duel.id for duel in live if await lapse(duel)]
    if not candidate_ids:
        return False
    duels = (await session.execute(
        select(Duel)
        .where(Duel.id.in_(candidate_ids))
        .order_by(Duel.id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )).scalars().all()

    forfeits: list[tuple[Duel, int]] = []
    for duel in duels:
        verdict = await lapse(duel)
        if verdict is None:
            continue
        if verdict[0] == "decline":
            duel.status = DuelStatus.declined
            duel.declined_at = now
        else:
            forfeits.append((duel, verdict[1]))
    await _rescore(
        await _apply_forfeits(forfeits, session), session, era, emit_taunts=False
    )
    await session.flush()
    return bool(duels)


async def get_duel(duel_id: int, session: AsyncSession, lock: bool = False) -> Duel:
    """``lock``: a concurrent transition waits, then sees this one's result."""
    query = select(Duel).where(Duel.id == duel_id)
    if lock:
        query = query.with_for_update().execution_options(populate_existing=True)
    duel = await session.scalar(query)
    if duel is None:
        raise HTTPException(status_code=404, detail="Duel not found.")
    return duel


def _faction_slug_of(character: Optional[Character]) -> str:
    if character is None:
        return UNAFFILIATED_FACTION_SLUG
    return character.faction_slug or UNAFFILIATED_FACTION_SLUG


async def get_duel_detail(
    duel_id: int,
    viewer: Optional[Character],
    session: AsyncSession,
    era: EraConfig = CURRENT_ERA,
) -> DuelDetailOut:
    """Both sides' display info and live vote points, never a body (#308).
    ``viewer`` keys the per-side nudge state."""
    await settle_lapsed_duels(session, era)
    duel = await get_duel(duel_id, session)

    challenger_praxis = await session.get(Praxis, duel.challenger_praxis_id)
    opponent_praxis = await _opponent_praxis(duel, session)
    challenger_character = (
        await session.get(Character, challenger_praxis.created_by_id)
        if challenger_praxis is not None
        else None
    )
    opponent_character = await session.get(Character, duel.opponent_character_id)

    praxis_ids = [
        pid
        for pid in (duel.challenger_praxis_id, duel.opponent_praxis_id)
        if pid is not None
    ]
    tallies = await tally_votes(praxis_ids, session)

    # Per side (#1083): the nudge rate limit is keyed per praxis.
    async def _nudged_at(
        character: Optional[Character], praxis_id: Optional[int]
    ) -> Optional[datetime]:
        if viewer is None or character is None or praxis_id is None:
            return None
        return await latest_nudge_at(praxis_id, viewer.id, character.id, session)

    challenger_nudged_at = await _nudged_at(
        challenger_character, duel.challenger_praxis_id
    )
    opponent_nudged_at = await _nudged_at(opponent_character, duel.opponent_praxis_id)

    # Stakes shown use the faction held at the seal, as the score did (#3873).
    stamped = {
        (pid, cid): slug
        for pid, cid, slug in (
            await session.execute(
                select(
                    PraxisMember.praxis_id,
                    PraxisMember.character_id,
                    PraxisMember.faction_slug,
                ).where(
                    PraxisMember.praxis_id.in_(praxis_ids),
                    PraxisMember.faction_slug.isnot(None),
                )
            )
        ).all()
    }

    def _held(character: Optional[Character], praxis_id: Optional[int]) -> str:
        if character is not None:
            slug = stamped.get((praxis_id, character.id))
            if slug:
                return slug
        return _faction_slug_of(character)

    voted = any(
        get_tally(tallies, pid).points_from_votes
        for pid in (duel.challenger_praxis_id, duel.opponent_praxis_id)
        if pid is not None
    )

    def _side(
        character: Optional[Character],
        praxis: Optional[Praxis],
        praxis_id: Optional[int],
        nudged_at: Optional[datetime] = None,
        *,
        opponent_character: Optional[Character] = None,
        foe_praxis_id: Optional[int] = None,
    ) -> DuelSideOut:
        own_slug = _faction_slug_of(character)
        identity = public_identity(character) if character is not None else None

        def _multiplier(is_winner: bool, is_tied: bool) -> float:
            return compute_duel_multiplier(
                _held(character, praxis_id),
                _held(opponent_character, foe_praxis_id),
                is_winner,
                is_tied,
                era,
                has_votes=voted,
            )

        return DuelSideOut(
            praxis_id=praxis_id,
            character_id=character.id if character is not None else 0,
            display_name=identity.display_name if identity else "",
            name_state=identity.name_state if identity else NameState.ok,
            faction_slug=own_slug,
            avatar_url=identity.avatar_url if identity else "",
            points_from_votes=(
                get_tally(tallies, praxis_id).points_from_votes if praxis_id is not None else 0
            ),
            is_submitted=praxis is not None and praxis.status == PraxisStatus.submitted,
            nudged_at=nudged_at,
            nudge_again_at=nudge_again_at(nudged_at),
            win_multiplier=_multiplier(True, False),
            loss_multiplier=_multiplier(False, False),
            tie_multiplier=_multiplier(False, True),
            rival_bonus=era.rival_duel_bonus if duel.rival_bonus else 0,
        )

    clock = _cast_clock(duel, challenger_praxis, opponent_praxis)
    return DuelDetailOut(
        id=duel.id,
        task_id=duel.task_id,
        status=duel.status,
        state=duel_state(
            duel, challenger_praxis, opponent_praxis, datetime.now(timezone.utc), era
        ),
        cast_clock_started_at=(
            clock[1] if clock and duel.forfeited_by_character_id is None else None
        ),
        forfeited_by_character_id=duel.forfeited_by_character_id,
        challenger=_side(
            challenger_character,
            challenger_praxis,
            duel.challenger_praxis_id,
            challenger_nudged_at,
            opponent_character=opponent_character,
            foe_praxis_id=duel.opponent_praxis_id,
        ),
        opponent=_side(
            opponent_character,
            opponent_praxis,
            duel.opponent_praxis_id,
            opponent_nudged_at,
            opponent_character=challenger_character,
            foe_praxis_id=duel.challenger_praxis_id,
        ),
        winner_character_id=duel.winner_character_id,
        challenger_final_points=duel.challenger_final_points,
        opponent_final_points=duel.opponent_final_points,
    )


async def issue_duel_challenge(
    challenger_character_id: int,
    challenger_praxis_id: int,
    opponent_character_id: int,
    session: AsyncSession,
    era: EraConfig = CURRENT_ERA,
) -> tuple[Praxis, Duel]:
    """Create a pending Duel on the challenger's in_progress solo praxis (ADR-0011).
    """
    if await _characters_share_account(
        challenger_character_id, opponent_character_id, session
    ):
        raise_coded(400, ErrorCode.duel_self_challenge, SELF_DUEL_DETAIL)

    # Serialize bursts from one praxis; the lock is released on commit.
    await session.execute(
        select(Praxis.id).where(Praxis.id == challenger_praxis_id).with_for_update()
    )
    # Plain read (#2874): only solo passes, and only collabs have a window.
    challenger_praxis = await get_praxis(challenger_praxis_id, session)
    if challenger_praxis.created_by_id != challenger_character_id:
        raise_coded(403, ErrorCode.praxis_not_owner, "You do not own this praxis.")
    if challenger_praxis.status != PraxisStatus.in_progress:
        raise_coded(
            422,
            ErrorCode.duel_requires_in_progress_praxis,
            "A duel can only start from an in-progress praxis.",
        )
    if challenger_praxis.type != PraxisType.solo:
        raise_coded(
            422,
            ErrorCode.duel_requires_solo_praxis,
            "Only a solo praxis can issue a duel challenge.",
        )
    # A side a finished duel left in progress (no-contest) stays out of duels.
    if await get_duel_for_praxis(
        challenger_praxis_id, session
    ) is not None or await session.scalar(
        select(Duel.id)
        .where(
            (Duel.challenger_praxis_id == challenger_praxis_id)
            | (Duel.opponent_praxis_id == challenger_praxis_id),
            Duel.status == DuelStatus.resolved,
        )
        .limit(1)
    ):
        raise_coded(
            409, ErrorCode.duel_already_exists, "This praxis is already part of a duel."
        )

    task = await session.get(Task, challenger_praxis.task_id)
    if task is None:
        raise_coded(404, ErrorCode.task_not_found, "Task no longer exists.")

    opponent = await session.get(Character, opponent_character_id)
    if opponent is None or not await is_playable(opponent, session):
        raise_coded(
            404, ErrorCode.character_not_found, "Opponent character not found."
        )
    await refuse_if_blocked(challenger_character_id, opponent_character_id, session)

    # Pass `era`: the predicate has the Double Dipper carve-out (#1511).
    if await is_active_member_of_task(opponent, task, session, era):
        raise_coded(
            409,
            ErrorCode.duel_opponent_has_active_praxis,
            "The opponent already has an active praxis for this task.",
        )

    # No admin or faction bypass for duels (#2868).
    era_row = await get_current_era_row(session)
    challenger_stats = await get_or_create_stats(session, challenger_character_id, era_row.id)
    if not may_create_duel(challenger_stats.level, None, False, era):
        raise_coded(
            403,
            ErrorCode.duel_level_too_low,
            f"Duels require level {era.duel_level_required}.",
            {"level": era.duel_level_required},
        )

    duel = Duel(
        task_id=challenger_praxis.task_id,
        challenger_praxis_id=challenger_praxis.id,
        opponent_character_id=opponent_character_id,
        status=DuelStatus.pending,
    )
    session.add(duel)
    try:
        await session.flush()
    except IntegrityError:
        raise_coded(
            409, ErrorCode.duel_already_exists, "This praxis is already part of a duel."
        )
    await notify_duel_challenge(
        session, duel.id, challenger_praxis, opponent_character_id
    )

    return challenger_praxis, duel


async def respond_to_duel_challenge(
    duel_id: int,
    character_id: int,
    accept: bool,
    session: AsyncSession,
    era: EraConfig = CURRENT_ERA,
) -> tuple[Optional[Praxis], Duel]:
    """Accept (create opponent praxis, → active) or decline (→ declined).
    Returns (opponent_praxis_or_None, duel)."""
    # Signup lock before the duel row lock (#3655): peek unlocked, lock, reload.
    peek = await get_duel(duel_id, session)
    if (
        accept
        and peek.opponent_character_id == character_id
        and peek.status == DuelStatus.pending
    ):
        await _lock_signups_for_character(character_id, session)
    duel = await get_duel(duel_id, session, lock=True)

    if duel.opponent_character_id != character_id:
        raise_coded(
            403, ErrorCode.duel_challenge_not_yours, "This challenge is not for you."
        )

    # No sweep here (signup lock came first, #3655): a lapsed one reads as resolved.
    transition = "accept" if accept else "decline"
    if await duel_state_of(duel, session, era) not in ALLOWED_FROM[transition]:
        raise_coded(
            400,
            ErrorCode.duel_challenge_already_resolved,
            "Challenge has already been resolved.",
        )

    now = datetime.now(timezone.utc)

    if not accept:
        duel.status = DuelStatus.declined
        duel.declined_at = now
        await session.flush()
        await _rescore_participants(duel, session, era)
        return None, duel

    opponent = await session.get(Character, character_id)
    if opponent is None:
        raise_coded(404, ErrorCode.character_not_found, "Character not found.")

    # Self-duel guard (ADR-0041, #1237): accept-only, so legacy same-account
    # challenges can still be declined or cancelled.
    challenger_praxis = await session.get(Praxis, duel.challenger_praxis_id)
    if challenger_praxis is not None and await _characters_share_account(
        challenger_praxis.created_by_id, character_id, session
    ):
        raise_coded(400, ErrorCode.duel_self_challenge, SELF_DUEL_DETAIL)

    await settle_closed_backdoors(session)
    task = await session.get(Task, duel.task_id)
    if task is None:
        raise_coded(404, ErrorCode.task_not_found, "Task no longer exists.")
    # Same 404 a deleted task gets: a refusal must not name the backdoor (#3848).
    if task.status == TaskStatus.backdoor and task_status_closed(task, opponent, era):
        raise_coded(404, ErrorCode.task_not_found, "Task no longer exists.")

    # The challenge may outlive the task's status (era close, mod action). Level
    # stays exempt below (#292).
    if task_status_closed(task, opponent, era):
        status = task.status.value
        deleted = task.status == TaskStatus.deleted
        context = {} if deleted else {DETAIL_CONTEXT_PARAM: status}
        raise_coded(
            403,
            ErrorCode.task_not_open_for_signup,
            f"This task is {status} and is not open for new praxis.",
            context,
        )

    # May have signed up since the challenge; `era` as above (#1511).
    if await is_active_member_of_task(opponent, task, session, era):
        raise_coded(
            409,
            ErrorCode.task_already_active_member,
            "You already have an active praxis for this task.",
            {DETAIL_CONTEXT_PARAM: "duel"},
        )

    in_progress_count = await count_in_progress_praxes(character_id, session)
    if in_progress_count >= era.max_task_signups:
        raise_coded(
            400,
            ErrorCode.task_bank_full,
            f"Task bank is full ({era.max_task_signups} in-progress praxis).",
            {"limit": era.max_task_signups},
        )

    # ponytail: flat duel floor only, no task-level check: a duel is a reach
    # above your level (#292). Revisit ADR-0051 before adding one.
    era_row = await get_current_era_row(session)
    opponent_stats = await get_or_create_stats(session, character_id, era_row.id)
    if not may_create_duel(opponent_stats.level, None, False, era):
        raise_coded(
            403,
            ErrorCode.duel_level_too_low,
            f"Duels require level {era.duel_level_required}.",
            {"level": era.duel_level_required},
        )

    opponent_praxis = Praxis(
        task_id=duel.task_id,
        type=PraxisType.solo,
        status=PraxisStatus.in_progress,
        body_text="",
        moderation_status=ModerationStatus.visible,
        created_by_id=character_id,
    )
    session.add(opponent_praxis)
    await session.flush()

    opponent_member = PraxisMember(
        praxis_id=opponent_praxis.id,
        character_id=character_id,
        has_approved=False,
    )
    session.add(opponent_member)
    await session.flush()

    duel.opponent_praxis_id = opponent_praxis.id
    duel.status = DuelStatus.active
    duel.accepted_at = now
    # Snapshot, never re-read (ADR-0100); a Block doesn't void it (ADR-0077).
    duel.rival_bonus = challenger_praxis is not None and await are_rivals(
        challenger_praxis.created_by_id, character_id, session
    )
    await session.flush()

    loaded_praxis = await get_praxis(opponent_praxis.id, session)
    return loaded_praxis, duel


async def cancel_duel_challenge(
    duel_id: int,
    character_id: int,
    session: AsyncSession,
    era: EraConfig = CURRENT_ERA,
) -> Duel:
    """Dissolve a pending *or* active duel — any participant may (ADR-0011 §Forfeit grill).

    Both sides stay plain solo praxes, no penalty.
    """
    duel = await get_duel(duel_id, session, lock=True)

    # Q5: a forfeit can't be dissolved away.
    if await duel_state_of(duel, session, era) not in ALLOWED_FROM["dissolve"]:
        raise HTTPException(status_code=400, detail="Duel has already been resolved.")

    challenger_praxis = await session.get(Praxis, duel.challenger_praxis_id)
    challenger_character_id = (
        challenger_praxis.created_by_id if challenger_praxis is not None else None
    )
    if character_id not in (challenger_character_id, duel.opponent_character_id):
        raise HTTPException(status_code=403, detail="Only a duel participant can end it.")

    duel.status = DuelStatus.declined
    duel.declined_at = datetime.now(timezone.utc)
    await session.flush()
    await _rescore_participants(duel, session, era)
    return duel


async def _rescore_participants(
    duel: Duel, session: AsyncSession, era: EraConfig
) -> None:
    """Decline and withdraw both end in DISSOLVED; a side may already be scored
    with the duel multiplier, so revert both."""
    challenger_praxis = await session.get(Praxis, duel.challenger_praxis_id)
    participant_ids = {
        challenger_praxis.created_by_id if challenger_praxis is not None else None,
        duel.opponent_character_id,
    } - {None}
    await _rescore(participant_ids, session, era, emit_taunts=True)
