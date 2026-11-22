"""The migration chain must produce the schema ``models/`` describes (#2426).

The rest of the suite builds its schema via ``create_all``, so this is the only
place the chain's result is checked. ``0003_squashed`` itself uses
``create_all``, so ``alembic check`` cannot see a model column with no revision;
two extra checks cover that:

* enum values: a model enum's ``ck_<table>_<enum>`` CHECK is created by a
  migration, so the DB's values are independent of the models.
* ``alembic/schema_snapshot.txt`` (#2448): a committed baseline, diffed like
  ``api-schema`` (#1584). Refreshing it blindly turns the check off.

``ponytail:`` the snapshot goes red on any schema change and can't tell migrated
from unmigrated; a human answers "where is the migration?". Upgrade: load the
snapshot, ``alembic stamp``, upgrade, check (needs snapshot to carry its revision).

Uses its own throwaway DB (name derived from ``TEST_DATABASE_URL``): the shared
test DB gets ``drop_all`` from parallel runners mid-migration.
"""
from __future__ import annotations

import difflib
import os
import re
import subprocess
import sys
from pathlib import Path

import asyncpg
import pytest_asyncio
from sqlalchemy import Enum as SAEnum
from sqlalchemy.engine import make_url

import models  # noqa: F401 — registers every mapped class on Base.metadata
from config import settings
from models.base import Base
from scripts.dump_schema_snapshot import (
    REGEN_COMMAND,
    SNAPSHOT_PATH,
    render_snapshot,
)

BACKEND_DIR = Path(__file__).resolve().parents[2]

MAX_DIFF_LINES = 60

_BASE_URL = make_url(os.environ.get("TEST_DATABASE_URL") or settings.DATABASE_URL)

# Derived, never fixed: it is DROPped unconditionally, so runners need their own.
MIGRATION_TEST_DB = f"{_BASE_URL.database}_migr"


def _dsn(database: str) -> str:
    return _BASE_URL.set(drivername="postgresql", database=database).render_as_string(
        hide_password=False
    )


def _alembic(*args: str) -> "subprocess.CompletedProcess[str]":
    _asyncpg_url = _dsn(MIGRATION_TEST_DB).replace("://", "+asyncpg://", 1)
    return subprocess.run(
        [sys.executable, "-m", "alembic", *args],
        cwd=BACKEND_DIR,
        env={**os.environ, "DATABASE_URL": _asyncpg_url},
        capture_output=True,
        text=True,
    )


def _report(label: str, result: "subprocess.CompletedProcess[str]") -> str:
    return (
        f"`alembic {label}` exited {result.returncode}\n"
        f"--- stdout ---\n{result.stdout}\n--- stderr ---\n{result.stderr}"
    )


async def _enum_values_in_db(database: str) -> dict[str, set[str]]:
    """Values each ``ck_<table>_<enum>`` CHECK admits, keyed by that name."""
    conn = await asyncpg.connect(_dsn(database))
    try:
        rows = await conn.fetch(
            "SELECT conname, pg_get_constraintdef(oid) AS definition FROM pg_constraint"
            " WHERE contype = 'c' AND connamespace = 'public'::regnamespace"
        )
    finally:
        await conn.close()
    return {
        row["conname"]: set(
            re.findall(r"'([^']*)'::character varying", row["definition"])
        )
        for row in rows
    }


def _enum_values_in_models() -> dict[str, set[str]]:
    declared: dict[str, set[str]] = {}
    for table in Base.metadata.tables.values():
        for column in table.columns:
            type_ = column.type
            if isinstance(type_, SAEnum) and type_.name:
                declared[f"ck_{table.name}_{type_.name}"] = set(type_.enums)
    return declared


@pytest_asyncio.fixture
async def migration_db() -> str:
    admin = await asyncpg.connect(_dsn("postgres"))
    try:
        await admin.execute(
            f'DROP DATABASE IF EXISTS "{MIGRATION_TEST_DB}" WITH (FORCE)'
        )
        await admin.execute(f'CREATE DATABASE "{MIGRATION_TEST_DB}"')
    finally:
        await admin.close()

    yield MIGRATION_TEST_DB

    admin = await asyncpg.connect(_dsn("postgres"))
    try:
        await admin.execute(
            f'DROP DATABASE IF EXISTS "{MIGRATION_TEST_DB}" WITH (FORCE)'
        )
    finally:
        await admin.close()


async def test_migrations_match_models(migration_db: str) -> None:
    """Upgrade, check, then down/up and re-check (catches a bad downgrade)."""
    upgrade = _alembic("upgrade", "head")
    assert upgrade.returncode == 0, _report("upgrade head", upgrade)

    check = _alembic("check")
    assert check.returncode == 0, (
        "The migration chain and models/ disagree. Autogenerate wants to emit "
        "operations that no revision performs, which means a deployed database "
        "would end up with a schema the ORM does not expect.\n\n"
        "Fix the migration (do NOT relax this check): add a revision carrying the "
        "change forward — see docs/agents/db-migrations.md.\n\n"
        + _report("check", check)
    )

    in_db = await _enum_values_in_db(migration_db)
    in_models = _enum_values_in_models()
    missing = {
        name: sorted(values - in_db.get(name, set()))
        for name, values in in_models.items()
        if values - in_db.get(name, set())
    }
    assert not missing, (
        "Enum values the models can produce that the migrated database's CHECK "
        f"rejects: {missing}\n\n"
        "The rest of the suite cannot see this: its create_all schema emits its "
        "own CHECK. A deployed database will reject the value at INSERT. "
        "Widen the CHECK in a new revision."
    )
    unreachable = {
        name: sorted(values - in_models.get(name, set()))
        for name, values in in_db.items()
        if name in in_models and values - in_models[name]
    }
    assert not unreachable, (
        "Enum values the CHECKs admit that no model declares — states the "
        f"database accepts and the application cannot produce: {unreachable}\n\n"
        "Drop them from the migration, or add them to the Python enum."
    )

    down = _alembic("downgrade", "-1")
    assert down.returncode == 0, (
        "The head revision has no working downgrade().\n\n"
        + _report("downgrade -1", down)
    )

    reupgrade = _alembic("upgrade", "head")
    assert reupgrade.returncode == 0, _report(
        "upgrade head (after downgrade)", reupgrade
    )

    recheck = _alembic("check")
    assert recheck.returncode == 0, (
        "downgrade -1 followed by upgrade head did not restore the schema.\n\n"
        + _report("check (after round trip)", recheck)
    )


async def test_migrated_schema_matches_the_committed_snapshot(
    migration_db: str,
) -> None:
    """#2448. ``read_text`` normalises a CRLF checkout to ``\\n``."""
    upgrade = _alembic("upgrade", "head")
    assert upgrade.returncode == 0, _report("upgrade head", upgrade)

    rendered = await render_snapshot(_dsn(migration_db))
    committed = SNAPSHOT_PATH.read_text(encoding="utf-8")
    if rendered == committed:
        return

    diff = list(
        difflib.unified_diff(
            committed.splitlines(),
            rendered.splitlines(),
            fromfile="alembic/schema_snapshot.txt (committed)",
            tofile="the database `alembic upgrade head` just built",
            lineterm="",
        )
    )
    shown = "\n".join(diff[:MAX_DIFF_LINES])
    if len(diff) > MAX_DIFF_LINES:
        shown += f"\n... and {len(diff) - MAX_DIFF_LINES} more diff line(s)."

    raise AssertionError(
        "The migrated schema and the committed snapshot disagree.\n\n"
        f"{shown}\n\n"
        "This is the check that sees what `alembic check` cannot: 0003_squashed "
        "builds its tables from Base.metadata, so a fresh database is the ORM's "
        "schema by construction and a model column with no revision behind it is "
        "absorbed silently (#2448). The committed file is not.\n\n"
        "IF YOU DID NOT INTEND A SCHEMA CHANGE, this is that drift: a model moved "
        "and no migration carries it forward, so an already-deployed database — "
        "production — will not have it. Add the revision; see "
        "docs/agents/db-migrations.md.\n\n"
        "IF YOU DID INTEND IT, regenerate the snapshot:\n"
        f"    {REGEN_COMMAND}\n"
        "then READ the diff it writes, line by line, and confirm every changed "
        "line is a change you meant AND that a migration carries it onto a "
        "deployed database. Commit it in the same PR as that migration. "
        "Refreshing this file to clear a red run without reading the diff turns "
        "the check off — it is the same move as raising a coverage floor instead "
        "of writing the test."
    )
