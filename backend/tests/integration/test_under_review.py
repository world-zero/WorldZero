"""Content under review can't be rewritten by its author (#3973)."""

import os

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from models.character import Character
from models.comment import Comment
from models.praxis import MediaItem, MediaType, ModerationStatus, Praxis, PraxisStatus


async def _comment(client, praxis, headers) -> int:
    r = await client.post(
        f"/praxes/{praxis.id}/comments", json={"body_text": "original"}, headers=headers
    )
    return r.json()["id"]


async def _edit(client, cid, headers):
    return await client.patch(
        f"/comments/{cid}", json={"body_text": "laundered"}, headers=headers
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "status",
    [ModerationStatus.flagged, ModerationStatus.hidden, ModerationStatus.deleted],
)
async def test_edit_refused_while_under_review_then_allowed(
    client: AsyncClient,
    db_session: AsyncSession,
    character: Character,
    character2: Character,
    praxis_solo: Praxis,
    auth_headers2: dict,
    status: ModerationStatus,
):
    cid = await _comment(client, praxis_solo, auth_headers2)
    comment = await db_session.get(Comment, cid)
    comment.moderation_status = status
    await db_session.commit()

    resp = await _edit(client, cid, auth_headers2)

    assert resp.status_code == 409
    assert resp.json()["detail"]["code"] == "UNDER_REVIEW"
    await db_session.refresh(comment)
    assert comment.body_text == "original"

    comment.moderation_status = ModerationStatus.visible
    await db_session.commit()
    assert (await _edit(client, cid, auth_headers2)).status_code == 200


@pytest.mark.asyncio
async def test_unsubmit_refused_while_flagged_then_allowed(
    client: AsyncClient,
    db_session: AsyncSession,
    character: Character,
    praxis_solo: Praxis,
    auth_headers: dict,
):
    praxis_solo.moderation_status = ModerationStatus.flagged
    await db_session.commit()

    resp = await client.post(f"/praxes/{praxis_solo.id}/unsubmit", headers=auth_headers)

    assert resp.status_code == 409
    assert resp.json()["detail"]["code"] == "UNDER_REVIEW"
    await db_session.refresh(praxis_solo)
    assert praxis_solo.status == PraxisStatus.submitted

    praxis_solo.moderation_status = ModerationStatus.visible
    await db_session.commit()
    resp = await client.post(f"/praxes/{praxis_solo.id}/unsubmit", headers=auth_headers)
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_media_delete_refused_while_flagged_then_allowed(
    client: AsyncClient,
    db_session: AsyncSession,
    character: Character,
    praxis_solo: Praxis,
    auth_headers: dict,
    media_root,
):
    stored = media_root / "keep.png"
    stored.write_bytes(b"x")
    extra = MediaItem(
        praxis_id=praxis_solo.id, type=MediaType.image, file_path="keep.png"
    )
    db_session.add(extra)
    praxis_solo.moderation_status = ModerationStatus.flagged
    await db_session.commit()
    url = f"/praxes/{praxis_solo.id}/media/{extra.id}"

    resp = await client.delete(url, headers=auth_headers)

    assert resp.status_code == 409
    assert resp.json()["detail"]["code"] == "UNDER_REVIEW"
    assert os.path.exists(stored)
    assert await db_session.get(MediaItem, extra.id) is not None

    praxis_solo.moderation_status = ModerationStatus.visible
    await db_session.commit()
    assert (await client.delete(url, headers=auth_headers)).status_code == 204
