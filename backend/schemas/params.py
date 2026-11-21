"""Shared bounds for route params, so an out-of-range number is a 422, not a DB 500."""

from typing import Annotated

from annotated_types import Ge, Le
from fastapi import Query

INT32_MAX = 2**31 - 1

Id = Annotated[int, Ge(1), Le(2**63 - 1)]
Int32 = Annotated[int, Ge(0), Le(INT32_MAX)]

PAGE_MAX = 200
WIDE_PAGE_MAX = 500


class Page:
    """Dependency: ``page: Page = Depends()`` gives bounded ``limit``/``offset``."""

    def __init__(
        self,
        limit: Annotated[int, Query(ge=1, le=PAGE_MAX)] = 50,
        offset: Annotated[int, Query(ge=0, le=INT32_MAX)] = 0,
    ):
        self.limit, self.offset = limit, offset


class WidePage(Page):
    def __init__(
        self,
        limit: Annotated[int, Query(ge=1, le=WIDE_PAGE_MAX)] = 50,
        offset: Annotated[int, Query(ge=0, le=INT32_MAX)] = 0,
    ):
        super().__init__(limit, offset)
