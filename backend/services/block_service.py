"""Block record service; a contact barrier (ADR-0077 and its #3867 amendment)."""
from typing import Union

from sqlalchemy import ColumnElement, Exists, Select, case, delete, exists, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from errors import ErrorCode, raise_coded
from models.character import Character
from models.character_block import CharacterBlock
from schemas.block import BlockListItem


def blocked_counterpart_ids(character_id: int) -> Select[tuple[int]]:
    """Every character silenced for ``character_id``, blocks read both ways.

    A ``SELECT`` so ``activity_feed`` can embed it as ``NOT IN`` without growing
    its pinned statement count; ``taunt_service`` executes it.
    """
    return select(
        case(
            (
                CharacterBlock.blocker_character_id == character_id,
                CharacterBlock.blocked_character_id,
            ),
            else_=CharacterBlock.blocker_character_id,
        )
    ).where(
        or_(
            CharacterBlock.blocker_character_id == character_id,
            CharacterBlock.blocked_character_id == character_id,
        )
    )


def has_blocked(
    blocker: Union[ColumnElement[int], int], blocked: Union[ColumnElement[int], int]
) -> Exists:
    """``blocker`` has blocked ``blocked``: one direction, correlates on columns."""
    return exists().where(
        CharacterBlock.blocker_character_id == blocker,
        CharacterBlock.blocked_character_id == blocked,
    )


async def blocked_by(character_id: int, session: AsyncSession) -> set[int]:
    return set(
        (
            await session.scalars(
                select(CharacterBlock.blocked_character_id).where(
                    CharacterBlock.blocker_character_id == character_id
                )
            )
        ).all()
    )


async def refuse_if_blocked(
    sender_id: int, recipient_id: int, session: AsyncSession
) -> None:
    """The blocker may not reach whom they blocked. Only the blocker hits this:
    the other way is swallowed, since a refusal would announce the block."""
    if await session.scalar(select(has_blocked(sender_id, recipient_id))):
        raise_coded(
            403,
            ErrorCode.contact_blocked,
            "You blocked this player, so you can't reach them.",
        )


def _to_item(character: Character, block: CharacterBlock) -> BlockListItem:
    return BlockListItem(
        character_id=character.id,
        display_name=character.display_name,
        avatar_url=character.avatar_url,
        faction_slug=character.faction_slug,
        created_at=block.created_at,
    )


async def block_character(
    blocker: Character,
    character_id: int,
    session: AsyncSession,
) -> BlockListItem:
    """Idempotent: re-blocking returns the existing record, not a conflict."""
    if character_id == blocker.id:
        raise_coded(422, ErrorCode.block_self, "Cannot block yourself.")

    target = await session.get(Character, character_id)
    if target is None:
        raise_coded(404, ErrorCode.character_not_found, "Target character not found.")

    existing = (
        await session.execute(
            select(CharacterBlock).where(
                CharacterBlock.blocker_character_id == blocker.id,
                CharacterBlock.blocked_character_id == character_id,
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        return _to_item(target, existing)

    block = CharacterBlock(
        blocker_character_id=blocker.id, blocked_character_id=character_id
    )
    session.add(block)
    await session.flush()
    await session.refresh(block)
    return _to_item(target, block)


async def unblock_character(
    blocker: Character,
    character_id: int,
    session: AsyncSession,
) -> None:
    """Restores no edge (ADR-0077 ruling 5). No match is a no-op, not a 404, so
    the blocked party learns nothing."""
    await session.execute(
        delete(CharacterBlock).where(
            CharacterBlock.blocker_character_id == blocker.id,
            CharacterBlock.blocked_character_id == character_id,
        )
    )
    await session.flush()


async def list_blocks(
    character_id: int,
    session: AsyncSession,
) -> list[BlockListItem]:
    """Outgoing blocks only: the blocked party must never read an incoming one."""
    rows = await session.execute(
        select(CharacterBlock, Character)
        .join(Character, Character.id == CharacterBlock.blocked_character_id)
        .where(CharacterBlock.blocker_character_id == character_id)
        .order_by(CharacterBlock.id)
    )
    return [_to_item(character, block) for block, character in rows.all()]
