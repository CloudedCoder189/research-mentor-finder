"""Gmail draft orchestration.

Write boundary: this module may persist OAuth credentials (via ``token_store``)
and Gmail draft metadata on the caller's own ``professor_outreach`` row. It
never writes to the ``professors`` table, embeddings, verification, taxonomy,
or scraper data.
"""

from __future__ import annotations

from datetime import datetime, timezone

from api.gmail import config, drafts, oauth, token_store
from api.gmail.drafts import RecipientError  # re-exported for routes
from api.gmail.oauth import GmailApiError, GmailAuthError
from api.schemas.gmail import (
    GmailConnectResponse,
    GmailDraftRequest,
    GmailDraftResult,
    GmailStatus,
)
from api.schemas.user_state import outreach_result_dto
from api.services import _single_researcher
from database import DEFAULT_USER_ID, get_professor_outreach, update_professor_outreach


class DraftMissingError(RuntimeError):
    """No Gmail draft exists yet for this outreach row."""


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def status(user_id: str = DEFAULT_USER_ID) -> GmailStatus:
    try:
        available = bool(config.client_id() and config.client_secret())
    except config.ConfigError:
        available = False
    token = token_store.load_credentials(user_id).get("token", {})
    connected = bool(token.get("access_token")) and token.get("scope_verified") is True
    connected = connected and set(config.GMAIL_SCOPES).issubset(str(token.get("scope", "")).split())
    return GmailStatus(
        connected=connected,
        available=available,
        account_email=oauth.account_email(user_id) if connected else "",
        expires_in_seconds=oauth.expires_in_seconds(user_id) if connected else None,
    )


def begin_connect(user_id: str = DEFAULT_USER_ID) -> GmailConnectResponse:
    return GmailConnectResponse(auth_url=oauth.authorize_url(user_id))


def handle_callback(
    *,
    code: str | None,
    state: str,
    error: str | None,
    user_id: str = DEFAULT_USER_ID,
) -> str:
    if error:
        raise GmailAuthError("Access was denied at the Google consent screen.")
    if not code:
        raise GmailAuthError("Google did not return an authorization code.")
    expected = token_store.pop_pending_state(user_id)
    oauth.exchange_code(user_id, code, expected, state)
    return config.append_query(config.success_url(), gmail="connected")


def disconnect(user_id: str = DEFAULT_USER_ID) -> str:
    return oauth.revoke(user_id)


def _persist_content(
    professor_id: int,
    request: GmailDraftRequest,
    user_id: str,
    *,
    mark_drafted: bool,
) -> dict:
    current = get_professor_outreach([professor_id], user_id=user_id).get(professor_id, {})
    fields: dict[str, object] = {}
    if request.to is not None:
        fields["email_to"] = request.to
    if request.subject is not None:
        fields["email_subject"] = request.subject
    if request.body is not None:
        fields["email_body"] = request.body
    if request.notes is not None:
        fields["notes"] = request.notes
    if mark_drafted:
        current_status = str(current.get("outreach_status", "Not contacted") or "Not contacted")
        if current_status == "Not contacted":
            fields["outreach_status"] = "Email drafted"
    return update_professor_outreach(professor_id, user_id=user_id, **fields)  # type: ignore[arg-type]


def _result(professor_id: int, row: dict, user_id: str, draft: dict) -> GmailDraftResult:
    target = _single_researcher(int(professor_id))
    if target is None:
        raise ValueError("Professor record was not found.")
    merged = dict(target)
    merged.update(row)
    return GmailDraftResult(
        gmail_draft_id=str(draft.get("draft_id", "")),
        gmail_thread_id=str(draft.get("thread_id", "")),
        gmail_account_email=str(row.get("gmail_account_email", "") or ""),
        gmail_draft_created_at=str(row.get("gmail_draft_created_at", "") or ""),
        outreach=outreach_result_dto(merged),
    )


def _call_with_retry(user_id: str, operation):
    try:
        return operation(oauth.access_token(user_id))
    except GmailApiError as exc:
        if exc.status != 401:
            raise
        return operation(oauth.refresh_access_token_now(user_id))


def create_gmail_draft(
    professor_id: int,
    request: GmailDraftRequest,
    user_id: str = DEFAULT_USER_ID,
) -> GmailDraftResult:
    """Persist the local draft first, then create a real Gmail draft (no send)."""
    row = _persist_content(professor_id, request, user_id, mark_drafted=True)
    to = str(row.get("email_to", "") or "")
    subject = str(row.get("email_subject", "") or "")
    body = str(row.get("email_body", "") or "")
    drafts.validate_recipient(to)
    created = _call_with_retry(user_id, lambda token: drafts.create_draft(token, to, subject, body))
    row = update_professor_outreach(
        professor_id,
        user_id=user_id,
        gmail_draft_id=created["draft_id"],
        gmail_thread_id=created["thread_id"],
        gmail_account_email=oauth.account_email(user_id),
        gmail_draft_created_at=_now(),
    )
    return _result(professor_id, row, user_id, created)


def update_gmail_draft(
    professor_id: int,
    request: GmailDraftRequest,
    user_id: str = DEFAULT_USER_ID,
) -> GmailDraftResult:
    """Persist local edits first, then replace the existing Gmail draft (no send)."""
    row = _persist_content(professor_id, request, user_id, mark_drafted=False)
    draft_id = str(row.get("gmail_draft_id", "") or "")
    if not draft_id:
        raise DraftMissingError("No Gmail draft exists yet. Create one first.")
    to = str(row.get("email_to", "") or "")
    subject = str(row.get("email_subject", "") or "")
    body = str(row.get("email_body", "") or "")
    drafts.validate_recipient(to)
    updated = _call_with_retry(
        user_id, lambda token: drafts.update_draft(token, draft_id, to, subject, body)
    )
    row = update_professor_outreach(
        professor_id,
        user_id=user_id,
        gmail_draft_id=updated["draft_id"],
        gmail_thread_id=updated["thread_id"] or str(row.get("gmail_thread_id", "") or ""),
        gmail_account_email=oauth.account_email(user_id),
    )
    return _result(professor_id, row, user_id, updated)


__all__ = [
    "DraftMissingError",
    "GmailApiError",
    "GmailAuthError",
    "RecipientError",
    "begin_connect",
    "create_gmail_draft",
    "disconnect",
    "handle_callback",
    "status",
    "update_gmail_draft",
]
