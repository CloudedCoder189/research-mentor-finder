"""Request/response models for the Gmail draft integration."""

from __future__ import annotations
from typing import Literal

from pydantic import BaseModel, Field

from api.gmail.config import GMAIL_DRAFTS_URL, GMAIL_SCOPES
from api.schemas.user_state import OutreachResult


class GmailStatus(BaseModel):
    connected: bool
    available: bool = False
    account_email: str = ""
    scope: str = GMAIL_SCOPES[0]
    expires_in_seconds: int | None = None
    draft_url: str = GMAIL_DRAFTS_URL


class GmailConnectResponse(BaseModel):
    auth_url: str


class GmailDisconnectResponse(BaseModel):
    disconnected: bool
    revocation: Literal["revoked", "unconfirmed", "not_connected"] = "unconfirmed"


class GmailDraftRequest(BaseModel):
    to: str | None = None
    subject: str | None = None
    body: str | None = None
    notes: str | None = None


class GmailDraftResult(BaseModel):
    gmail_draft_id: str
    gmail_thread_id: str
    gmail_account_email: str
    gmail_draft_created_at: str
    outreach: OutreachResult = Field(description="Updated user outreach state.")


class GmailSyncResult(BaseModel):
    professor_id: int
    linked: bool = False
    sent: bool = False
    replied: bool = False
    preserved: bool = Field(
        default=False,
        description="True when a manual terminal state was left untouched.",
    )
    not_sent_yet: bool = False
    checked_at: str = ""
    message: str = ""
    outreach: OutreachResult | None = None


class GmailSyncAllResult(BaseModel):
    checked: int = 0
    updated: int = 0
    errors: list[str] = Field(default_factory=list)
    results: list[GmailSyncResult] = Field(default_factory=list)


class FollowUpDraftResult(BaseModel):
    professor_id: int
    message: str = ""
    outreach: OutreachResult = Field(description="Updated user outreach state.")
