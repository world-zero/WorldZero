"""Every row on the Notifications card has a push sender (#3678)."""

from services.notification_prefs import NOTIFICATION_EVENTS
from services.push import SENDERS


def test_every_preference_row_has_a_sender():
    assert set(SENDERS) == {event.key for event in NOTIFICATION_EVENTS}


async def test_broadcast_picks_only_active_lives(monkeypatch):
    """The select filters on status, so a banned lower-id life is skipped."""
    from services import push

    seen = {}

    class _Session:
        async def scalars(self, stmt):
            seen["sql"] = str(stmt.compile(compile_kwargs={"literal_binds": True}))

            class _R:
                def all(self):
                    return [7]

            return _R()

    sent = []

    async def _notify(session, **kw):
        sent.append(kw["recipient_id"])

    monkeypatch.setattr(push, "notify", _notify)
    await push.notify_broadcast(_Session(), kind="k", tag="t", url="/")
    assert "character.status = 'active'" in seen["sql"]
    assert "min(character.id)" in seen["sql"]
    assert sent == [7]
