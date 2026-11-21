"""0056 makes account 1 the owner and leaves every other prior admin with nothing.

Seam: the migration's own ``upgrade()``, its statements replayed on the session
over 0055-shaped role rows (the permission table already exists, as in 0056 itself).
"""
import importlib.util
from pathlib import Path

import pytest
from sqlalchemy import text

from models.account import Account

_PATH = (
    Path(__file__).resolve().parents[2] / "alembic/versions/0056_admin_permissions.py"
)


class _Recorder:
    def __init__(self):
        self.statements = []

    def execute(self, sql):
        self.statements.append(sql)


@pytest.mark.asyncio
async def test_upgrade_keeps_account_1_as_owner_and_strips_other_admins(db_session):
    spec = importlib.util.spec_from_file_location("admin_perm_migration", _PATH)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    recorder = migration.op = _Recorder()

    db_session.add_all([Account(id=1, email="a@example.com"),
                        Account(id=2, email="b@example.com")])
    await db_session.flush()
    await db_session.execute(text(
        "INSERT INTO role (name, description) VALUES ('admin', 'Administrator') "
        "ON CONFLICT (name) DO NOTHING"
    ))
    await db_session.execute(text(
        "INSERT INTO account_role (account_id, role_id, granted_by_id) "
        "SELECT a.id, r.id, a.id FROM account a, role r "
        "WHERE a.id IN (1, 2) AND r.name = 'admin'"
    ))

    migration.upgrade()
    for statement in recorder.statements:
        await db_session.execute(text(statement))

    held = (await db_session.execute(text(
        "SELECT ar.account_id, r.name FROM account_role ar "
        "JOIN role r ON r.id = ar.role_id ORDER BY 1"
    ))).all()
    assert held == [(1, "owner")]
    assert (await db_session.execute(
        text("SELECT count(*) FROM account_permission")
    )).scalar() == 0
