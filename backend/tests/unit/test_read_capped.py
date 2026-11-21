import io

import pytest
from fastapi import HTTPException, UploadFile
from starlette.datastructures import Headers

from services import media
from services.media import process_and_save_avatar, process_and_save_media

CAP = 10
CHUNK = 4


class CountingUpload(UploadFile):
    """Serves ``total`` bytes and counts how many it handed out."""

    def __init__(self, total: int, declared_size: int | None = None) -> None:
        super().__init__(
            io.BytesIO(),
            filename="big.png",
            size=declared_size,
            headers=Headers({"content-type": "image/png"}),
        )
        self._left = total
        self.served = 0

    async def read(self, size: int = -1) -> bytes:
        count = self._left if size < 0 else min(size, self._left)
        self._left -= count
        self.served += count
        return b"x" * count


@pytest.fixture(autouse=True)
def small_chunks(monkeypatch, tmp_path):
    monkeypatch.setattr(media.settings, "MEDIA_ROOT", str(tmp_path))
    monkeypatch.setattr(media, "_READ_CHUNK_BYTES", CHUNK)
    monkeypatch.setattr(media, "MEDIA_MAX_BYTES", CAP)
    monkeypatch.setattr(media, "AVATAR_MAX_BYTES", CAP)


async def test_read_capped_stops_at_cap_plus_one_chunk():
    upload = CountingUpload(10_000)
    assert await media.read_capped(upload, CAP) is None
    assert upload.served <= CAP + CHUNK


async def test_read_capped_skips_read_when_declared_size_over():
    upload = CountingUpload(10_000, declared_size=10_000)
    assert await media.read_capped(upload, CAP) is None
    assert upload.served == 0


async def test_read_capped_returns_bytes_at_cap():
    assert await media.read_capped(CountingUpload(CAP), CAP) == b"x" * CAP


async def test_media_path_413s_without_reading_everything():
    upload = CountingUpload(10_000)
    with pytest.raises(HTTPException) as caught:
        await process_and_save_media(upload, 1, 1, 0)
    assert caught.value.status_code == 413
    assert upload.served <= CAP + CHUNK


async def test_avatar_path_413s_without_reading_everything():
    upload = CountingUpload(10_000)
    with pytest.raises(HTTPException) as caught:
        await process_and_save_avatar(upload, 1)
    assert caught.value.status_code == 413
    assert upload.served <= CAP + CHUNK
