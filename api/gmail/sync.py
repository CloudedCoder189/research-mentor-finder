"""Gmail sent/reply detection and follow-up drafting for a user's outreach rows.

Write boundary: this module may write only per-user ``professor_outreach``
metadata/status (``gmail_sent_at``, ``gmail_replied_at``, ``gmail_reply_count``,
``gmail_last_checked_at``, and — via the status rules below — ``outreach_status``).
It never writes to the ``professors`` table, embeddings, verification, taxonomy,
or scraper data, never reads/store Gmail message bodies, and never sends email.

Status precedence (checked in order, never touching manual terminal states):
1. ``Meeting scheduled`` / ``Rejected`` are preserved as-is: metadata facts are
   still recorded, but the conversation state is never downgraded by Gmail data.
2. A detected reply promotes the conversation to ``Replied``.
3. Otherwise a detected send promotes ``Not contacted``/``Email drafted`` to
   ``Email sent``.
4. Otherwise the stored status is left untouched. Follow-up-due is derived on
   read from send/reply metadata plus the user's own follow-up date.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any, Callable

from api.gmail import oauth, threads
from api.gmail.oauth import GmailApiError
from api.gmail.threads import ThreadNotFoundError, elapsed_minutes
from api.schemas.gmail import (
    FollowUpDraftResult,
    GmailSyncAllResult,
    GmailSyncResult,
)
from api.schemas.user_state import outreach_result_dto
from api.services import _single_researcher
from database import (
    get_professor_outreach,
    get_student_profile,
    get_user,
    update_professor_outreach,
)

TERMINAL_STORED = ("Meeting scheduled", "Rejected")

_PRINTABLE_LINE = re.compile(r"[^\x20-\x7E\t\r\n]")


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _fetch(user_id: str, operation: Callable[[str], Any]) -> Any:
    try:
        return operation(oauth.access_token(user_id))
    except GmailApiError as exc:
        if exc.status != 401:
            raise
        return operation(oauth.refresh_access_token_now(user_id))


def _row_or_raise(professor_id: int, user_id: str) -> dict[str, Any]:
    row = get_professor_outreach([professor_id], user_id=user_id).get(professor_id)
    if not row:
        raise ValueError("Professor record was not found.")
    return dict(row)


def _result_dto(professor_id: int, row: dict[str, Any]) -> Any:
    target = _single_researcher(professor_id)
    if target is None:
        raise ValueError("Professor record was not found.")
    merged = dict(target)
    merged.update(row)
    return outreach_result_dto(merged)


def _sync_result(
    professor_id: int,
    row: dict[str, Any],
    *,
    linked: bool,
    sent: bool,
    replied: bool,
    preserved: bool,
    not_sent_yet: bool,
    checked_at: str,
    message: str = "",
) -> GmailSyncResult:
    outreach = None
    if linked or row:
        # Always include current outreach state so the UI can refresh.
        try:
            outreach = _result_dto(professor_id, row)
        except ValueError:
            outreach = None
    return GmailSyncResult(
        professor_id=professor_id,
        linked=linked,
        sent=sent,
        replied=replied,
        preserved=preserved,
        not_sent_yet=not_sent_yet,
        checked_at=checked_at,
        message=message,
        outreach=outreach,
    )


def sync_one(professor_id: int, *, user_id: str) -> GmailSyncResult:
    """Check one outreach row's Gmail thread and apply the status rules."""
    row = _row_or_raise(professor_id, user_id)
    thread_id = str(row.get("gmail_thread_id", "") or "")
    checked_at = _now()
    if not thread_id:
        return _sync_result(
            professor_id,
            row,
            linked=False,
            sent=False,
            replied=False,
            preserved=False,
            not_sent_yet=False,
            checked_at=checked_at,
            message="No Gmail link yet — create a Gmail draft and send it, then check again.",
        )

    try:
        state = _fetch(
            user_id, lambda token: threads.fetch_thread_state(token, thread_id)
        )
    except ThreadNotFoundError:
        row = update_professor_outreach(
            professor_id, user_id=user_id, gmail_last_checked_at=checked_at
        )
        return _sync_result(
            professor_id,
            row,
            linked=True,
            sent=False,
            replied=False,
            preserved=False,
            not_sent_yet=True,
            checked_at=checked_at,
            message="Checked Gmail: no sent message in this thread yet.",
        )

    fields: dict[str, object] = {
        "gmail_sent_at": state.sent_at,
        "gmail_replied_at": state.replied_at,
        "gmail_reply_count": state.reply_count,
        "gmail_last_checked_at": checked_at,
    }
    stored = str(row.get("outreach_status", "Not contacted") or "Not contacted")
    preserved = stored in TERMINAL_STORED
    if not preserved and state.replied:
        fields["outreach_status"] = "Replied"
    elif (
        not preserved
        and state.sent
        and stored in ("Not contacted", "Email drafted")
    ):
        fields["outreach_status"] = "Email sent"
    row = update_professor_outreach(professor_id, user_id=user_id, **fields)

    messages = []
    if preserved:
        messages.append("Conversation state was left as you set it.")
    if not state.sent:
        messages.append("Checked Gmail: no sent message in this thread yet.")
    elif not state.replied:
        messages.append("Checked Gmail: your email was sent.")
    if state.replied:
        messages.append("Checked Gmail: a reply was detected.")
    return _sync_result(
        professor_id,
        row,
        linked=True,
        sent=state.sent,
        replied=state.replied,
        preserved=preserved,
        not_sent_yet=not state.sent,
        checked_at=checked_at,
        message=" ".join(messages).strip(),
    )


def sync_all(*, user_id: str) -> GmailSyncAllResult:
    """Check every outreach row that has a Gmail thread link."""
    rows = get_professor_outreach(None, user_id=user_id)
    linked = [
        (int(pid), row)
        for pid, row in rows.items()
        if str(row.get("gmail_thread_id", "") or "")
    ]
    results: list[GmailSyncResult] = []
    errors: list[str] = []
    for professor_id, _row in linked:
        try:
            results.append(sync_one(professor_id, user_id=user_id))
        except GmailApiError as exc:
            errors.append(str(exc))
        except ValueError as exc:
            errors.append(str(exc))
    return GmailSyncAllResult(
        checked=len(linked),
        updated=len(results),
        errors=errors,
        results=results,
    )


def _timephrase(sent_at: str) -> str:
    minutes = elapsed_minutes(sent_at)
    if minutes <= 0:
        return "recently"
    days = minutes // 1440
    if days <= 0:
        hours = max(1, minutes // 60)
        return f"{hours} hour{'s' if hours != 1 else ''} ago"
    if days == 1:
        return "about a day ago"
    return f"about {days} days ago"


def _clean_plain(value: str) -> str:
    return _PRINTABLE_LINE.sub("", str(value or "")).strip()


def build_follow_up_draft(professor_id: int, *, user_id: str) -> FollowUpDraftResult:
    """Generate a grounded follow-up draft and persist it to local fields.

    Content is grounded in the professor, the original subject line, the actual
    elapsed time, and (when available) the student profile. It never claims the
    professor saw or read the email, ignored the student, is interested, or that
    any reply occurred. Nothing is sent and no Gmail call is made.
    """
    row = _row_or_raise(professor_id, user_id)
    target = _single_researcher(professor_id)
    if target is None:
        raise ValueError("Professor record was not found.")
    sent_at = str(row.get("gmail_sent_at", "") or row.get("email_sent_at", "") or "")
    if not sent_at:
        raise ValueError(
            "Add the date you sent this email before drafting a follow-up. "
            "Nothing is sent automatically."
        )
    to = str(row.get("email_to", "") or "").strip() or str(target.get("email", "") or "").strip()
    if not to:
        raise ValueError("No recipient email is known for this researcher.")
    subject = str(row.get("email_subject", "") or "").strip() or "(no subject)"

    user = get_user(user_id) or {}
    profile = get_student_profile(user_id) or {}
    display_name = str(user.get("display_name", "") or "").strip()
    first_name = display_name.split()[0] if display_name else ""
    interests = [str(item).strip() for item in (profile.get("interests") or []) if str(item).strip()]
    interest_line = ""
    if interests:
        interest_line = (
            f"\n\nA quick context line: I'm a student interested in {interests[0]}, "
            "which is what drew me to your work."
        )

    follow_up_body = (
        f"Dear {target.get('name', 'there')},\n\n"
        f"I emailed you {_timephrase(sent_at)} about \"{subject}\" and wanted to "
        "make sure my earlier note reached you - I know how full a schedule can be."
        f"{interest_line}"
        "\n\nIf it's still a good time and the opportunity fits your workload, I "
        "would be glad to hear your thoughts whenever convenient."
        "\n\nThank you for your time and for everything you share openly."
        f"\n\n{first_name or display_name}".strip()
    )

    row = update_professor_outreach(
        professor_id,
        user_id=user_id,
        email_to=to,
        email_subject=f"Following up: {subject}",
        email_body=_clean_plain(follow_up_body),
    )
    return FollowUpDraftResult(
        professor_id=professor_id,
        message="Follow-up draft generated from your sent email — nothing was sent.",
        outreach=_result_dto(professor_id, row),
    )


__all__ = [
    "TERMINAL_STORED",
    "build_follow_up_draft",
    "sync_all",
    "sync_one",
]
