"""Notification email (#2164): token, availability, catalog and the message itself.

Seam: ``services.email`` (``build_message``, the token pair, ``email_available``).
No network: ``send_email`` is never called here.
"""

import base64
from urllib.parse import quote

import pytest

from config import settings
from services.email import (
    build_message,
    catalog,
    email_available,
    read_unsubscribe_token,
    unsubscribe_token,
)
from services.notification_prefs import NOTIFICATION_EVENTS
from services.push import SENDERS

BROADCAST_ROWS = {"era_announcement", "rules_change", "global_task"}


def test_token_round_trips_and_hides_nothing_readable():
    token = unsubscribe_token(90817263541, "vote_on_mine")
    assert read_unsubscribe_token(token) == (90817263541, "vote_on_mine")
    assert "@" not in token
    for segment in token.replace("=", "").split("."):
        raw = base64.urlsafe_b64decode(segment + "=" * (-len(segment) % 4))
        assert b"90817263541" not in raw and b"vote_on_mine" not in raw


def test_a_tampered_or_foreign_token_is_rejected():
    token = unsubscribe_token(41, "vote_on_mine")
    assert read_unsubscribe_token(token[:-2] + "xx") is None
    assert read_unsubscribe_token("nonsense") is None
    assert read_unsubscribe_token("") is None


def test_email_is_off_and_silent_without_a_key(monkeypatch, caplog):
    monkeypatch.setattr(settings, "RESEND_API_KEY", "")
    assert email_available() is False
    assert caplog.records == []


def test_a_key_without_a_sender_is_off_and_logs(monkeypatch, caplog):
    monkeypatch.setattr(settings, "RESEND_API_KEY", "re_test")
    monkeypatch.setattr(settings, "EMAIL_FROM", "not an address")
    assert email_available() is False
    assert any("EMAIL_FROM" in record.getMessage() for record in caplog.records)


def test_a_key_and_sender_turn_email_on(monkeypatch):
    monkeypatch.setattr(settings, "RESEND_API_KEY", "re_test")
    monkeypatch.setattr(settings, "EMAIL_FROM", "hi@mail.worldzero.org")
    assert email_available() is True


def test_every_single_recipient_row_has_wording_and_no_broadcast_row_does():
    kinds = catalog()["kinds"]
    rows = {event.key for event in NOTIFICATION_EVENTS}
    assert set(kinds) == rows - BROADCAST_ROWS
    assert set(SENDERS) == rows
    for entry in kinds.values():
        assert entry["setting"] and entry["subject"] and entry["body"]


def test_the_footer_names_the_setting_and_the_stop_link_and_headers_are_set():
    token = unsubscribe_token(7, "comment_on_mine")
    message = build_message(
        kind="comment_on_mine",
        token=token,
        url="/praxis/9#comment-1",
        actor="Ada <b>",
        task_title="Feed a stranger",
    )
    assert message["subject"] == "Ada <b> commented on your praxis"
    for part in ("html", "text"):
        assert "Comments on my praxis" in message[part]
        assert f"/unsubscribe?token={quote(token, safe='')}" in message[part]
        assert "/settings" in message[part]
    assert "Ada <b>" not in message["html"]  # escaped
    assert message["headers"]["List-Unsubscribe"].endswith(
        f"/email/unsubscribe?token={token}>"
    )
    assert message["headers"]["List-Unsubscribe-Post"] == "List-Unsubscribe=One-Click"


@pytest.mark.parametrize("kind", sorted(catalog()["kinds"]))
def test_no_placeholder_is_left_unfilled(kind):
    message = build_message(kind=kind, token="t", url="/x")
    assert "{{" not in message["subject"] + message["html"] + message["text"]
