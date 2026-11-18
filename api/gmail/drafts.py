"""Gmail draft create/update via raw REST (never sends anything)."""

from __future__ import annotations

import base64
import html as html_lib
import re
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import requests

from api.gmail.config import GMAIL_API_URL


class RecipientError(ValueError):
    """The recipient is not a usable email address."""


def validate_recipient(value: str) -> str:
    recipient = str(value or "").strip()
    if (
        not recipient
        or len(recipient) > 254
        or " " in recipient
        or "@" not in recipient
        or recipient.count("@") != 1
    ):
        raise RecipientError("Enter a valid recipient email address.")
    local, domain = recipient.rsplit("@", 1)
    if not local or not domain or "." not in domain:
        raise RecipientError("Enter a valid recipient email address.")
    if re.search(r"[^A-Za-z0-9._%+\-]", local):
        raise RecipientError("Enter a valid recipient email address.")
    return recipient.lower()


def build_mime_raw(to: str, subject: str, body: str) -> str:
    """Build an RFC 2822 MIME message and return it as base64url text."""
    message = MIMEMultipart("alternative")
    message["To"] = validate_recipient(to)
    message["Subject"] = str(subject or "").strip() or "(no subject)"
    message["X-Mailer"] = "Research-Mentor-Finder (draft only; nothing is sent)"
    plain = str(body or "").strip()
    message.attach(MIMEText(plain, "plain", "utf-8"))
    rendered = "<br>\n".join(html_lib.escape(line) for line in plain.splitlines())
    message.attach(MIMEText(f"<html><body>{rendered}</body></html>", "html", "utf-8"))
    return base64.urlsafe_b64encode(message.as_bytes()).decode("ascii")


def _call(access_token_value: str, method: str, url: str, payload: dict | None) -> dict:
    try:
        response = requests.request(
            method,
            url,
            headers={"Authorization": f"Bearer {access_token_value}"},
            json=payload or {},
            timeout=25,
        )
    except requests.RequestException as exc:
        from api.gmail.oauth import GmailApiError

        raise GmailApiError("Could not reach Gmail. Try again later.") from exc
    if response.status_code not in (200, 201):
        from api.gmail.oauth import GmailApiError

        raise GmailApiError(
            f"Gmail rejected the request (HTTP {response.status_code}).",
            status=response.status_code,
        )
    try:
        return response.json()
    except ValueError:
        return {}


def create_draft(access_token_value: str, to: str, subject: str, body: str) -> dict:
    """Create a real Gmail draft. Never sends it."""
    raw = build_mime_raw(to, subject, body)
    result = _call(
        access_token_value,
        "POST",
        f"{GMAIL_API_URL}/users/me/drafts",
        {"message": {"raw": raw}},
    )
    return {
        "draft_id": str(result.get("id") or ""),
        "thread_id": str(result.get("message", {}).get("threadId") or ""),
    }


def update_draft(access_token_value: str, draft_id: str, to: str, subject: str, body: str) -> dict:
    """Replace an existing Gmail draft's message. Never sends it."""
    if not draft_id:
        raise ValueError("No Gmail draft exists to update.")
    raw = build_mime_raw(to, subject, body)
    result = _call(
        access_token_value,
        "PUT",
        f"{GMAIL_API_URL}/users/me/drafts/{draft_id}",
        {"id": draft_id, "message": {"raw": raw}},
    )
    return {
        "draft_id": str(result.get("id") or "") or draft_id,
        "thread_id": str(result.get("message", {}).get("threadId") or ""),
    }
