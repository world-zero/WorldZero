"""Player standing as two derived enums and the predicates built on them (#4204).

Pure: no session, no I/O. Account standing is per account, life standing per
character; the two are independent.
"""

import enum
import logging
from dataclasses import dataclass
from typing import Iterable, Optional

from models.account import AccountStatus
from models.character import Character, CharacterStatus, NameState

logger = logging.getLogger(__name__)


class AccountStanding(enum.Enum):
    NEEDS_TERMS = "needs_terms"
    NO_CHARACTER = "no_character"
    CREATION_BANNED = "creation_banned"
    PLAYING = "playing"
    SUSPENDED = "suspended"
    DELETED = "deleted"


class LifeStanding(enum.Enum):
    ACTIVE = "active"
    MOD_BANNED = "mod_banned"
    DEPARTED = "departed"


def life_standing(character: Character) -> LifeStanding:
    if character.status == CharacterStatus.active:
        return LifeStanding.ACTIVE
    # departed_at is only stamped on a self-delete, never on a mod ban.
    if character.departed_at is not None:
        return LifeStanding.DEPARTED
    return LifeStanding.MOD_BANNED


def account_standing(
    status: AccountStatus,
    has_accepted_terms: bool,
    lives: Iterable[LifeStanding],
    carried_ban: bool = False,
) -> AccountStanding:
    """``carried_ban``: a live tombstone's mod ban (ADR-0081), kept past a return."""
    if status == AccountStatus.deleted:
        return AccountStanding.DELETED
    if status == AccountStatus.suspended:
        return AccountStanding.SUSPENDED
    if not has_accepted_terms:
        return AccountStanding.NEEDS_TERMS
    lives = list(lives)
    # S1 (#4204): a mod ban on any life stops the whole account, not one life.
    if carried_ban or LifeStanding.MOD_BANNED in lives:
        return AccountStanding.CREATION_BANNED
    if LifeStanding.ACTIVE in lives:
        return AccountStanding.PLAYING
    return AccountStanding.NO_CHARACTER


def standing_of(
    status: AccountStatus, character: Character
) -> tuple[AccountStanding, LifeStanding]:
    """Both standings from one row pair, for the set-wide queries that don't load
    terms or siblings (a hidden or counted check never reads them)."""
    life = life_standing(character)
    return account_standing(status, True, [life]), life


def is_playable(account: AccountStanding, life: LifeStanding) -> bool:
    return account == AccountStanding.PLAYING and life == LifeStanding.ACTIVE


_HIDDEN = (AccountStanding.SUSPENDED, AccountStanding.DELETED)


def is_public(account: AccountStanding, life: LifeStanding) -> bool:
    """Appears and links publicly: roster, leaderboard, profile."""
    return account not in _HIDDEN and life == LifeStanding.ACTIVE


def counts_as_voter(account: AccountStanding, life: LifeStanding) -> bool:
    """Self-deletion keeps votes (ADR-0081); a suspension or mod ban drops them."""
    return account != AccountStanding.SUSPENDED and life != LifeStanding.MOD_BANNED


@dataclass(frozen=True)
class PublicName:
    """``name`` is None when the UI shows the placeholder (S2b)."""

    name: Optional[str]
    suspended: bool
    linkable: bool


def public_name(name: str, account: AccountStanding, life: LifeStanding) -> PublicName:
    if account == AccountStanding.DELETED or life != LifeStanding.ACTIVE:
        return PublicName(None, False, False)
    if account == AccountStanding.SUSPENDED:
        return PublicName(name, True, False)
    return PublicName(name, False, True)


@dataclass(frozen=True)
class PublicIdentity:
    """A character as others see it. Absent loses name, username and face (S2b);
    the UI shows the label. Admin surfaces fall back to the id."""

    display_name: str
    username: str
    avatar_url: str
    name_state: NameState


def public_identity(character: Character) -> PublicIdentity:
    # vars(), never getattr: an unloaded or expired name_state would lazy-load from
    # sync code (MissingGreenlet). A just-created character reads as ok.
    raw = vars(character).get("name_state")
    if raw is None:
        logger.warning("name_state not loaded for character %s", character.id)
        raw = NameState.ok.value
    state = NameState(raw)
    if state == NameState.absent:
        return PublicIdentity("", "", "", state)
    return PublicIdentity(
        character.display_name, character.username, character.avatar_url, state
    )
