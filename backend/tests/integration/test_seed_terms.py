import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from game_config import CURRENT_ERA
from models.account import Account
from seed import bootstrap_admin
from services.character import has_current_terms


@pytest.mark.asyncio
async def test_seeded_admin_has_current_terms_and_reseed_is_idempotent(
    db_session: AsyncSession,
):
    await bootstrap_admin(db_session, CURRENT_ERA, None)
    acc = (await db_session.execute(
        select(Account).where(Account.email == "pixieofhugs@gmail.com")
    )).scalar_one()
    assert await has_current_terms(acc.id, db_session)

    await bootstrap_admin(db_session, CURRENT_ERA, acc)
    assert await has_current_terms(acc.id, db_session)
