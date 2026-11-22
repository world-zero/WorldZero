"""Read, write and revert admin copy overrides.

No era (copy is not a game rule) and no key validation: the catalogs live in
the frontend bundle, so the backend deliberately has no registry.
"""

from typing import Sequence

from sqlalchemy import delete, func, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from models.copy_override import CopyOverride


async def list_overrides(session: AsyncSession) -> Sequence[CopyOverride]:
    """Every override, in stable order."""
    result = await session.execute(
        select(CopyOverride).order_by(CopyOverride.ns, CopyOverride.key)
    )
    return result.scalars().all()


async def upsert_override(
    ns: str,
    key: str,
    value: str,
    account_id: int,
    session: AsyncSession,
) -> CopyOverride:
    """Single upsert so concurrent saves cannot race on the PK. ``updated_at``
    is explicit: ``onupdate`` does not fire on the ``ON CONFLICT`` arm."""
    statement = (
        pg_insert(CopyOverride)
        .values(ns=ns, key=key, value=value, updated_by_id=account_id)
        .on_conflict_do_update(
            index_elements=["ns", "key"],
            set_={
                "value": value,
                "updated_by_id": account_id,
                "updated_at": func.now(),
            },
        )
        .returning(CopyOverride)
    )
    row = (
        await session.execute(statement, execution_options={"populate_existing": True})
    ).scalar_one()
    await session.flush()
    return row


async def replace_override_if_unchanged(
    ns: str,
    key: str,
    value: str,
    base: str | None,
    account_id: int,
    session: AsyncSession,
) -> CopyOverride | None:
    """Write only if the row still holds ``base`` (None = no row yet).

    One statement either way, so two editors racing cannot both win. None means
    someone else changed or reverted it first; nothing was written.
    """
    if base is None:
        statement = (
            pg_insert(CopyOverride)
            .values(ns=ns, key=key, value=value, updated_by_id=account_id)
            .on_conflict_do_nothing(index_elements=["ns", "key"])
            .returning(CopyOverride)
        )
    else:
        statement = (
            update(CopyOverride)
            .where(
                CopyOverride.ns == ns,
                CopyOverride.key == key,
                CopyOverride.value == base,
            )
            .values(value=value, updated_by_id=account_id, updated_at=func.now())
            .returning(CopyOverride)
        )
    row = (
        await session.execute(statement, execution_options={"populate_existing": True})
    ).scalar_one_or_none()
    await session.flush()
    return row


async def current_value(ns: str, key: str, session: AsyncSession) -> str | None:
    """The live override, or None when the shipped wording rules."""
    return (
        await session.execute(
            select(CopyOverride.value).where(
                CopyOverride.ns == ns, CopyOverride.key == key
            )
        )
    ).scalar_one_or_none()


async def delete_override(ns: str, key: str, session: AsyncSession) -> bool:
    """Revert ``ns``/``key`` to the shipped catalog. False if there was no row."""
    result = await session.execute(
        delete(CopyOverride).where(CopyOverride.ns == ns, CopyOverride.key == key)
    )
    await session.flush()
    return bool(result.rowcount)
