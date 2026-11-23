"""Copy proposals (#4280): CI files with a shared token; edit_copy settles."""

import hmac

from fastapi import APIRouter, Depends, Header
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from db import get_db
from dependencies import require_permission
from errors import ErrorCode, raise_coded
from models.account import Account
from models.roles import Permission
from schemas.copy_proposal import CopyProposalIn, CopyProposalLineRef, CopyProposalOut
from services import copy_proposal as service
from services.push import notify_copy_proposal

router = APIRouter(prefix="/copy-proposals")


def _require_token(
    x_copy_proposal_token: str = Header(default="", max_length=256),
) -> None:
    """Refuses everyone while the setting is blank: an empty header must never match."""
    expected = settings.COPY_PROPOSAL_TOKEN
    if not expected:
        raise_coded(
            503,
            ErrorCode.copy_proposals_disabled,
            "Copy proposals are not enabled on this server.",
        )
    if not hmac.compare_digest(x_copy_proposal_token.encode(), expected.encode()):
        raise_coded(401, ErrorCode.copy_proposal_token_invalid, "Bad proposal token.")


@router.post("", response_model=CopyProposalOut, status_code=201)
async def file_copy_proposal(
    data: CopyProposalIn,
    _: None = Depends(_require_token),
    session: AsyncSession = Depends(get_db, scope="function"),
):
    proposal, needs_eyes = await service.file_proposal(data, session)
    if needs_eyes:
        await notify_copy_proposal(session, proposal)
    await session.commit()
    return proposal


@router.get("", response_model=list[CopyProposalOut])
async def list_copy_proposals(
    _: Account = Depends(require_permission(Permission.edit_copy)),
    session: AsyncSession = Depends(get_db, scope="function"),
):
    """Proposals with at least one open line, newest first."""
    return await service.list_open(session)


@router.post("/{proposal_id}/approve", response_model=CopyProposalOut)
async def approve_copy_proposal_line(
    proposal_id: int,
    line: CopyProposalLineRef,
    admin: Account = Depends(require_permission(Permission.edit_copy)),
    session: AsyncSession = Depends(get_db, scope="function"),
):
    proposal = await service.approve_line(
        proposal_id, line.ns, line.key, admin, session
    )
    await session.commit()
    return proposal


@router.post("/{proposal_id}/reject", response_model=CopyProposalOut)
async def reject_copy_proposal_line(
    proposal_id: int,
    line: CopyProposalLineRef,
    _: Account = Depends(require_permission(Permission.edit_copy)),
    session: AsyncSession = Depends(get_db, scope="function"),
):
    proposal = await service.reject_line(proposal_id, line.ns, line.key, session)
    await session.commit()
    return proposal
