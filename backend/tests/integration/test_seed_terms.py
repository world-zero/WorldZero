import subprocess
import sys
from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from game_config import CURRENT_ERA
from models.account import Account
from seed import bootstrap_admin, upsert_era_factions
from services.character import has_current_terms


@pytest.mark.asyncio
async def test_seeded_admin_has_current_terms_and_reseed_is_idempotent(
    db_session: AsyncSession,
):
    await upsert_era_factions(db_session, CURRENT_ERA)
    await bootstrap_admin(db_session, CURRENT_ERA, None)
    acc = (await db_session.execute(
        select(Account).where(Account.email == "pixieofhugs@gmail.com")
    )).scalar_one()
    assert await has_current_terms(acc.id, db_session)

    await bootstrap_admin(db_session, CURRENT_ERA, acc)
    assert await has_current_terms(acc.id, db_session)


def test_seed_imports_in_a_fresh_interpreter():
    # In-process, the app has already loaded the modules a cycle would break on.
    backend = Path(__file__).resolve().parents[2]
    done = subprocess.run(
        [sys.executable, "-c", "import seed"],
        cwd=backend, capture_output=True, text=True,
    )
    assert done.returncode == 0, done.stderr
