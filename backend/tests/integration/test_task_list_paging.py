"""Offset paging over tied sort keys returns each task exactly once."""
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from models.character import Character
from services.task import TaskSort, list_tasks
from tests.integration.factories import make_task


@pytest.mark.asyncio
@pytest.mark.parametrize("sort", [None, *TaskSort])
async def test_tied_tasks_page_without_repeats_or_gaps(
    db_session: AsyncSession, character: Character, sort
):
    made = [
        await make_task(db_session, character, title=f"t{i}") for i in range(7)
    ]
    ids: list[int] = []
    for offset in range(0, 7, 2):
        page = await list_tasks(db_session, sort=sort, limit=2, offset=offset)
        ids += [t.id for t in page]
    assert sorted(ids) == sorted(t.id for t in made)
    assert len(ids) == len(set(ids))
