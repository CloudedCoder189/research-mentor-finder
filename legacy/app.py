from __future__ import annotations

import html
import logging
import os
import re
import time
from collections.abc import Iterable

import pandas as pd
import streamlit as st
from dotenv import load_dotenv

from database import (
    OUTREACH_STATUSES,
    ai_index_counts,
    consume_daily_usage,
    favorite_professor_ids,
    fetch_outreach_professors,
    fetch_professors,
    get_professor_outreach,
    initialize_database,
    list_department_categories,
    list_disciplines,
    list_fields,
    list_states,
    list_universities,
    outreach_counts,
    professor_count,
    query_cache_count,
    save_professor_outreach,
    set_professor_favorite,
    source_counts,
    update_verification_results,
    verification_counts,
    update_website_link_results,
    website_link_counts,
)
from scrapers.universities import IMPLEMENTED_SCRAPERS
from seed_data import seed_demo_data
from services.admin_auth import admin_access_decision, password_matches
from services.ai_enrichment import (
    AIIndexingError,
    enrich_records_with_openai,
    openai_available,
    query_embedding_with_source,
)
from services.audit_scope import AUDIT_SCOPES, select_audit_records
from services.categorization import CATEGORY_KEYWORDS
from services.pagination import (
    PAGE_SIZE_OPTIONS,
    clamp_page,
    page_bounds,
    page_count,
    paginate,
    parse_page_selection,
    sort_results,
)
from services.refresh import refresh_all_universities, refresh_university
from services.audit_repair import preview_v94_repair, run_v94_repair
from services.search import rank_professors
from services.ui_helpers import (
    filter_candidates,
    resolve_search_query,
    topic_chips_html,
    topic_values,
)
from services.verification import audit_records
from services.link_verification import (
    LINK_AUDIT_SCOPES,
    audit_website_links,
    select_link_records,
    website_is_publicly_usable,
)

load_dotenv()
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
LOGGER = logging.getLogger("professor_finder")

NOT_AVAILABLE = "Not publicly available"


def env_flag(name: str, default: bool = False) -> bool:
    raw_value = os.getenv(name)
    if raw_value is None:
        return default
    return raw_value.strip().casefold() in {"1", "true", "yes", "on"}


def env_int(name: str, default: int, minimum: int = 0) -> int:
    try:
        return max(minimum, int(os.getenv(name, str(default))))
    except ValueError:
        return max(minimum, default)


def _initialize_session_state() -> None:
    defaults = {
        "results": [],
        "audit_results": [],
        "website_audit_results": [],
        "refresh_all_results": [],
        "ai_index_summary": None,
        "audit_repair_summary": None,
        "search_metadata": {},
        "ai_search_count": 0,
        "current_page": 1,
        "selected_professor_ids": set(),
        "admin_authorized": False,
        "admin_login_attempts": 0,
        "quick_search_requested": False,
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


def _inject_css() -> None:
    st.markdown(
        """
        <style>
        .block-container {max-width: 1240px; padding-top: 1.5rem; padding-bottom: 4rem;}
        [data-testid="stSidebar"] {min-width: 310px; max-width: 340px;}
        .hero-card {
            padding: 2.1rem 2.25rem;
            border: 1px solid rgba(120,120,120,.22);
            border-radius: 1.25rem;
            background: linear-gradient(135deg, rgba(79,70,229,.10), rgba(14,165,233,.06));
            margin-bottom: 1rem;
        }
        .hero-eyebrow {font-size:.82rem; font-weight:800; letter-spacing:.12em; text-transform:uppercase; opacity:.72;}
        .hero-title {font-size:2.25rem; font-weight:850; line-height:1.08; margin:.4rem 0 .65rem 0;}
        .hero-copy {font-size:1.05rem; max-width:790px; opacity:.84; margin:0;}
        .topic-chip {
            display:inline-block; padding:.26rem .58rem; border-radius:999px;
            background:rgba(79,70,229,.10); border:1px solid rgba(79,70,229,.16);
            margin:0 .32rem .32rem 0; font-size:.82rem; font-weight:650;
        }
        .status-pill {
            display:inline-block; padding:.23rem .58rem; border-radius:999px;
            font-size:.79rem; font-weight:750; margin-right:.35rem;
        }
        .pill-strong,.pill-verified {background:#d1fae5;color:#065f46;}
        .pill-moderate,.pill-review {background:#fef3c7;color:#92400e;}
        .pill-basic,.pill-not-checked {background:#e5e7eb;color:#374151;}
        .pill-failed,.pill-rejected,.pill-broken {background:#fee2e2;color:#991b1b;}
        .pill-not-contacted,.pill-not-available {background:#e5e7eb;color:#374151;}
        .pill-email-drafted {background:#dbeafe;color:#1e40af;}
        .pill-email-sent {background:#ede9fe;color:#5b21b6;}
        .pill-follow-up-needed {background:#fef3c7;color:#92400e;}
        .pill-replied,.pill-meeting-scheduled {background:#d1fae5;color:#065f46;}
        .match-badge {
            display:inline-block; min-width:72px; text-align:center; padding:.38rem .62rem;
            border-radius:.8rem; font-weight:850; font-size:1.05rem;
            background:rgba(14,165,233,.12); border:1px solid rgba(14,165,233,.22);
        }
        .small-muted {font-size:.86rem; opacity:.72;}
        .result-title {font-size:1.28rem; font-weight:800; margin-bottom:.12rem;}
        .notice-card {padding:1rem 1.1rem; border-radius:.85rem; border:1px solid rgba(120,120,120,.2);}
        div[data-testid="stMetric"] {border:1px solid rgba(120,120,120,.18); padding:.65rem .8rem; border-radius:.85rem;}
        </style>
        """,
        unsafe_allow_html=True,
    )


def _clear_search_selection() -> None:
    for key in list(st.session_state):
        if str(key).startswith("select-professor-"):
            del st.session_state[key]
    st.session_state.selected_professor_ids = set()


def _set_example_query(query: str) -> None:
    st.session_state["search-query"] = query
    st.session_state.quick_search_requested = True


def _set_page(page: int, total_items: int, page_size: int) -> None:
    safe_page = clamp_page(page, total_items, page_size)
    st.session_state.current_page = safe_page
    st.session_state.page_picker = safe_page


def _page_picker_changed() -> None:
    st.session_state.current_page = parse_page_selection(
        st.session_state.get("page_picker"),
        default=st.session_state.get("current_page", 1),
    )


def _render_page_controls(*, total_items: int, page_size: int, location: str) -> None:
    total_pages = page_count(total_items, page_size)
    current_page = clamp_page(st.session_state.current_page, total_items, page_size)
    st.session_state.current_page = current_page
    if st.session_state.get("page_picker") not in range(1, total_pages + 1):
        st.session_state.page_picker = current_page

    first_col, previous_col, page_col, next_col, last_col = st.columns([1, 1.2, 2.1, 1.2, 1])
    with first_col:
        st.button(
            "⇤ First",
            key=f"first-{location}",
            disabled=current_page <= 1,
            use_container_width=True,
            on_click=_set_page,
            args=(1, total_items, page_size),
        )
    with previous_col:
        st.button(
            "← Previous",
            key=f"previous-{location}",
            disabled=current_page <= 1,
            use_container_width=True,
            on_click=_set_page,
            args=(current_page - 1, total_items, page_size),
        )
    with page_col:
        if location == "top":
            st.selectbox(
                "Page",
                options=list(range(1, total_pages + 1)),
                key="page_picker",
                label_visibility="collapsed",
                format_func=lambda value: f"Page {value} of {total_pages}",
                on_change=_page_picker_changed,
            )
        else:
            st.markdown(
                f"<div style='text-align:center;padding:.45rem'>Page {current_page} of {total_pages}</div>",
                unsafe_allow_html=True,
            )
    with next_col:
        st.button(
            "Next →",
            key=f"next-{location}",
            disabled=current_page >= total_pages,
            use_container_width=True,
            on_click=_set_page,
            args=(current_page + 1, total_items, page_size),
        )
    with last_col:
        st.button(
            "Last ⇥",
            key=f"last-{location}",
            disabled=current_page >= total_pages,
            use_container_width=True,
            on_click=_set_page,
            args=(total_pages, total_items, page_size),
        )


def _export_dataframe(records: list[dict]) -> pd.DataFrame:
    export_columns = [
        "name",
        "university",
        "city",
        "state",
        "department",
        "department_category",
        "title",
        "research_interests",
        "categories",
        "ai_categories",
        "ai_summary",
        "match_score",
        "keyword_score",
        "semantic_score",
        "search_mode",
        "match_reason",
        "opportunity_level",
        "opportunity_signals",
        "opportunity_source_url",
        "email",
        "website_url",
        "website_status",
        "website_issue",
        "website_checked_at",
        "website_final_url",
        "profile_url",
        "data_source_url",
        "source_type",
        "verification_status",
        "verification_issues",
        "verified_at",
        "last_checked_at",
        "updated_at",
        "is_favorite",
        "outreach_status",
        "email_sent_at",
        "follow_up_date",
        "notes",
        "outreach_updated_at",
    ]
    frame = pd.DataFrame(records)
    for column in export_columns:
        if column not in frame.columns:
            frame[column] = NOT_AVAILABLE
    return frame[export_columns]


def _records_with_outreach(records: list[dict]) -> list[dict]:
    professor_ids = [int(record.get("id", 0)) for record in records if int(record.get("id", 0)) > 0]
    outreach_by_id = get_professor_outreach(professor_ids)
    merged_records: list[dict] = []
    for record in records:
        merged = dict(record)
        outreach = outreach_by_id.get(int(record.get("id", 0)), {})
        merged.update(
            {
                "is_favorite": int(outreach.get("is_favorite", 0) or 0),
                "notes": str(outreach.get("notes", "")),
                "outreach_status": str(outreach.get("outreach_status", "Not contacted")),
                "email_sent_at": str(outreach.get("email_sent_at", "")),
                "follow_up_date": str(outreach.get("follow_up_date", "")),
                "outreach_updated_at": str(outreach.get("updated_at", "")),
            }
        )
        merged_records.append(merged)
    return merged_records


def _outreach_export_dataframe(records: list[dict]) -> pd.DataFrame:
    columns = [
        "name",
        "university",
        "department",
        "title",
        "research_interests",
        "email",
        "profile_url",
        "website_url",
        "verification_status",
        "is_favorite",
        "outreach_status",
        "email_sent_at",
        "follow_up_date",
        "notes",
        "outreach_updated_at",
    ]
    frame = pd.DataFrame(records)
    for column in columns:
        if column not in frame.columns:
            frame[column] = ""
    frame["is_favorite"] = frame["is_favorite"].map(
        lambda value: "Yes" if bool(int(value or 0)) else "No"
    )
    return frame[columns]


def _toggle_favorite_from_button(
    professor_id: int,
    professor_name: str = "",
    target_favorite: bool = True,
) -> None:
    """Persist a shortlist toggle without rendering any UI inside the callback."""
    new_value = bool(target_favorite)
    name_display = f" for {professor_name}" if professor_name else ""
    try:
        set_professor_favorite(professor_id, new_value)
    except ValueError as exc:
        st.session_state["shortlist_feedback"] = ("error", str(exc))
        return

    for key in list(st.session_state):
        if str(key).endswith(f"-outreach-favorite-{professor_id}"):
            st.session_state[key] = new_value

    st.session_state["shortlist_feedback"] = (
        "saved" if new_value else "removed",
        f"Saved{name_display} to shortlist" if new_value else f"Removed{name_display} from shortlist",
    )


def _render_favorite_button(
    professor_id: int,
    *,
    is_favorite: bool,
    professor_name: str = "",
    key_prefix: str = "search",
) -> None:
    """Render a responsive shortlist control synchronized with global state."""
    label = "🗑 Remove from shortlist" if is_favorite else "⭐ Save to shortlist"
    help_text = (
        "Remove this professor from your persistent shortlist."
        if is_favorite
        else "Save this professor to your persistent shortlist."
    )
    st.button(
        label,
        key=f"{key_prefix}-favorite-action-{professor_id}",
        use_container_width=True,
        type="secondary",
        help=help_text,
        on_click=_toggle_favorite_from_button,
        args=(professor_id, professor_name, not is_favorite),
    )


def _render_feedback_toast() -> None:
    """Display any pending toast or error feedback queued from callbacks."""
    feedback = st.session_state.pop("shortlist_feedback", None)
    if feedback:
        feedback_type, feedback_message = feedback
        if feedback_type == "error":
            st.error(feedback_message)
        elif feedback_type == "saved":
            st.toast(feedback_message, icon="⭐")
        else:
            st.toast(feedback_message, icon="🗑️")


def _render_outreach_editor(
    professor: dict,
    outreach: dict,
    *,
    key_prefix: str,
    allow_favorite_edit: bool,
) -> None:
    professor_id = int(professor.get("id", 0))
    current_status = str(outreach.get("outreach_status", "Not contacted"))
    if current_status not in OUTREACH_STATUSES:
        current_status = "Not contacted"
    with st.form(f"{key_prefix}-outreach-form-{professor_id}", clear_on_submit=False):
        favorite = bool(int(outreach.get("is_favorite", 0) or 0))
        if allow_favorite_edit:
            first_row = st.columns([1, 1.4])
            favorite_label = (
                "Keep on shortlist — uncheck to remove"
                if favorite
                else "Add to shortlist"
            )
            favorite = first_row[0].checkbox(
                favorite_label,
                value=favorite,
                key=f"{key_prefix}-outreach-favorite-{professor_id}",
            )
            status_container = first_row[1]
        else:
            status_container = st.container()
        status = status_container.selectbox(
            "Outreach status",
            OUTREACH_STATUSES,
            index=OUTREACH_STATUSES.index(current_status),
            key=f"{key_prefix}-outreach-status-{professor_id}",
        )
        date_cols = st.columns(2)
        email_sent_at = date_cols[0].text_input(
            "Email sent date",
            value=str(outreach.get("email_sent_at", "")),
            placeholder="YYYY-MM-DD",
            key=f"{key_prefix}-sent-date-{professor_id}",
        )
        follow_up_date = date_cols[1].text_input(
            "Follow-up date",
            value=str(outreach.get("follow_up_date", "")),
            placeholder="YYYY-MM-DD",
            key=f"{key_prefix}-followup-date-{professor_id}",
        )
        notes = st.text_area(
            "Private notes",
            value=str(outreach.get("notes", "")),
            placeholder="Why this professor matches, email details, response notes, or next steps",
            height=100,
            key=f"{key_prefix}-notes-{professor_id}",
        )
        submitted = st.form_submit_button("Save outreach details", use_container_width=True)
    if submitted:
        try:
            save_professor_outreach(
                professor_id,
                is_favorite=favorite,
                outreach_status=status,
                notes=notes,
                email_sent_at=email_sent_at,
                follow_up_date=follow_up_date,
            )
        except ValueError as exc:
            st.error(str(exc))
        else:
            st.session_state["shortlist_feedback"] = (
                "saved",
                f"Saved outreach details for {professor.get('name', 'professor')}",
            )
            st.rerun()


def _render_outreach_dashboard() -> None:
    counts = outreach_counts()
    with st.expander(
        f"My shortlist & outreach — {counts['shortlisted']:,} shortlisted",
        expanded=False,
    ):
        st.caption(
            "Stored only in this local database. Public deployments keep this section owner-only so visitors do not share private notes."
        )
        metric_cols = st.columns(4)
        metric_cols[0].metric("Shortlisted", counts["shortlisted"])
        metric_cols[1].metric("Contacted", counts["contacted"])
        metric_cols[2].metric("Follow-ups due", counts["follow_ups_due"])
        metric_cols[3].metric("Replies / meetings", counts["positive_responses"])

        filter_cols = st.columns([1.4, 1])
        status_filter = filter_cols[0].selectbox(
            "Show outreach status",
            ["All statuses", *OUTREACH_STATUSES],
            key="outreach-dashboard-status",
        )
        favorites_only = filter_cols[1].checkbox(
            "Shortlisted only",
            value=True,
            key="outreach-dashboard-favorites-only",
        )
        records = fetch_outreach_professors(
            favorites_only=favorites_only,
            status=status_filter,
        )
        if not records:
            st.info(
                "No professors match this view yet. Save a professor from the search results to begin your shortlist."
            )
            return

        st.download_button(
            "Download outreach tracker CSV",
            _outreach_export_dataframe(records).to_csv(index=False).encode("utf-8"),
            "professor_outreach_tracker.csv",
            "text/csv",
            use_container_width=True,
        )
        st.caption(f"Showing {len(records):,} saved or tracked professor(s).")
        for professor in records:
            professor_id = int(professor["id"])
            is_fav = bool(int(professor.get("is_favorite", 0) or 0))
            status = str(professor.get("outreach_status", "Not contacted"))
            with st.container(border=True):
                heading_cols = st.columns([5, 1.4])
                heading_cols[0].markdown(
                    f"**{html.escape(str(professor['name']))}** — "
                    f"{html.escape(str(professor['university']))}"
                )
                heading_cols[1].markdown(
                    f"<span class='status-pill pill-{_status_class(status)}'>{html.escape(status)}</span>",
                    unsafe_allow_html=True,
                )
                detail_bits = []
                if str(professor.get("email_sent_at", "")).strip():
                    detail_bits.append(f"Sent: {professor['email_sent_at']}")
                if str(professor.get("follow_up_date", "")).strip():
                    detail_bits.append(f"Follow up: {professor['follow_up_date']}")
                if detail_bits:
                    st.caption(" · ".join(detail_bits))

                action_cols = st.columns([1.6, 1, 1, 2.4])
                remove_label = "🗑 Remove from shortlist" if is_fav else "⭐ Save to shortlist"
                remove_help = (
                    "Remove this professor from your persistent shortlist."
                    if is_fav
                    else "Save this professor to your persistent shortlist."
                )
                action_cols[0].button(
                    remove_label,
                    key=f"dashboard-favorite-action-{professor_id}",
                    use_container_width=True,
                    type="secondary",
                    help=remove_help,
                    on_click=_toggle_favorite_from_button,
                    args=(professor_id, str(professor.get("name", "professor")), not is_fav),
                )
                profile_url = str(professor.get("profile_url", NOT_AVAILABLE))
                website_url = str(professor.get("website_url", NOT_AVAILABLE))
                if profile_url != NOT_AVAILABLE:
                    action_cols[1].link_button("Faculty profile", profile_url, use_container_width=True)
                if website_url != NOT_AVAILABLE:
                    action_cols[2].link_button("Website or lab", website_url, use_container_width=True)
                action_cols[3].markdown(f"**Email:** `{html.escape(str(professor.get('email', NOT_AVAILABLE)))}`")

                with st.expander("Edit notes and outreach", expanded=False):
                    _render_outreach_editor(
                        professor,
                        professor,
                        key_prefix="dashboard",
                        allow_favorite_edit=True,
                    )


def _status_class(value: str) -> str:
    return re.sub(r"[^a-z]+", "-", value.casefold()).strip("-")


def _safe_public_error(message: str) -> None:
    LOGGER.exception(message)
    st.error("Something went wrong, but the app stayed online. Try again or use keyword search.")


def _render_admin_access(admin_tools_enabled: bool, *, public_mode: bool) -> bool:
    if not admin_tools_enabled:
        return False

    plain_password = os.getenv("ADMIN_PASSWORD", "").strip()
    password_hash = os.getenv("ADMIN_PASSWORD_SHA256", "").strip()
    decision = admin_access_decision(public_mode, bool(plain_password or password_hash))
    if decision == "fail_closed":
        st.warning(
            "Owner tools are enabled for this public deployment, but neither ADMIN_PASSWORD nor "
            "ADMIN_PASSWORD_SHA256 is configured. Owner tools stay locked and will not auto-authorize."
        )
        return False
    if decision == "auto_unlock":
        st.session_state.admin_authorized = True
        st.caption("Owner tools are unlocked for this local environment.")
        return True

    if st.session_state.admin_authorized:
        left, right = st.columns([3, 1])
        left.success("Owner tools unlocked")
        if right.button("Lock", use_container_width=True):
            st.session_state.admin_authorized = False
            st.rerun()
        return True

    with st.expander("Owner access", expanded=False):
        st.caption("Public visitors cannot see database, indexing, or audit controls.")
        password = st.text_input("Admin password", type="password", key="admin-password-input")
        locked = st.session_state.admin_login_attempts >= 8
        if st.button("Unlock owner tools", disabled=locked, use_container_width=True):
            if password_matches(password, plain=plain_password, sha256_hash=password_hash):
                st.session_state.admin_authorized = True
                st.session_state.admin_login_attempts = 0
                st.rerun()
            else:
                st.session_state.admin_login_attempts += 1
                st.error("Incorrect password.")
        if locked:
            st.warning("Too many attempts in this browser session. Restart the session to try again.")
    return False


def _render_admin_tools(
    *,
    supported: list[str],
    imported_universities: list[str],
    live_count: int,
    all_records: list[dict] | None = None,
) -> None:
    if all_records is None:
        all_records = fetch_professors()
    with st.expander("V9.4 audit repair", expanded=False):
        try:
            repair_preview = preview_v94_repair()
            if repair_preview["already_applied"]:
                st.success("The one-time V9.4 audit preparation has already been applied.")
            else:
                st.warning(
                    "This creates a timestamped database backup and prepares the audited rows for "
                    "safe re-import. It does not delete UC Irvine or Cal Poly records before a "
                    "successful full authoritative refresh."
                )
                left, middle, right = st.columns(3)
                left.metric("UC Irvine to refresh", repair_preview["uci_records_to_refresh"])
                middle.metric("Cal Poly to refresh", repair_preview["calpoly_records_to_refresh"])
                right.metric("UC Davis to re-audit", repair_preview["ucdavis_records_to_reaudit"])
                st.caption(
                    f"Also repairs {repair_preview['ucsb_profiles_to_repair']} missing UCSB profile "
                    f"fallback(s) and cleans {repair_preview['research_rows_with_contact_text']} "
                    "research field(s) containing contact information."
                )
                if st.button("Back up and prepare audited records", use_container_width=True):
                    with st.spinner("Backing up and preparing audited records..."):
                        st.session_state.audit_repair_summary = run_v94_repair()
                    st.rerun()

            repair_summary = st.session_state.get("audit_repair_summary")
            if repair_summary and not repair_summary.get("already_applied"):
                st.success("Audit preparation finished without deleting UCI or Cal Poly records.")
                st.code(str(repair_summary.get("backup_path", "")), language=None)
                st.caption(
                    f"Marked for full refresh: UCI {repair_summary.get('uci_marked_for_refresh', 0)}, "
                    f"Cal Poly {repair_summary.get('calpoly_marked_for_refresh', 0)} · "
                    f"UC Davis re-audit {repair_summary.get('ucdavis_marked_for_reaudit', 0)} · "
                    f"Research rows cleaned {repair_summary.get('research_rows_cleaned', 0)}."
                )
                st.info(
                    "Next: test 10 UCI and 10 Cal Poly records. If each test looks correct, run a "
                    "full refresh for that university with the smaller-test option off. Only a "
                    "successful full refresh removes stale records from the old connector."
                )
        except Exception:
            _safe_public_error("V9.4 audit preparation failed")

    with st.expander("Database refresh", expanded=live_count == 0):
        refresh_university_name = st.selectbox(
            "University to import", supported, key="refresh-university"
        )
        profile_limit_enabled = st.checkbox("Use a smaller test refresh", value=True)
        max_profiles = (
            st.slider("Profiles to import/check per university", 5, 100, 20, step=5)
            if profile_limit_enabled
            else None
        )
        st.caption(
            "Refreshes run only for the owner. Unchanged records keep their audit and AI index; "
            "changed records are marked for targeted rechecking."
        )
        if (
            refresh_university_name in {
                "University of California, Irvine",
                "California Polytechnic State University, San Luis Obispo",
            }
            and max_profiles is not None
        ):
            st.info(
                "This small test will not remove old audited rows. After the test looks correct, "
                "run this university again with the smaller-test option off."
            )
        if st.button("Refresh selected university", use_container_width=True):
            status_box = st.empty()
            try:
                with st.spinner(f"Collecting public records from {refresh_university_name}..."):
                    summary = refresh_university(
                        refresh_university_name,
                        use_openai=False,
                        max_profiles=max_profiles,
                        progress_callback=status_box.info,
                    )
                if int(summary["saved"]) > 0:
                    detail = str(summary.get("error", "") or "").strip()
                    pruned = int(summary.get("pruned", 0))
                    message = (
                        f"Saved or checked {summary['saved']} record(s) from {summary['university']}."
                    )
                    if pruned:
                        message += f" Removed {pruned} stale record(s) after the full authoritative refresh."
                    status_box.success(message)
                    if detail:
                        st.caption(f"Source note: {detail}")
                    st.session_state.results = []
                else:
                    detail = str(summary.get("error", "") or "").strip()
                    if detail:
                        status_box.warning(f"No records were saved. Source detail: {detail}")
                    else:
                        status_box.warning(
                            "No records were saved. The source may have changed or the checked profiles "
                            "may not publish public email addresses."
                        )
            except Exception:
                _safe_public_error("Selected-university refresh failed")

        st.divider()
        if st.button("Refresh all supported universities", use_container_width=True):
            all_status = st.empty()
            all_progress = st.progress(0, text="Starting all-university refresh...")

            def show_progress(message: str) -> None:
                match = re.match(r"\[(\d+)/(\d+)\]", message)
                if match:
                    current, total = int(match.group(1)), max(int(match.group(2)), 1)
                    all_progress.progress(min(current / total, 1.0), text=f"University {current} of {total}")
                all_status.info(message)

            try:
                summary = refresh_all_universities(
                    use_openai=False,
                    max_profiles_per_university=max_profiles,
                    progress_callback=show_progress,
                )
                all_progress.progress(1.0, text="All-university refresh finished")
                st.session_state.refresh_all_results = summary["results"]
                st.session_state.results = []
                all_status.success(
                    f"Finished {summary['universities_attempted']} universities: "
                    f"{summary['saved']} saved/checked, {summary['pruned']} stale removed, "
                    f"{summary['failed']} failed, {summary['empty']} empty."
                )
            except Exception:
                _safe_public_error("All-university refresh failed")

        refresh_results = st.session_state.get("refresh_all_results", [])
        if refresh_results:
            frame = pd.DataFrame(refresh_results)
            st.dataframe(frame, hide_index=True, use_container_width=True)
            st.download_button(
                "Download refresh summary",
                frame.to_csv(index=False).encode("utf-8"),
                "all_university_refresh_summary.csv",
                "text/csv",
                use_container_width=True,
            )

    with st.expander("OpenAI search index", expanded=False):
        counts = ai_index_counts()
        st.caption(
            f"Indexed: {counts['indexed']} / {counts['total']} live records · "
            f"AI summaries: {counts['summarized']} · Cached public queries: {query_cache_count()}"
        )
        if not openai_available():
            st.warning("Add OPENAI_API_KEY to .env or deployment secrets, then restart.")
        else:
            scope = st.selectbox(
                "Records to index",
                ["All imported records", *sorted(imported_universities)],
                key="ai-index-scope",
            )
            only_missing = st.checkbox("Only records missing an embedding", value=True)
            generate_text = st.checkbox("Generate AI topic labels and summaries", value=True)
            limit_enabled = st.checkbox("Use a smaller AI test first", value=True)
            limit = st.slider("Records to process", 5, 100, 10, step=5) if limit_enabled else None
            if st.button("Build or update AI search index", use_container_width=True):
                status = st.empty()
                records = fetch_professors(None if scope == "All imported records" else scope)
                try:
                    summary = enrich_records_with_openai(
                        records,
                        generate_topics_and_summaries=generate_text,
                        only_missing=only_missing,
                        max_records=limit,
                        progress_callback=status.info,
                    )
                    st.session_state.ai_index_summary = summary
                    status.success(
                        f"Indexed {summary['embedded']} record(s); generated text for "
                        f"{summary['text_enriched']} record(s)."
                    )
                    st.session_state.results = []
                except AIIndexingError as exc:
                    LOGGER.exception("AI indexing failed after partial progress")
                    status.error(str(exc))
                except Exception:
                    _safe_public_error("AI indexing failed")

    with st.expander("Website and lab link reliability", expanded=False):
        link_scope = st.selectbox("Link-check scope", LINK_AUDIT_SCOPES, key="link-audit-scope")
        link_university = None
        if link_scope == "One university":
            if imported_universities:
                link_university = st.selectbox(
                    "University",
                    sorted(imported_universities),
                    key="link-audit-university",
                )
            else:
                st.info(
                    "No universities are imported yet. Add data before using a one-university link check."
                )
        link_candidates = select_link_records(
            all_records,
            scope=link_scope,
            university=link_university,
            selected_ids=set(st.session_state.selected_professor_ids),
        )
        st.caption(
            f"{len(link_candidates)} personal/lab link(s) match this scope. "
            "This is separate from the full professor audit and checks only the optional website button."
        )
        link_limit_enabled = st.checkbox(
            "Limit this link check",
            value=len(link_candidates) > 40,
            key="link-audit-limit-enabled",
        )
        link_limit = (
            st.slider(
                "Maximum links", 1, max(1, min(150, len(link_candidates) or 1)),
                min(20, len(link_candidates) or 1), key="link-audit-limit"
            )
            if link_limit_enabled and link_candidates
            else None
        )
        run_link_records = select_link_records(
            all_records,
            scope=link_scope,
            university=link_university,
            selected_ids=set(st.session_state.selected_professor_ids),
            limit=link_limit,
        )
        if st.button(
            f"Check {len(run_link_records)} website link(s)",
            disabled=not run_link_records,
            use_container_width=True,
        ):
            link_status = st.empty()
            link_progress = st.progress(0, text="Starting website checks...")
            total_links = len(run_link_records)

            def show_link_progress(message: str) -> None:
                match = re.search(r"website (\d+) of (\d+)", message, re.IGNORECASE)
                if match:
                    link_progress.progress(
                        int(match.group(1)) / max(int(match.group(2)), 1), text=message
                    )
                link_status.info(message)

            try:
                link_results = audit_website_links(
                    run_link_records, progress_callback=show_link_progress
                )
                update_website_link_results(link_results)
                st.session_state.website_audit_results = link_results
                link_progress.progress(1.0, text="Website checks finished")
                summary: dict[str, int] = {}
                for result in link_results:
                    summary[str(result["status"])] = summary.get(str(result["status"]), 0) + 1
                link_status.success(
                    "Link check complete — "
                    + ", ".join(f"{key}: {value}" for key, value in sorted(summary.items()))
                )
                st.session_state.results = []
            except Exception:
                _safe_public_error("Website link check failed")

        stored_links = website_link_counts()
        if stored_links:
            st.caption(
                "Saved link statuses — "
                + ", ".join(f"{key}: {value}" for key, value in sorted(stored_links.items()))
            )
        if st.session_state.website_audit_results:
            link_frame = pd.DataFrame(st.session_state.website_audit_results)
            st.dataframe(link_frame, hide_index=True, use_container_width=True)
            st.download_button(
                "Download latest website-link report",
                link_frame.to_csv(index=False).encode("utf-8"),
                "professor_website_link_audit.csv",
                "text/csv",
                use_container_width=True,
            )

    with st.expander("Targeted verification audit", expanded=False):
        scope = st.selectbox("Audit scope", AUDIT_SCOPES, key="audit-scope")
        audit_university = None
        if scope == "One university":
            if imported_universities:
                audit_university = st.selectbox(
                    "University",
                    sorted(imported_universities),
                    key="audit-university",
                )
            else:
                st.info(
                    "No universities are imported yet. Add data before using a one-university audit."
                )
        selected_ids = set(st.session_state.selected_professor_ids)
        candidates = select_audit_records(
            all_records,
            scope,
            university=audit_university,
            selected_ids=selected_ids,
        )
        st.caption(
            f"{len(candidates)} record(s) match this audit scope. "
            "New/changed, failed, review, selected, and one-university audits avoid another 20-minute full run."
        )
        use_limit = st.checkbox(
            "Limit this audit",
            value=scope == "All records" and len(candidates) > 50,
            key="audit-limit-enabled",
        )
        audit_limit = (
            st.slider("Maximum records", 1, max(1, min(100, len(candidates) or 1)), min(20, len(candidates) or 1))
            if use_limit and candidates
            else None
        )
        run_records = select_audit_records(
            all_records,
            scope,
            university=audit_university,
            selected_ids=selected_ids,
            limit=audit_limit,
        )
        if run_records:
            estimated_minutes = max(1, round(len(run_records) * 2.5 / 60))
            st.caption(f"Estimated live-check time: roughly {estimated_minutes} minute(s), depending on websites.")
        if st.button(
            f"Audit {len(run_records)} record(s)",
            disabled=not run_records,
            use_container_width=True,
        ):
            status = st.empty()
            progress = st.progress(0, text="Starting verification...")
            total = len(run_records)

            def show_audit_progress(message: str) -> None:
                match = re.search(r"Checking (\d+)/(\d+)", message)
                if match:
                    progress.progress(int(match.group(1)) / max(int(match.group(2)), 1), text=message)
                status.info(message)

            try:
                results = audit_records(run_records, progress_callback=show_audit_progress)
                update_verification_results(results)
                st.session_state.audit_results = results
                progress.progress(1.0, text="Verification finished")
                summary: dict[str, int] = {}
                for result in results:
                    summary[str(result["status"])] = summary.get(str(result["status"]), 0) + 1
                status.success(
                    "Audit complete — " + ", ".join(f"{key}: {value}" for key, value in sorted(summary.items()))
                )
                st.session_state.results = []
            except Exception:
                _safe_public_error("Verification audit failed")

        stored = verification_counts()
        if stored:
            st.caption("Saved statuses — " + ", ".join(f"{k}: {v}" for k, v in sorted(stored.items())))
        if st.session_state.audit_results:
            frame = pd.DataFrame(st.session_state.audit_results)
            st.download_button(
                "Download latest audit report",
                frame.to_csv(index=False).encode("utf-8"),
                "professor_verification_audit.csv",
                "text/csv",
                use_container_width=True,
            )


def _render_selected_sidebar(results: list[dict]) -> None:
    selected_ids = set(st.session_state.selected_professor_ids)
    if not selected_ids:
        return
    result_lookup = {int(record.get("id", 0)): record for record in results}
    selected_records = [result_lookup[item] for item in selected_ids if item in result_lookup]
    with st.sidebar:
        st.divider()
        st.subheader(f"Selected professors ({len(selected_records)})")
        for record in selected_records[:12]:
            professor_id = int(record["id"])
            left, right = st.columns([4, 1])
            left.caption(f"{record['name']} · {record['university']}")
            if right.button("×", key=f"remove-selected-{professor_id}", help="Remove selection"):
                st.session_state.selected_professor_ids.discard(professor_id)
                st.session_state[f"select-professor-{professor_id}"] = False
                st.rerun()
        if len(selected_records) > 12:
            st.caption(f"+ {len(selected_records) - 12} more selected")
        if st.button("Clear all selected", key="sidebar-clear-selected", use_container_width=True):
            _clear_search_selection()
            st.rerun()


# ---------- Configuration and startup ----------
app_mode = os.getenv("APP_MODE", "local").strip().casefold()
public_mode = app_mode == "public"
admin_tools_enabled = env_flag(
    "ENABLE_ADMIN_TOOLS",
    default=env_flag("ENABLE_ADMIN_REFRESH", default=not public_mode),
)
ai_search_enabled = env_flag("ENABLE_AI_SEARCH", default=True)
demo_data_enabled = env_flag("ENABLE_DEMO_DATA", default=not public_mode)
max_ai_searches_per_session = env_int("MAX_AI_SEARCHES_PER_SESSION", 25, 1)
max_ai_searches_per_day = env_int("MAX_AI_SEARCHES_PER_DAY", 500, 0)

st.set_page_config(page_title="Research Mentor Finder", page_icon="🎓", layout="wide")
initialize_database()
if demo_data_enabled:
    seed_demo_data()
_initialize_session_state()
st.session_state.app_render_revision = int(
    st.session_state.get("app_render_revision", 0)
) + 1
_inject_css()
_render_feedback_toast()

counts = source_counts()
demo_count = counts.get("Demo record", 0)
live_count = professor_count() - demo_count
imported_universities = [name for name in list_universities() if name]
supported = list(IMPLEMENTED_SCRAPERS)
ai_counts = ai_index_counts()
all_records_for_filters = fetch_professors(omit_embeddings=True)

# ---------- Hero ----------
st.markdown(
    """
    <section class="hero-card">
      <div class="hero-eyebrow">AI-powered academic discovery</div>
      <div class="hero-title">Find researchers whose work matches your interests.</div>
      <p class="hero-copy">Search public university profiles using normal language, compare research similarity, and export verified contact information for responsible outreach.</p>
    </section>
    """,
    unsafe_allow_html=True,
)
metric_cols = st.columns(3)
metric_cols[0].metric("Public researcher records", f"{live_count:,}")
metric_cols[1].metric("University sources", len(imported_universities))
metric_cols[2].metric("AI-indexed records", f"{ai_counts['indexed']:,}/{ai_counts['total']:,}")

if live_count == 0 and public_mode:
    st.error("The public database is not available yet. The owner needs to deploy the prepared database.")
elif live_count == 0:
    st.info("No live data is imported yet. Use the owner tools to refresh a university.")

# ---------- Sidebar ----------
with st.sidebar:
    st.header("About this search")
    st.caption(
        "Match scores measure research-topic similarity. They do not predict whether someone will reply, mentor a student, or offer an internship."
    )
    st.caption(
        "The app uses professional information intentionally published on academic websites. Verify details before contacting anyone."
    )
    st.divider()
    owner_authorized = _render_admin_access(admin_tools_enabled, public_mode=public_mode)
    if owner_authorized:
        st.subheader("Owner tools")
        _render_admin_tools(
            supported=supported,
            imported_universities=imported_universities,
            live_count=live_count,
            all_records=all_records_for_filters,
        )

personal_tools_enabled = not public_mode or owner_authorized
if personal_tools_enabled:
    _render_outreach_dashboard()

# ---------- Example searches ----------
st.markdown("#### Search by research interest")
examples = [
    "AI for climate change",
    "machine learning for healthcare",
    "robots that learn from humans",
    "NLP and misinformation",
]
example_cols = st.columns(len(examples))
for column, example in zip(example_cols, examples):
    column.button(
        example,
        key=f"example-{example}",
        use_container_width=True,
        on_click=_set_example_query,
        args=(example,),
    )

universities = ["All supported universities", *sorted(set(supported + imported_universities))]
states = ["All states", *list_states()]
department_groups = ["All department groups", *list_department_categories()]
disciplines = ["All disciplines", *list_disciplines()]
fields = ["All fields", *list_fields()]
topic_options = sorted(CATEGORY_KEYWORDS)
search_method_options = (
    ["Automatic (AI when available)", "Keyword only"] if ai_search_enabled else ["Keyword only"]
)

with st.form("professor-search-form", clear_on_submit=False):
    query_col, university_col = st.columns([2.35, 1])
    with query_col:
        query = st.text_input(
            "Research topic or interest",
            placeholder="Describe a topic, problem, or field — e.g. AI for detecting cancer",
            key="search-query",
        )
    with university_col:
        selected_university = st.selectbox(
            "University",
            universities,
            format_func=lambda value: "All universities" if value == "All supported universities" else value,
        )

    with st.expander("Advanced filters", expanded=False):
        filter_row_one = st.columns(3)
        state_filter = filter_row_one[0].selectbox("State", states)
        department_filter = filter_row_one[1].selectbox("Department group", department_groups)
        outreach_filter = filter_row_one[2].selectbox(
            "Research outreach signal",
            ["All public contacts", "Moderate or strong", "Strong only"],
        )
        topic_filters = st.multiselect(
            "Require at least one standardized topic",
            topic_options,
            help="Optional. If the main search box is empty, the selected topic labels will be used as the search query.",
        )
        filter_row_two = st.columns(4)
        verification_filter = filter_row_two[0].selectbox(
            "Verification",
            [
                "All verification statuses",
                "Verified only",
                "Verified or review",
                "Review only",
                "Failed only",
                "Not checked only",
            ],
        )
        sort_mode = filter_row_two[1].selectbox(
            "Sort",
            ["Best match", "Name (A–Z)", "University (A–Z)"],
        )
        results_per_page = filter_row_two[2].selectbox(
            "Results per page", PAGE_SIZE_OPTIONS, index=1
        )
        search_method = filter_row_two[3].selectbox("Search method", search_method_options)
        filter_row_three = st.columns(2)
        discipline_filter = filter_row_three[0].selectbox("Discipline", disciplines)
        field_filter = filter_row_three[1].selectbox("Field", fields)
        shortlisted_only = st.checkbox(
            "Search only my shortlist",
            value=False,
            disabled=not personal_tools_enabled,
            help="Persistent shortlist entries are stored in your local database.",
        )

    search_clicked = st.form_submit_button(
        "Search researchers", type="primary", use_container_width=True
    )

quick_search_requested = bool(st.session_state.pop("quick_search_requested", False))
search_requested = search_clicked or quick_search_requested
effective_query = resolve_search_query(query, topic_filters)

if search_requested:
    if not effective_query:
        st.warning("Enter a research topic or select at least one standardized topic before searching.")
    else:
        if not query.strip() and topic_filters:
            st.info(f"Searching using selected topic filter(s): {', '.join(topic_filters)}")
        search_started = time.perf_counter()
        try:
            with st.status("Understanding your research topic…", expanded=False) as status:
                candidates = fetch_professors(selected_university)
                if shortlisted_only:
                    saved_ids = favorite_professor_ids()
                    candidates = [
                        record for record in candidates
                        if int(record.get("id", 0)) in saved_ids
                    ]
                status.update(label=f"Applying filters to {len(candidates):,} public records…")
                candidates = filter_candidates(
                    candidates,
                    state_filter=state_filter,
                    department_filter=department_filter,
                    topic_filters=topic_filters,
                    outreach_filter=outreach_filter,
                    verification_filter=verification_filter,
                    discipline_filter=discipline_filter,
                    field_filter=field_filter,
                )

                query_vector = None
                embedding_source = "Not used"
                search_mode_used = "Keyword"
                fallback_message = ""
                if search_method.startswith("Automatic"):
                    has_stored_vectors = any(
                        str(record.get("embedding_json", "")).strip() for record in candidates
                    )
                    if not ai_search_enabled:
                        fallback_message = "AI search is disabled, so keyword ranking was used."
                    elif not has_stored_vectors:
                        fallback_message = "No stored professor embeddings were available, so keyword ranking was used."
                    else:
                        try:
                            query_vector, embedding_source = query_embedding_with_source(
                                effective_query, allow_api=False
                            )
                            search_mode_used = "AI semantic + keyword"
                        except RuntimeError:
                            if st.session_state.ai_search_count >= max_ai_searches_per_session:
                                fallback_message = "This browser session reached its AI-search limit, so keyword ranking was used."
                            elif not openai_available():
                                fallback_message = "OpenAI is not configured, so keyword ranking was used."
                            else:
                                quota = consume_daily_usage(
                                    "public_query_embedding", max_ai_searches_per_day
                                )
                                if not bool(quota["allowed"]):
                                    fallback_message = "The app reached its daily AI-search budget, so keyword ranking was used."
                                else:
                                    try:
                                        query_vector, embedding_source = query_embedding_with_source(
                                            effective_query, allow_api=True
                                        )
                                        st.session_state.ai_search_count += 1
                                        search_mode_used = "AI semantic + keyword"
                                    except Exception:
                                        LOGGER.exception("OpenAI query embedding failed")
                                        fallback_message = "Semantic search was temporarily unavailable, so keyword ranking was used."

                status.update(label=f"Ranking {len(candidates):,} matching researchers…")
                ranked_results = rank_professors(
                    candidates,
                    effective_query,
                    limit=None,
                    query_embedding=query_vector,
                )
                elapsed = time.perf_counter() - search_started
                status.update(
                    label=f"Results ready in {elapsed:.2f} seconds",
                    state="complete",
                    expanded=False,
                )

            _clear_search_selection()
            st.session_state.current_page = 1
            st.session_state.page_picker = 1
            st.session_state.results = ranked_results
            st.session_state.search_metadata = {
                "mode": search_mode_used,
                "embedding_source": embedding_source,
                "fallback_message": fallback_message,
                "query": effective_query,
                "elapsed_seconds": round(elapsed, 3),
                "university": selected_university,
                "state_filter": state_filter,
                "department_filter": department_filter,
                "discipline_filter": discipline_filter,
                "field_filter": field_filter,
                "topic_filters": topic_filters,
                "outreach_filter": outreach_filter,
                "verification_filter": verification_filter,
                "shortlisted_only": shortlisted_only,
                "sort_mode": sort_mode,
                "results_per_page": int(results_per_page),
            }
        except Exception:
            _safe_public_error("Search failed")

results = list(st.session_state.results)
metadata = st.session_state.get("search_metadata", {})

if results:
    if metadata.get("shortlisted_only"):
        saved_fav_ids = favorite_professor_ids()
        results = [
            record for record in results
            if int(record.get("id", 0)) in saved_fav_ids
        ]
    active_sort = str(metadata.get("sort_mode", sort_mode))
    active_page_size = int(metadata.get("results_per_page", results_per_page))
    sorted_results = sort_results(results, active_sort)
    total_results = len(sorted_results)
    st.session_state.current_page = clamp_page(
        st.session_state.current_page, total_results, active_page_size
    )
    current_page_records = paginate(
        sorted_results, st.session_state.current_page, active_page_size
    )
    first_result, last_result = page_bounds(
        total_results, st.session_state.current_page, active_page_size
    )

    st.markdown(f"## {total_results:,} matching researchers")
    summary_cols = st.columns(4)
    summary_cols[0].metric("Showing", f"{first_result}–{last_result}")
    summary_cols[1].metric("Search method", str(metadata.get("mode", "Keyword")))
    summary_cols[2].metric("Search time", f"{float(metadata.get('elapsed_seconds', 0)):.2f}s")
    summary_cols[3].metric("Selected", len(st.session_state.selected_professor_ids))
    if metadata.get("embedding_source") == "persistent cache":
        st.caption("This semantic query was served from the app's persistent cache and used no new API request.")
    if metadata.get("fallback_message"):
        st.info(str(metadata["fallback_message"]))
    st.caption(
        "Match scores describe research-topic similarity only. Outreach labels summarize public evidence and do not predict acceptance or response."
    )

    _render_page_controls(
        total_items=total_results, page_size=active_page_size, location="top"
    )

    selected_ids = set(st.session_state.selected_professor_ids)
    outreach_by_id = get_professor_outreach(
        [int(record.get("id", 0)) for record in current_page_records]
    )
    selection_cols = st.columns([1, 1, 2])
    if selection_cols[0].button("Select current page", use_container_width=True):
        for professor in current_page_records:
            professor_id = int(professor.get("id", 0))
            if professor_id:
                selected_ids.add(professor_id)
                st.session_state[f"select-professor-{professor_id}"] = True
        st.session_state.selected_professor_ids = selected_ids
        st.rerun()
    if selection_cols[1].button("Clear selections", use_container_width=True):
        _clear_search_selection()
        st.rerun()
    selection_cols[2].caption("Selections last for this session; the shortlist persists after the app closes.")

    for page_index, professor in enumerate(current_page_records, start=first_result):
        professor_id = int(professor.get("id", 0))
        opportunity_level = str(professor.get("opportunity_level", "Basic"))
        verification_status = str(professor.get("verification_status", "Not checked"))
        topics = topic_values(professor)
        profile_url = str(professor.get("profile_url", NOT_AVAILABLE))
        website_url = str(professor.get("website_url", NOT_AVAILABLE))
        website_status = str(professor.get("website_status", "Not checked"))
        opportunity_url = str(professor.get("opportunity_source_url", NOT_AVAILABLE))
        email = str(professor.get("email", NOT_AVAILABLE))
        outreach = outreach_by_id.get(professor_id, {})
        personal_status = str(outreach.get("outreach_status", "Not contacted"))

        with st.container(border=True):
            header_left, header_right = st.columns([6, 1])
            with header_left:
                st.markdown(
                    f"<div class='result-title'>{page_index}. {html.escape(str(professor['name']))}</div>",
                    unsafe_allow_html=True,
                )
                st.markdown(
                    f"**{html.escape(str(professor['university']))}** · "
                    f"{html.escape(str(professor.get('department', NOT_AVAILABLE)))} · "
                    f"{html.escape(str(professor.get('title', NOT_AVAILABLE)))}"
                )
            with header_right:
                st.markdown(
                    f"<div class='match-badge'>{float(professor['match_score']):.0f}%</div>",
                    unsafe_allow_html=True,
                )

            if topics:
                st.markdown(topic_chips_html(topics), unsafe_allow_html=True)
            summary = str(professor.get("ai_summary", "")).strip()
            st.write(summary or str(professor.get("research_interests", NOT_AVAILABLE)))
            st.caption(str(professor.get("match_reason", "")))
            website_pill = ""
            if website_url != NOT_AVAILABLE:
                website_pill = (
                    f"<span class='status-pill pill-{_status_class(website_status)}'>"
                    f"Website: {html.escape(website_status)}</span>"
                )
            st.markdown(
                f"<span class='status-pill pill-{_status_class(opportunity_level)}'>Outreach: {html.escape(opportunity_level)}</span>"
                f"<span class='status-pill pill-{_status_class(verification_status)}'>Verification: {html.escape(verification_status)}</span>"
                f"{website_pill}"
                + (
                    f"<span class='status-pill pill-{_status_class(personal_status)}'>Status: {html.escape(personal_status)}</span>"
                    if personal_tools_enabled and personal_status != "Not contacted"
                    else ""
                ),
                unsafe_allow_html=True,
            )

            action_cols = st.columns(2 if personal_tools_enabled else 1)
            checkbox_key = f"select-professor-{professor_id}"
            if checkbox_key not in st.session_state:
                st.session_state[checkbox_key] = professor_id in selected_ids
            include = action_cols[0].checkbox("Add to current selection", key=checkbox_key)
            if include:
                selected_ids.add(professor_id)
            else:
                selected_ids.discard(professor_id)
            if personal_tools_enabled:
                with action_cols[1]:
                    is_fav = bool(int(outreach.get("is_favorite", 0) or 0))
                    _render_favorite_button(
                        professor_id,
                        is_favorite=is_fav,
                        professor_name=str(professor.get("name", "professor")),
                        key_prefix="search",
                    )

            link_items: list[tuple[str, str]] = []
            if profile_url != NOT_AVAILABLE:
                link_items.append(("Faculty profile", profile_url))
            if (
                website_url != NOT_AVAILABLE
                and website_url != profile_url
                and website_is_publicly_usable(professor, owner_mode=owner_authorized)
            ):
                label = "Website or lab"
                if owner_authorized and website_status not in {"Verified", "Not checked"}:
                    label = f"Website or lab ({website_status})"
                verified_final = str(professor.get("website_final_url", NOT_AVAILABLE)).strip()
                target_url = (
                    verified_final
                    if website_status == "Verified" and verified_final not in {"", NOT_AVAILABLE}
                    else website_url
                )
                link_items.append((label, target_url))
            if (
                opportunity_url != NOT_AVAILABLE
                and opportunity_url not in {profile_url, website_url}
            ):
                link_items.append(("Outreach evidence", opportunity_url))
            contact_cols = st.columns([1.5, *([1] * len(link_items))])
            contact_cols[0].markdown(f"**Email:** `{html.escape(email)}`")
            for column, (label, url) in zip(contact_cols[1:], link_items):
                column.link_button(label, url, use_container_width=True)

            if personal_tools_enabled:
                with st.expander("My private notes & outreach", expanded=False):
                    _render_outreach_editor(
                        professor,
                        outreach,
                        key_prefix="search",
                        allow_favorite_edit=False,
                    )

            with st.expander("View full research and verification details", expanded=False):
                st.write(f"**Research interests:** {professor.get('research_interests', NOT_AVAILABLE)}")
                st.write(f"**AI-standardized topics:** {professor.get('ai_categories') or NOT_AVAILABLE}")
                if summary:
                    st.write(f"**AI research summary:** {summary}")
                st.write(f"**Why matched:** {professor.get('match_reason', NOT_AVAILABLE)}")
                st.write(
                    f"**Outreach evidence:** {professor.get('opportunity_signals', 'No explicit opportunity information found')}"
                )
                if verification_status in {"Review", "Failed", "Not checked"}:
                    st.write(
                        f"**Verification notes:** {professor.get('verification_issues', NOT_AVAILABLE)}"
                    )
                if website_url != NOT_AVAILABLE:
                    st.write(f"**Website/lab status:** {website_status}")
                    if website_status != "Verified":
                        st.write(
                            f"**Website/lab notes:** {professor.get('website_issue', NOT_AVAILABLE)}"
                        )
                st.write(
                    f"**Location:** {professor.get('city', NOT_AVAILABLE)}, {professor.get('state', NOT_AVAILABLE)}"
                )
                st.write(
                    f"**Last checked:** {professor.get('last_checked_at', NOT_AVAILABLE)}"
                )
                st.code(email, language=None, wrap_lines=True)

    st.session_state.selected_professor_ids = selected_ids
    _render_page_controls(
        total_items=total_results, page_size=active_page_size, location="bottom"
    )

    selected_records = [
        record
        for record in sorted_results
        if int(record.get("id", 0)) in selected_ids
    ]
    if selected_records:
        with st.expander(f"Review {len(selected_records)} selected professor(s)", expanded=False):
            for record in selected_records:
                professor_id = int(record["id"])
                left, right = st.columns([5, 1])
                left.write(f"**{record['name']}** — {record['university']}")
                if right.button("Remove", key=f"remove-main-{professor_id}", use_container_width=True):
                    st.session_state.selected_professor_ids.discard(professor_id)
                    st.session_state[f"select-professor-{professor_id}"] = False
                    st.rerun()

    st.markdown("### Export results")
    st.caption(
        f"Selected: {len(selected_records)} · Current page: {len(current_page_records)} · All matches: {total_results}"
    )
    export_scope = st.radio(
        "Export scope",
        ["Selected professors", "Current page", "All matching results"],
        horizontal=True,
        label_visibility="collapsed",
    )
    export_records = (
        selected_records
        if export_scope == "Selected professors"
        else current_page_records
        if export_scope == "Current page"
        else sorted_results
    )
    frame = _export_dataframe(_records_with_outreach(export_records))
    st.download_button(
        "Download CSV",
        frame.to_csv(index=False).encode("utf-8"),
        "professor_search_results.csv",
        "text/csv",
        use_container_width=True,
        disabled=not export_records,
    )
    _render_selected_sidebar(sorted_results)

elif search_requested and query.strip() and metadata.get("shortlisted_only"):
    st.info(
        "Your shortlist has no professors matching the current query. Save professors to your "
        "shortlist from the search results or the dashboard, then search again."
    )
elif search_requested and query.strip():
    st.warning(
        "No sufficiently relevant researchers matched the current filters. Try a broader topic or fewer filters."
    )
else:
    st.markdown(
        """
        <div class="notice-card">
        <b>How it works</b><br>
        The app compares the meaning of your query with cached professor research profiles, then combines semantic and exact-topic matching. Public searches do not scrape university sites and normally finish in a few seconds.
        </div>
        """,
        unsafe_allow_html=True,
    )

st.divider()
st.caption(
    "Professional information is collected from public academic pages. Semantic search sends only the research query to OpenAI when a cached query vector is unavailable. Verify all information before outreach."
)
