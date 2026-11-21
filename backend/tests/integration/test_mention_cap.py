"""Mentions per comment are capped: each one is a push."""
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from models.character import Character
from models.comment import MAX_MENTIONS_PER_COMMENT
from models.praxis import Praxis
from tests.integration.factories import DEFAULT_FACTION_SLUG


@pytest.mark.asyncio
async def test_mentions_capped_on_create_and_edit(
    client: AsyncClient,
    db_session: AsyncSession,
    character2: Character,
    praxis_solo: Praxis,
    auth_headers2: dict,
):
    for index in range(8):
        db_session.add(
            Character(
                account_id=character2.account_id,
                username=f"mention{index}",
                display_name=f"M{index}",
                faction_slug=DEFAULT_FACTION_SLUG,
            )
        )
    await db_session.commit()
    names = [f"@mention{index}" for index in range(8)]
    resp = await client.post(
        f"/praxes/{praxis_solo.id}/comments",
        json={"body_text": " ".join(names + names[:2])},
        headers=auth_headers2,
    )
    assert resp.status_code == 201, resp.text
    assert {m["username"] for m in resp.json()["mentions"]} == {
        f"mention{index}" for index in range(MAX_MENTIONS_PER_COMMENT)
    }
    edit = await client.patch(
        f"/comments/{resp.json()['id']}",
        json={"body_text": " ".join(reversed(names))},
        headers=auth_headers2,
    )
    assert edit.status_code == 200, edit.text
    assert {m["username"] for m in edit.json()["mentions"]} == {
        f"mention{index}" for index in range(8 - MAX_MENTIONS_PER_COMMENT, 8)
    }
