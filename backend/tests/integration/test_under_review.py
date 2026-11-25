"""Content under review can't be rewritten by its author (#3973)."""

import io
import os

import pytest
from httpx import AsyncClient
from PIL import Image
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from models.character import Character
from models.comment import Comment
from models.meta_task import PraxisMetaTask
from models.praxis import MediaItem, MediaType, ModerationStatus, Praxis, PraxisStatus
from models.task import TaskType
from tests.integration.factories import make_task


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


def _png() -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (8, 8)).save(buffer, format="PNG")
    return buffer.getvalue()


def _on_disk(root) -> set:
    return {path for path in root.rglob("*") if path.is_file()}


async def _media_count(db_session: AsyncSession, praxis: Praxis) -> int:
    return await db_session.scalar(
        select(func.count())
        .select_from(MediaItem)
        .where(MediaItem.praxis_id == praxis.id)
    )


UNDER_REVIEW = [
    ModerationStatus.flagged,
    ModerationStatus.hidden,
    ModerationStatus.failed,
]


@pytest.mark.asyncio
@pytest.mark.parametrize("batch", [False, True])
@pytest.mark.parametrize("status", UNDER_REVIEW)
async def test_media_add_refused_while_under_review_then_allowed(
    client: AsyncClient,
    db_session: AsyncSession,
    character: Character,
    praxis_solo: Praxis,
    auth_headers: dict,
    media_root,
    status: ModerationStatus,
    batch: bool,
):
    url = f"/praxes/{praxis_solo.id}/media" + ("/batch" if batch else "")
    parts = [("files" if batch else "file", ("p.png", _png(), "image/png"))]
    before_rows = await _media_count(db_session, praxis_solo)
    before_files = _on_disk(media_root)
    praxis_solo.moderation_status = status
    await db_session.commit()

    resp = await client.post(url, files=parts, headers=auth_headers)

    assert resp.status_code == 409
    assert resp.json()["detail"]["code"] == "UNDER_REVIEW"
    assert await _media_count(db_session, praxis_solo) == before_rows
    assert _on_disk(media_root) == before_files

    praxis_solo.moderation_status = ModerationStatus.visible
    await db_session.commit()
    resp = await client.post(url, files=parts, headers=auth_headers)
    assert resp.status_code == 201
    assert await _media_count(db_session, praxis_solo) == before_rows + 1


@pytest.mark.asyncio
@pytest.mark.parametrize("status", UNDER_REVIEW)
async def test_metatask_remove_and_apply_refused_while_under_review(
    client: AsyncClient,
    db_session: AsyncSession,
    character: Character,
    praxis_solo: Praxis,
    auth_headers: dict,
    status: ModerationStatus,
):
    meta = await make_task(
        db_session, character, title="meta", task_type=TaskType.metatask
    )
    db_session.add(PraxisMetaTask(praxis_id=praxis_solo.id, task_id=meta.id))
    praxis_solo.moderation_status = status
    await db_session.commit()
    url = f"/praxes/{praxis_solo.id}/metatasks"

    resp = await client.delete(f"{url}/{meta.id}", headers=auth_headers)
    assert resp.status_code == 409
    assert resp.json()["detail"]["code"] == "UNDER_REVIEW"
    assert await db_session.get(PraxisMetaTask, (praxis_solo.id, meta.id))

    resp = await client.post(url, json={"task_id": meta.id}, headers=auth_headers)
    assert resp.status_code == 409
    assert resp.json()["detail"]["code"] == "UNDER_REVIEW"

    praxis_solo.moderation_status = ModerationStatus.visible
    await db_session.commit()
    resp = await client.delete(f"{url}/{meta.id}", headers=auth_headers)
    assert resp.status_code == 200
