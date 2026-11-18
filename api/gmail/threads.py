"""Read-only Gmail thread-metadata access for sent/reply detection.

Only ``users.threads.get`` with ``format=metadata`` is ever called, for thread
ids this installation already stored on its own ``professor_outreach`` rows.
The call is authorized by the ``gmail.metadata`` scope, which explicitly
excludes message bodies; we additionally ignore body/header content and only
look at ``labelIds`` and ``internalDate`` per message.

Write boundary: nothing is written to Gmail here (no send, no draft changes,
no label edits). The module does not store any Gmail message content.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

import requests

from api.gmail.config import GMAIL_API_URL
from api.gmail.oauth import GmailApiError


class ThreadNotFoundError(RuntimeError):
    """The stored thread id could not confirm a send.

    A 404 (or an unusable empty thread) means Gmail has no readable sent message
    for the stored thread id right now, so for UI purposes the row is treated as
    not currently detectable / not sent. This never asserts that drafts cannot
    create or participate in threads.
    """


class ThreadState:
    """Minimal, privacy-safe summary of one Gmail thread."""

    __slots__ = ("thread_id", "sent", "sent_at", "replied", "replied_at", "reply_count", "message_count")

    def __init__(
        self,
        thread_id: str,
        *,
        sent: bool,
        sent_at: str = "",
        replied: bool,
        replied_at: str = "",
        reply_count: int = 0,
        message_count: int = 0,
    ) -> None:
        self.thread_id = thread_id
        self.sent = sent
        self.sent_at = sent_at
        self.replied = replied
        self.replied_at = replied_at
        self.reply_count = reply_count
        self.message_count = message_count


def _iso(epoch_millis: object) -> str:
    try:
        millis = int(epoch_millis or 0)
    except (TypeError, ValueError):
        return ""
    if millis <= 0:
        return ""
    try:
        return datetime.fromtimestamp(millis / 1000.0, tz=timezone.utc).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        )
    except (OverflowError, OSError, ValueError):
        return ""


def _minutes_between(later_ms: int, earlier_ms: int) -> int:
    try:
        delta = timedelta(milliseconds=max(0, int(later_ms) - int(earlier_ms)))
        return int(delta.total_seconds() / 60)
    except (TypeError, ValueError):
        return 0


def fetch_thread_state(access_token_value: str, thread_id: str) -> ThreadState:
    """Fetch thread metadata and summarize sent/reply signals.

Sent-ness is decided exclusively by message labels: any message carrying the
``SENT`` label means ``sent`` (``sent_at`` records the earliest such message),
and a thread whose messages carry no ``SENT`` label — whether those are drafts,
empty, or otherwise — is reported as not sent. A 404 is treated as "not
currently detectable" and surfaced as ``ThreadNotFoundError`` for UI purposes;
this does not claim drafts cannot create threads, it only says no sent message
is available to read. Replies are ``INBOX``-labeled messages matched on their
own branch, so the original outbound message is never classified as a reply.
The optional ``reference_ms`` (the inbox-scan timestamp of a previous check)
is intentionally not used: state is always computed from the authoritative
thread data, so a reply is never "forgotten" between manual refreshes.
"""
    if not thread_id:
        raise ThreadNotFoundError("No Gmail thread link exists for this outreach record.")
    try:
        response = requests.get(
            f"{GMAIL_API_URL}/users/me/threads/{thread_id}?format=metadata",
            headers={"Authorization": f"Bearer {access_token_value}"},
            timeout=25,
        )
    except requests.RequestException as exc:
        raise GmailApiError("Could not reach Gmail. Try again later.") from exc
    if response.status_code == 404:
        raise ThreadNotFoundError(
            "No messages found in Gmail for this thread yet — not counted as sent."
        )
    if response.status_code not in (200, 201):
        raise GmailApiError(
            f"Gmail rejected the request (HTTP {response.status_code}).",
            status=response.status_code,
        )
    try:
        payload = response.json()
    except ValueError:
        payload = {}

    messages: list[dict[str, Any]] = []
    raw_messages = payload.get("messages")
    if isinstance(raw_messages, list):
        # internalDate is always present on real messages; guard against
        # malformed API responses so detection never misfires on fake rows.
        messages = [
            message
            for message in raw_messages
            if isinstance(message, dict)
            and message.get("id")
            and str(message.get("internalDate", "") or "").lstrip("-").isdigit()
            and int(message.get("internalDate", 0)) > 0
        ]

    sent_messages: list[dict[str, Any]] = []
    reply_messages: list[dict[str, Any]] = []
    for message in messages:
        labels = [str(label) for label in (message.get("labelIds") or [])]
        if "SENT" in labels:
            sent_messages.append(message)
        elif "INBOX" in labels:
            reply_messages.append(message)
    sent_messages.sort(key=lambda item: int(item.get("internalDate", 0)))
    reply_messages.sort(key=lambda item: int(item.get("internalDate", 0)))

    sent_at = _iso(sent_messages[0]["internalDate"]) if sent_messages else ""
    replied_at = _iso(reply_messages[-1]["internalDate"]) if reply_messages else ""
    return ThreadState(
        thread_id=thread_id,
        sent=bool(sent_messages),
        sent_at=sent_at,
        replied=bool(reply_messages),
        replied_at=replied_at,
        reply_count=len(reply_messages),
        message_count=len(messages),
    )


def elapsed_minutes(sent_at: str) -> int:
    """Minutes between ``sent_at`` (ISO) and now; 0 when unparseable."""
    try:
        sent = datetime.fromisoformat(str(sent_at).replace("Z", "+00:00"))
    except ValueError:
        return 0
    now = datetime.now(timezone.utc)
    if sent.tzinfo is None:
        sent = sent.replace(tzinfo=timezone.utc)
    return max(0, int((now - sent).total_seconds() / 60))


__all__ = [
    "ThreadNotFoundError",
    "ThreadState",
    "elapsed_minutes",
    "fetch_thread_state",
]
