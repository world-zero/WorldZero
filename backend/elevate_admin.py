"""
Grant — or revoke — the owner role on a character's account.

The owner role is settable only here or in the DB, never from a web page
(ADR-0101). Idempotent grant; revoking a non-owner is refused.

Usage:
    python elevate_admin.py pixie                # dev (default)
    python elevate_admin.py pixie --env prod     # production
    python elevate_admin.py --env prod           # defaults username to 'pixie'
    python elevate_admin.py pixie --revoke       # take the owner role away

Ordinary admins (permission boxes) are made from ``/admin/admins`` by an owner.
"""

import argparse
import asyncio
import sys

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from models.character import Character
from models.roles import OWNER_ROLE_NAME, AccountRole, Role
from script_utils import add_env_argument, get_settings
from services.admin_service import assign_or_revoke_role
from services.mod_log import log_mod_action

ADMIN_ROLE_NAME = OWNER_ROLE_NAME
#: ``assign_or_revoke_role``'s action vocabulary — mirrors ``schemas.admin.RoleAction``.
REVOKE_ACTION = "revoke"


async def run(username: str, env: str, revoke: bool) -> None:
    settings = get_settings(env)
    print(f"Environment : {env}")
    print(f"Database    : {settings.DATABASE_URL.split('@')[-1]}\n")  # host/db only, no creds
    engine = create_async_engine(settings.DATABASE_URL, echo=False)
    async_session = async_sessionmaker(engine, expire_on_commit=False)

    async with async_session() as session:

        char_result = await session.execute(
            select(Character).where(Character.username == username)
        )
        character = char_result.scalar_one_or_none()
        if not character:
            print(f"ERROR: No character found with username '{username}'")
            await engine.dispose()
            sys.exit(1)

        account_id = character.account_id
        print(f"Found character '{username}' -> account_id={account_id}")

        if revoke:
            # assign_or_revoke_role is silent on a non-holder; a typo must not be.
            held = await session.execute(
                select(AccountRole)
                .join(Role, AccountRole.role_id == Role.id)
                .where(
                    AccountRole.account_id == account_id,
                    Role.name == ADMIN_ROLE_NAME,
                )
            )
            if held.scalar_one_or_none() is None:
                print(f"ERROR: account {account_id} ('{username}') is not an owner - nothing to revoke.")
                await engine.dispose()
                sys.exit(1)

            await assign_or_revoke_role(
                account_id=account_id,
                role_name=ADMIN_ROLE_NAME,
                action=REVOKE_ACTION,
                admin_account_id=account_id,
                session=session,
            )
            await session.commit()
            print(f"\nDone: Account {account_id} (character: '{username}') is no longer an owner.")
            await engine.dispose()
            return

        role_result = await session.execute(
            select(Role).where(Role.name == ADMIN_ROLE_NAME)
        )
        admin_role = role_result.scalar_one_or_none()
        if not admin_role:
            print("'owner' role not found - creating it")
            admin_role = Role(name=ADMIN_ROLE_NAME, description="Holds every permission")
            session.add(admin_role)
            await session.flush()
        else:
            print(f"Found 'owner' role (id={admin_role.id})")

        existing = await session.execute(
            select(AccountRole).where(
                AccountRole.account_id == account_id,
                AccountRole.role_id == admin_role.id,
            )
        )
        if existing.scalar_one_or_none():
            print(f"Account {account_id} is already an owner. Nothing to do.")
            await engine.dispose()
            return

        # Self-granted bootstrap.
        account_role = AccountRole(
            account_id=account_id,
            role_id=admin_role.id,
            granted_by_id=account_id,
        )
        session.add(account_role)
        await log_mod_action(
            session, account_id, "role_grant", "account", account_id, ADMIN_ROLE_NAME
        )
        await session.commit()

        print(f"\nDone: Account {account_id} (character: '{username}') is now an owner.")

    await engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(description="Grant or revoke the owner role on a character's account.")
    parser.add_argument("username", nargs="?", default="pixie", help="Character username (default: pixie)")
    add_env_argument(parser)
    parser.add_argument(
        "--revoke",
        action="store_true",
        help="Take the admin role away instead of granting it.",
    )
    args = parser.parse_args()
    asyncio.run(run(args.username, args.env, args.revoke))


if __name__ == "__main__":
    main()
