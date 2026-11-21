"""Unsubscribe from notification email (#2164). No auth: the signed token is the key."""

from fastapi import APIRouter, Depends
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from db import get_db
from errors import ErrorCode, raise_coded
from models.account import Account
from schemas.email import UnsubscribeOut
from services.email import read_unsubscribe_token, unsubscribe_page_url
from services.notification_prefs import EVENTS_BY_KEY, apply_update

router = APIRouter()

_OFF = {"by_email": False}


async def _owner(token: str, session: AsyncSession) -> tuple[Account, str]:
    """The token's account and event, or a coded 400 for anything not ours."""
    parsed = read_unsubscribe_token(token)
    account = await session.get(Account, parsed[0]) if parsed else None
    if parsed is None or account is None or parsed[1] not in EVENTS_BY_KEY:
        raise_coded(
            400,
            ErrorCode.email_unsubscribe_bad_token,
            "That unsubscribe link is not valid.",
        )
    return account, parsed[1]


@router.get("/unsubscribe", status_code=303)
async def unsubscribe_page(token: str) -> RedirectResponse:
    """A mail client without one-click opens the List-Unsubscribe URL with GET."""
    return RedirectResponse(unsubscribe_page_url(token), status_code=303)


@router.post("/unsubscribe", response_model=UnsubscribeOut)
async def unsubscribe(
    token: str, session: AsyncSession = Depends(get_db, scope="function")
) -> UnsubscribeOut:
    """Turn off email for the one event that sent the mail. Idempotent; also the
    target of the one-click ``List-Unsubscribe-Post``."""
    account, kind = await _owner(token, session)
    account.notification_prefs = apply_update(account.notification_prefs, {kind: _OFF})
    await session.commit()
    return UnsubscribeOut(event=kind)


@router.post("/unsubscribe-all", response_model=UnsubscribeOut)
async def unsubscribe_all(
    token: str, session: AsyncSession = Depends(get_db, scope="function")
) -> UnsubscribeOut:
    """The "turn them all off" button: every row's email, not only this one."""
    account, kind = await _owner(token, session)
    account.notification_prefs = apply_update(
        account.notification_prefs, {key: _OFF for key in EVENTS_BY_KEY}
    )
    await session.commit()
    return UnsubscribeOut(event=kind)
