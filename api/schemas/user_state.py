"""Models for the private local user-state endpoints (saved + outreach)."""

from __future__ import annotations

from datetime import date
from typing import Any

from pydantic import BaseModel, Field

from api.schemas.researcher import ResearcherSummary, summary_dto

# Presentation labels are frontend-facing. Stored values are never rewritten;
# the mapping below converts between the two at the API boundary.
FRONTEND_STATUS_BY_STORED: dict[str, str] = {
    "Not contacted": "Not contacted",
    "Email drafted": "Drafted",
    "Email sent": "Sent",
    "Follow-up needed": "Follow-up due",
    "Replied": "Replied",
    "Meeting scheduled": "Meeting scheduled",
    "Rejected": "Closed",
}

STORED_STATUS_BY_FRONTEND: dict[str, str] = {
    label: stored for stored, label in FRONTEND_STATUS_BY_STORED.items()
}

#: Statuses that end a follow-up cycle; a follow-up is never due for them.
FOLLOW_UP_ENDED_STORED = {"Replied", "Meeting scheduled", "Rejected"}


def follow_up_due(record: dict[str, Any]) -> bool:
    """A stored, deterministic follow-up signal (never derived from replies).

    Real Gmail send/reply timestamps (``gmail_sent_at``/``gmail_replied_at``)
    take part in the computation when present: a follow-up is due only when the
    email was actually sent, no reply has been received, and the user-set
    follow-up date is at or before today. The stored status is never changed by
    this read-only helper.
    """
    stored = str(record.get("outreach_status", ""))
    if stored == "Follow-up needed":
        return True
    if stored != "Email sent":
        return False
    gmail_sent_at = str(record.get("gmail_sent_at", "") or "").strip()
    email_sent_at = str(record.get("email_sent_at", "") or "").strip()
    gmail_replied_at = str(record.get("gmail_replied_at", "") or "").strip()
    follow_up_date = str(record.get("follow_up_date", "") or "").strip()
    sent_evidence = bool(gmail_sent_at or email_sent_at)
    return bool(
        sent_evidence
        and not gmail_replied_at
        and follow_up_date
        and follow_up_date <= date.today().isoformat()
    )


def frontend_status(record: dict[str, Any]) -> str:
    """Map a stored outreach row to its presentation status.

    Follow-up is derived on read, never stored: an email that was sent with a
    follow-up date at or before today reads as "Follow-up due" unless the
    conversation already ended in a reply, a meeting, or a rejection.
    """
    stored = str(record.get("outreach_status", "Not contacted"))
    if stored not in FRONTEND_STATUS_BY_STORED:
        stored = "Not contacted"
    if stored == "Email sent" and follow_up_due(record):
        return "Follow-up due"
    return FRONTEND_STATUS_BY_STORED[stored]


class OutreachState(BaseModel):
    is_favorite: bool
    status: str
    notes: str = ""
    email_sent_at: str = ""
    follow_up_date: str = ""
    email_to: str = ""
    email_subject: str = ""
    email_body: str = ""
    gmail_draft_id: str = ""
    gmail_thread_id: str = ""
    gmail_account_email: str = ""
    gmail_draft_created_at: str = ""
    gmail_sent_at: str = ""
    gmail_replied_at: str = ""
    gmail_reply_count: int = 0
    gmail_last_checked_at: str = ""
    updated_at: str = ""
    follow_up_due: bool = False


class OutreachResult(BaseModel):
    researcher: ResearcherSummary
    outreach: OutreachState


class SavedListResponse(BaseModel):
    total: int
    results: list[OutreachResult] = Field(default_factory=list)


class OutreachListResponse(BaseModel):
    total: int
    results: list[OutreachResult] = Field(default_factory=list)


class OutreachUpdate(BaseModel):
    expected_user_id: str | None = None
    outreach_status: str | None = None
    notes: str | None = None
    email_sent_at: str | None = None
    follow_up_date: str | None = None
    email_to: str | None = None
    email_subject: str | None = None
    email_body: str | None = None


class MutationResult(BaseModel):
    professor_id: int
    saved: bool


def outreach_state_dto(record: dict[str, Any]) -> OutreachState:
    is_favorite = int(record.get("is_favorite", 0) or 0)
    updated_at = str(record.get("outreach_updated_at", "") or "").strip()
    if not updated_at:
        updated_at = str(record.get("updated_at", "") or "").strip()
    return OutreachState(
        is_favorite=bool(is_favorite),
        status=frontend_status(record),
        notes=str(record.get("notes", "") or "").strip(),
        email_sent_at=str(record.get("email_sent_at", "") or "").strip(),
        follow_up_date=str(record.get("follow_up_date", "") or "").strip(),
        email_to=str(record.get("email_to", "") or "").strip(),
        email_subject=str(record.get("email_subject", "") or "").strip(),
        email_body=str(record.get("email_body", "") or "").strip(),
        gmail_draft_id=str(record.get("gmail_draft_id", "") or "").strip(),
        gmail_thread_id=str(record.get("gmail_thread_id", "") or "").strip(),
        gmail_account_email=str(record.get("gmail_account_email", "") or "").strip(),
        gmail_draft_created_at=str(record.get("gmail_draft_created_at", "") or "").strip(),
        gmail_sent_at=str(record.get("gmail_sent_at", "") or "").strip(),
        gmail_replied_at=str(record.get("gmail_replied_at", "") or "").strip(),
        gmail_reply_count=int(record.get("gmail_reply_count", 0) or 0),
        gmail_last_checked_at=str(record.get("gmail_last_checked_at", "") or "").strip(),
        updated_at=updated_at,
        follow_up_due=follow_up_due(record),
    )


def outreach_result_dto(record: dict[str, Any]) -> OutreachResult:
    """Build the public saved/outreach row, never leaking internal fields."""
    return OutreachResult(
        researcher=summary_dto(record),
        outreach=outreach_state_dto(record),
    )
