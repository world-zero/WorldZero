from typing import Optional

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from db import get_db
from dependencies import get_current_account_optional, get_viewer_is_admin
from models.account import Account
from schemas.character import CharacterOut
from schemas.params import WidePage
from schemas.base import WireModel
from services.character import build_character_outs, list_characters_for_viewer
from services.era import era_row_name, get_era_row_or_404

router = APIRouter()


class LeaderboardEraOut(WireModel):
    id: int
    name: str


@router.get("/era/{era_id}", response_model=LeaderboardEraOut)
async def get_leaderboard_era(
    era_id: int,
    session: AsyncSession = Depends(get_db, scope="function"),
):
    """The era's display name, for labelling ``?era=<id>``."""
    row = await get_era_row_or_404(session, era_id)
    return LeaderboardEraOut(id=row.id, name=era_row_name(row))


@router.get("", response_model=list[CharacterOut])
async def get_leaderboard(
    faction: Optional[str] = None,
    era: Optional[int] = None,
    page: WidePage = Depends(),
    session: AsyncSession = Depends(get_db, scope="function"),
    account: Optional[Account] = Depends(get_current_account_optional),
    viewer_is_admin: bool = Depends(get_viewer_is_admin),
):
    """Top characters by current era score, optionally filtered by faction or ranked for a past ``era`` id.

    Public; optional auth only feeds the reveal check (#2422).
    """
    if era is not None:
        await get_era_row_or_404(session, era)
    rows = await list_characters_for_viewer(
        session,
        faction_slug=faction,
        viewer_account=account,
        # Admins count as revealed here only (#2400).
        viewer_is_admin=viewer_is_admin,
        limit=page.limit,
        offset=page.offset,
        era_id=era,
    )
    return await build_character_outs(rows, session)
