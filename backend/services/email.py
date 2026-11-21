"""Notification email (#2164): the Resend sender, the unsubscribe token and the message.

Wording lives in the shared catalog ``frontend/src/locales/en/email.json`` (ADR-0031):
mail is rendered here, so the backend reads it by relative path. Mail queues on the
session next to push (``services.push.notify``) and leaves only after the commit.
"""

import base64
import hashlib
import html
import json
import logging
from functools import cache
from pathlib import Path
from typing import Optional

import httpx
from cryptography.fernet import Fernet, InvalidToken

from config import settings

logger = logging.getLogger(__name__)

RESEND_URL = "https://api.resend.com/emails"
SEND_TIMEOUT_SECONDS = 10
_UNSUBSCRIBE_SALT = "email-unsubscribe"
# Dev: /repo/backend/services -> /repo. Prod image: the Dockerfile copies the file to
# the same relative spot under /.
_CATALOG = Path(__file__).resolve().parents[2] / "frontend/src/locales/en/email.json"


@cache
def _log_config_once(problem: str) -> None:
    logger.error("Email is OFF: %s", problem)


def email_available() -> bool:
    """On only with a key and a sender address; a key without one logs an ERROR."""
    if not settings.RESEND_API_KEY:  # blank on purpose: email is simply off
        return False
    if "@" not in settings.EMAIL_FROM:
        _log_config_once("RESEND_API_KEY is set but EMAIL_FROM is not an address")
        return False
    return True


async def send_email(
    to: str, subject: str, html: str, text: str, headers: dict[str, str]
) -> None:
    """One message through Resend's HTTP API. Raises on a refusal; no redirects."""
    async with httpx.AsyncClient(
        timeout=SEND_TIMEOUT_SECONDS, follow_redirects=False
    ) as client:
        response = await client.post(
            RESEND_URL,
            headers={"Authorization": f"Bearer {settings.RESEND_API_KEY}"},
            json={
                "from": settings.EMAIL_FROM,
                "to": [to],
                "subject": subject,
                "html": html,
                "text": text,
                "headers": headers,
            },
        )
    response.raise_for_status()


def _fernet() -> Fernet:
    seed = f"{_UNSUBSCRIBE_SALT}:{settings.SECRET_KEY}".encode()
    digest = hashlib.sha256(seed).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def unsubscribe_token(account_id: int, kind: str) -> str:
    """Encrypted and authenticated, never expires (an old mail must still work)."""
    return _fernet().encrypt(json.dumps([account_id, kind]).encode()).decode()


def read_unsubscribe_token(token: str) -> Optional[tuple[int, str]]:
    """``(account_id, kind)``, or None for anything forged or malformed."""
    try:
        account_id, kind = json.loads(_fernet().decrypt(token.encode()))
    except (InvalidToken, TypeError, ValueError):
        return None
    if not isinstance(account_id, int) or not isinstance(kind, str):
        return None
    return account_id, kind


def unsubscribe_page_url(token: str) -> str:
    return f"{settings.FRONTEND_URL.rstrip('/')}/unsubscribe?token={token}"


@cache
def catalog() -> dict:
    return json.loads(_CATALOG.read_text(encoding="utf-8"))


def _fill(template: str, **values: str) -> str:
    for name, value in values.items():
        template = template.replace("{{" + name + "}}", value)
    return template


def build_message(
    *,
    kind: str,
    token: str,
    url: str,
    actor: Optional[str] = None,
    task_title: Optional[str] = None,
    faction: Optional[str] = None,
) -> dict:
    """``subject``, ``html``, ``text`` and ``headers`` for one event.

    Every mail's footer says why it arrived, which setting sent it, and how to stop it.
    """
    copy = catalog()
    entry = copy["kinds"][kind]
    values = {
        "actor": actor or copy["someone"],
        "task": task_title or copy["aTask"],
        "faction": (faction or "").replace("_", " ").title() or copy["aFaction"],
    }
    subject = _fill(entry["subject"], **values)
    body = _fill(entry["body"], **values)
    why = _fill(copy["footer"]["why"], setting=entry["setting"])
    site = settings.FRONTEND_URL.rstrip("/")
    open_url = f"{site}{url}"
    stop_url = unsubscribe_page_url(token)
    settings_url = f"{site}/settings"
    api = settings.MEDIA_BASE_URL.rstrip("/").removesuffix("/media")
    esc = html.escape
    page = (
        f"<p>{esc(body)}</p>"
        f'<p><a href="{esc(open_url)}">{esc(copy["open"])}</a></p>'
        f"<hr><p>{esc(why)}</p>"
        f'<p><a href="{esc(stop_url)}">{esc(copy["footer"]["stop"])}</a> · '
        f'<a href="{esc(settings_url)}">{esc(copy["footer"]["settings"])}</a></p>'
    )
    text = (
        f"{body}\n\n{copy['open']}: {open_url}\n\n--\n{why}\n"
        f"{copy['footer']['stop']}: {stop_url}\n"
        f"{copy['footer']['settings']}: {settings_url}\n"
    )
    return {
        "subject": subject,
        "html": page,
        "text": text,
        "headers": {
            "List-Unsubscribe": f"<{api}/email/unsubscribe?token={token}>",
            "List-Unsubscribe-Post": "List-Unsubscribe=One-Click",
        },
    }
