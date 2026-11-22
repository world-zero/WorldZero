"""Each field combination maps to exactly one standing (#4236)."""
from datetime import datetime, timezone
from itertools import product
from types import SimpleNamespace

import pytest

from models.account import AccountStatus
from models.character import CharacterStatus
from services.standing import (
    AccountStanding,
    LifeStanding,
    PublicName,
    account_standing,
    counts_as_voter,
    is_playable,
    is_public,
    life_standing,
    public_name,
)

A, L = AccountStanding, LifeStanding
NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)


@pytest.mark.parametrize(
    "status, departed_at, expected",
    [
        (CharacterStatus.active, None, L.ACTIVE),
        (CharacterStatus.banned, None, L.MOD_BANNED),
        (CharacterStatus.banned, NOW, L.DEPARTED),
    ],
)
def test_life_standing(status, departed_at, expected):
    character = SimpleNamespace(status=status, departed_at=departed_at)
    assert life_standing(character) is expected


ACC = AccountStatus
ACCOUNT_CASES = [
    (ACC.deleted, True, [L.ACTIVE], False, A.DELETED),
    (ACC.deleted, False, [], True, A.DELETED),
    (ACC.suspended, True, [L.ACTIVE], False, A.SUSPENDED),
    (ACC.suspended, False, [], False, A.SUSPENDED),
    (ACC.active, False, [L.ACTIVE], False, A.NEEDS_TERMS),
    (ACC.active, False, [], False, A.NEEDS_TERMS),
    (ACC.active, True, [], False, A.NO_CHARACTER),
    (ACC.active, True, [L.DEPARTED], False, A.NO_CHARACTER),
    (ACC.active, True, [], True, A.CREATION_BANNED),
    (ACC.active, True, [L.MOD_BANNED], False, A.CREATION_BANNED),
    (ACC.active, True, [L.MOD_BANNED, L.DEPARTED], False, A.CREATION_BANNED),
    (ACC.active, True, [L.ACTIVE], False, A.PLAYING),
    (ACC.active, True, [L.ACTIVE, L.MOD_BANNED], True, A.PLAYING),
]


@pytest.mark.parametrize("status, terms, lives, carried, expected", ACCOUNT_CASES)
def test_account_standing(status, terms, lives, carried, expected):
    assert account_standing(status, terms, lives, carried) is expected


def test_every_account_input_combination_derives_a_standing():
    for status, terms, lives, carried in product(
        AccountStatus, (True, False), ([], [L.ACTIVE], [L.MOD_BANNED]), (True, False)
    ):
        assert isinstance(account_standing(status, terms, lives, carried), A)


def test_predicates_over_every_pair():
    for account, life in product(A, L):
        assert is_playable(account, life) == (account is A.PLAYING and life is L.ACTIVE)
        assert is_public(account, life) == (
            account not in (A.SUSPENDED, A.DELETED) and life is L.ACTIVE
        )
        assert counts_as_voter(account, life) == (
            account is not A.SUSPENDED and life is not L.MOD_BANNED
        )


@pytest.mark.parametrize(
    "account, life, expected",
    [
        (A.PLAYING, L.ACTIVE, PublicName("Ada", False, True)),
        (A.NEEDS_TERMS, L.ACTIVE, PublicName("Ada", False, True)),
        (A.SUSPENDED, L.ACTIVE, PublicName("Ada", True, False)),
        (A.PLAYING, L.MOD_BANNED, PublicName(None, False, False)),
        (A.PLAYING, L.DEPARTED, PublicName(None, False, False)),
        (A.DELETED, L.ACTIVE, PublicName(None, False, False)),
        (A.SUSPENDED, L.MOD_BANNED, PublicName(None, False, False)),
    ],
)
def test_public_name(account, life, expected):
    assert public_name("Ada", account, life) == expected
