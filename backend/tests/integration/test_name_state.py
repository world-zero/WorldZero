"""Absent players read the same everywhere (#4238 S2b), at the praxis seam."""
from datetime import datetime, timezone

import pytest

from models.account import AccountStatus
from models.character import CharacterStatus, NameState
from services.standing import public_name, standing_of

NOW = datetime.now(timezone.utc)
CASES = [
    (AccountStatus.active, CharacterStatus.active, None, NameState.ok),
    (AccountStatus.suspended, CharacterStatus.active, None, NameState.suspended),
    (AccountStatus.active, CharacterStatus.banned, None, NameState.absent),
    (AccountStatus.active, CharacterStatus.banned, NOW, NameState.absent),
    (AccountStatus.deleted, CharacterStatus.active, None, NameState.absent),
]


@pytest.mark.asyncio
@pytest.mark.parametrize("account_status,life,departed_at,expected", CASES)
async def test_name_state_column_agrees_with_public_name(
    client, db_session, account, character, praxis_solo,
    account_status, life, departed_at, expected,
):
    praxis_id = praxis_solo.id
    account.status = account_status
    character.status = life
    character.departed_at = departed_at
    await db_session.commit()
    db_session.expire_all()
    await db_session.refresh(account)
    await db_session.refresh(character)

    shown = public_name(character.display_name, *standing_of(account.status, character))
    assert (expected == NameState.absent) == (shown.name is None)
    assert (expected == NameState.suspended) == shown.suspended

    praxis = await client.get(f"/praxes/{praxis_id}")
    assert praxis.status_code == 200
    body = praxis.json()
    assert body["created_by_name_state"] == expected.value
    assert body["members"][0]["character_name_state"] == expected.value
    if expected == NameState.absent:
        assert body["created_by_display_name"] == ""
        assert body["created_by_avatar_url"] == ""
        assert body["members"][0]["character_display_name"] == ""
