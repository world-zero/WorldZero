"""Copy proposals: CI asks, the owner settles each line (#4280)."""

from typing import Optional, Sequence

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from errors import ErrorCode, raise_coded
from models.account import Account
from models.copy_override import CopyOverride
from models.copy_proposal import CopyProposal, LineStatus
from schemas.copy_proposal import CopyProposalIn
from services.copy_override import current_value, replace_override_if_unchanged


def _line_id(line: dict) -> tuple:
    return tuple(line[k] for k in ("ns", "key", "owner_value", "proposed_value"))


def _is_open(proposal: CopyProposal) -> bool:
    return any(line["status"] == LineStatus.open for line in proposal.lines)


async def file_proposal(
    data: CopyProposalIn, session: AsyncSession
) -> tuple[CopyProposal, bool]:
    """Create the PR's proposal, or replace its lines. True when it newly needs the
    owner's eyes (new, or nothing open before), so a Test re-run does not re-push.
    A line rejected before and unchanged stays rejected; empty ``lines`` withdraws."""
    proposal = await session.scalar(
        select(CopyProposal)
        .where(CopyProposal.pr_number == data.pr_number)
        .with_for_update()
    )
    rejected = {
        _line_id(line)
        for line in (proposal.lines if proposal else [])
        if line["status"] == LineStatus.rejected
    }
    lines = []
    for line in data.lines:
        fields = line.model_dump()
        kept = _line_id(fields) in rejected
        status = LineStatus.rejected if kept else LineStatus.open
        lines.append({**fields, "status": status.value})
    if proposal is None:
        proposal = CopyProposal(pr_number=data.pr_number)
        session.add(proposal)
        fresh = True
    else:
        fresh = not _is_open(proposal)
    fresh = fresh and any(line["status"] == LineStatus.open.value for line in lines)
    proposal.pr_url = str(data.pr_url)
    proposal.lines = lines
    await session.flush()
    return proposal, fresh


async def list_open(session: AsyncSession) -> Sequence[CopyProposal]:
    rows = await session.scalars(select(CopyProposal).order_by(CopyProposal.id.desc()))
    return [proposal for proposal in rows if _is_open(proposal)]


async def _open_line(
    proposal_id: int, ns: str, key: str, session: AsyncSession
) -> tuple[CopyProposal, dict]:
    proposal = await session.scalar(
        select(CopyProposal).where(CopyProposal.id == proposal_id).with_for_update()
    )
    line: Optional[dict] = next(
        (
            candidate
            for candidate in (proposal.lines if proposal else [])
            if candidate["ns"] == ns and candidate["key"] == key
        ),
        None,
    )
    if line is None or line["status"] != LineStatus.open.value:
        raise_coded(
            404,
            ErrorCode.copy_proposal_not_found,
            "That proposal line was already settled, or is gone.",
        )
    return proposal, line


def _settled(proposal: CopyProposal, line: dict, status: LineStatus) -> CopyProposal:
    # Reassign: JSONB mutation in place is not tracked.
    proposal.lines = [
        {**other, "status": status.value} if other is line else other
        for other in proposal.lines
    ]
    return proposal


async def approve_line(
    proposal_id: int, ns: str, key: str, admin: Account, session: AsyncSession
) -> CopyProposal:
    """Write the PR's wording into the override (null deletes the row), only if the
    row still holds ``owner_value``; the same 409 the copy editor gives."""
    proposal, line = await _open_line(proposal_id, ns, key, session)
    base, proposed = line["owner_value"], line["proposed_value"]
    if proposed is None:
        result = await session.execute(
            delete(CopyOverride).where(
                CopyOverride.ns == ns,
                CopyOverride.key == key,
                CopyOverride.value == base,
            )
        )
        applied = bool(result.rowcount)
    else:
        applied = (
            await replace_override_if_unchanged(
                ns, key, proposed, base, admin.id, session
            )
            is not None
        )
    if not applied:
        raise_coded(
            409,
            ErrorCode.copy_override_changed,
            "Someone else changed this wording while you were editing.",
            params={"current": await current_value(ns, key, session)},
        )
    return _settled(proposal, line, LineStatus.approved)


async def reject_line(
    proposal_id: int, ns: str, key: str, session: AsyncSession
) -> CopyProposal:
    proposal, line = await _open_line(proposal_id, ns, key, session)
    return _settled(proposal, line, LineStatus.rejected)
