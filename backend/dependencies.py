"""Shared FastAPI dependencies used across multiple routers."""
from typing import Optional

from fastapi import Cookie, Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db import get_db
from errors import ErrorCode, raise_coded
from models.account import Account, AccountStatus
from models.character import Character
from models.roles import (
    OWNER_ROLE_NAME,
    AccountPermission,
    AccountRole,
    Permission,
    Role,
)
from services.auth import decode_jwt, get_current_account
from services.character import resolve_active_character

_OPTIONAL_BEARER = HTTPBearer(auto_error=False)


async def get_current_character(
    account: Account = Depends(get_current_account),
    session: AsyncSession = Depends(get_db, scope="function"),
) -> Character:
    """The account's active character — the actor for every write path. 403 if none."""
    character = await resolve_active_character(account, session)
    if character is None:
        raise HTTPException(
            status_code=403,
            detail="No active character found. Create a character first.",
        )
    return character


async def get_current_account_optional(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_OPTIONAL_BEARER),
    access_token: Optional[str] = Cookie(default=None),
    session: AsyncSession = Depends(get_db, scope="function"),
) -> Optional[Account]:
    """Never-raising :func:`services.auth.get_current_account`; ``None`` if anon."""
    token = None
    if credentials:
        token = credentials.credentials
    elif access_token:
        token = access_token
    if not token:
        return None

    try:
        payload = decode_jwt(token)
        account_id = int(payload["sub"])
    except Exception:
        return None

    account_result = await session.execute(
        select(Account).where(Account.id == account_id)
    )
    account = account_result.scalar_one_or_none()
    if account is None or account.status != AccountStatus.active:
        return None
    return account


async def get_current_character_optional(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_OPTIONAL_BEARER),
    access_token: Optional[str] = Cookie(default=None),
    session: AsyncSession = Depends(get_db, scope="function"),
) -> Optional[Character]:
    """Mirror of :func:`get_current_character` that never raises."""
    token = None
    if credentials:
        token = credentials.credentials
    elif access_token:
        token = access_token
    if not token:
        return None

    try:
        payload = decode_jwt(token)
    except Exception:
        return None

    try:
        account_id = int(payload["sub"])
    except (KeyError, TypeError, ValueError):
        return None

    account_result = await session.execute(
        select(Account).where(Account.id == account_id)
    )
    account = account_result.scalar_one_or_none()
    if account is None or account.status != AccountStatus.active:
        return None

    return await resolve_active_character(account, session)


async def require_admin(
    account: Account = Depends(get_current_account),
    session: AsyncSession = Depends(get_db, scope="function"),
) -> Account:
    """Raise 403 unless the account is an admin (any permission, or owner)."""
    if not await account_has_admin_role(account.id, session):
        raise HTTPException(status_code=403, detail="Admin access required.")
    return account


async def get_viewer_is_admin(
    account: Optional[Account] = Depends(get_current_account_optional),
    session: AsyncSession = Depends(get_db, scope="function"),
) -> bool:
    """Is the viewer an admin? Anonymous resolves to ``False``, never 401."""
    if account is None:
        return False
    return await account_has_admin_role(account.id, session)


async def account_is_owner(account_id: int, session: AsyncSession) -> bool:
    """Holds the ``owner`` role (set only from the CLI or the DB, ADR-0101)."""
    result = await session.execute(
        select(AccountRole.id)
        .join(Role, AccountRole.role_id == Role.id)
        .where(AccountRole.account_id == account_id, Role.name == OWNER_ROLE_NAME)
    )
    return result.first() is not None


async def account_permissions(account_id: int, session: AsyncSession) -> frozenset[Permission]:
    """What the account may do as an admin; the owner holds all nine."""
    if await account_is_owner(account_id, session):
        return frozenset(Permission)
    rows = await session.scalars(
        select(AccountPermission.permission).where(
            AccountPermission.account_id == account_id
        )
    )
    return frozenset(rows)


async def account_has_admin_role(account_id: int, session: AsyncSession) -> bool:
    """The one definition of admin: owner, or at least one permission."""
    return bool(await account_permissions(account_id, session))


def require_permission(*permissions: Permission):
    """403 unless the account is the owner or holds one of ``permissions``.

    More than one only where a single route spans checkboxes and the handler
    re-checks the finer one (``update_task_status``).
    """

    async def dependency(
        account: Account = Depends(get_current_account),
        session: AsyncSession = Depends(get_db, scope="function"),
    ) -> Account:
        if not (await account_permissions(account.id, session)).intersection(permissions):
            raise_coded(
                403, ErrorCode.admin_permission_required, "You lack that permission."
            )
        return account

    dependency.required_permissions = frozenset(permissions)  # type: ignore[attr-defined]
    return dependency


async def require_owner(
    account: Account = Depends(get_current_account),
    session: AsyncSession = Depends(get_db, scope="function"),
) -> Account:
    """Raise 403 unless the account holds the owner role."""
    if not await account_is_owner(account.id, session):
        raise_coded(403, ErrorCode.admin_owner_required, "Owner access required.")
    return account
