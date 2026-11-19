# Research Mentor Finder — Frontend

Next.js 16 + React 19 + TypeScript + Tailwind frontend for the student-facing experience.

For a complete clean-install guide covering both the backend and frontend, see
the [main README](../README.md). Use `npm ci` from this directory to install the
committed lockfile. The frontend currently uses Next.js 16.4.6, React 19.3.0,
and Lucide 1.52.0, with Node.js 20.9+ required. Run ESLint separately using
`npm run lint`; Next.js does not run it as part of `npm run build`.

The frontend relies on the FastAPI backend for researcher discovery,
profile data, and account-related features.

Discover (manual search), professor profiles, the student profile/onboarding wizard,
personalized **For You recommendations**, **Saved researchers**, the **Outreach dashboard**,
and the **outreach email composer** are **live**, served by the Python FastAPI backend.
The composer can create and update real **Gmail drafts** (never send), and the outreach
dashboard can **check Gmail thread status** (sent/replied detection) and generate grounded
**follow-up drafts** — all manual, all read-only with respect to message content, and nothing
is ever sent automatically. Accounts use backend Google Sign-In (or a local developer
account), and every personal screen is per-account and session-protected.

## Running both servers

1. Start the backend (from the repo root):

   ```bash
   .venv\Scripts\python.exe -m uvicorn api.main:app --port 8000
   ```

2. Start the frontend:

   ```bash
   npm run dev   # http://localhost:3000
   ```

   The frontend calls `http://localhost:8000` by default. To point at another backend,
   copy `.env.example` to `.env.local` and set `NEXT_PUBLIC_API_BASE_URL`.

## Accounts and sign-in

- The layout mounts an `AuthProvider` that calls `GET /api/auth/me`; when a session exists
  it also receives the CSRF token and forwards it on every non-GET request as
  `X-CSRF-Token` (`lib/api/client.ts` sets `credentials: "include"`).
- The nav shows **Sign in with Google** (backend redirect) or, in `local` server mode, the
  **Local developer account** one-click sign-in only when `APP_MODE=local` and
  `AUTH_ALLOW_DEV_LOGIN=true`. Signed-in users see their name and a
  **Sign out** action.
- Saved, For You, Outreach, the composer, Gmail connection, and Account/Onboarding pages
  are wrapped in `RequireAuth`; signed-out visitors get a sign-in card instead.

## How For You works

- Sign in, then the onboarding wizard saves your profile to your account
  (`PUT /api/profile`; step progress stays in `rmf:onboarding:step`). At least one research
  interest is required; every other step is skippable and editable later. The résumé file
  name stays in browser storage (`rmf:profile:resume`) — the file itself is never uploaded.
- `/for-you` reads your account profile and sends it to `POST /api/recommendations` each
  time you change interests or filters. The backend reuses the live search/embedding
  infrastructure to rank real professors, returns a transparent `research_fit_score` with
  the label **Strong research match** / **Good research match** / **Potential match**, plus
  a deterministic, data-grounded **Why you match** explanation (primary interest fit plus
  secondary skills / projects / coursework / location signals).
- Professor profile pages call `POST /api/recommendations/explain` with your profile for a
  personalized **Why you match** panel; without a saved profile they fall back to an
  informational research-connection note.

## How Saved and Outreach work

- `SavedProvider` (mounted in the root layout) hydrates `GET /api/saved` after sign-in and
  is the single source of truth for saved state. Profile **Save/Remove** buttons call
  `POST /api/saved/{id}` / `DELETE /api/saved/{id}`; signed-out visitors are directed to
  sign in instead. The homepage fixture showcase hides the save button by design.
- `/saved` shows your saved researchers from the live API with an outreach-status summary
  and Move draft / Continue draft actions.
- `/outreach` lists every professor you have engaged with, sorted by needs-attention
  (follow-ups first), with a local workflow: Continue draft, Snooze, Log reply,
  Schedule meeting, Mark closed, Reopen — each an optimistic `PATCH /api/outreach/{id}` —
  plus **Check Gmail status** (per row and "all") and **Draft follow-up** (Phase 7).
  Sync is manual only; the card shows the resulting sent/replied/last-checked times.
- `/outreach/compose/[id]` fetches the live professor and any saved draft. Save draft
  persists `email_to`/`email_subject`/`email_body`/`notes` and marks the row `Drafted`
  (if no other status is set). Once Gmail is connected, **Create Gmail draft** posts the
  current message to Gmail (drafts only), **Update Gmail draft** replaces it, and
  **Open in Gmail** lands on the drafts list. Unsaved edits show a "not synced" notice.
- **Check Gmail status** calls `POST /api/outreach/{id}/gmail-sync` (or
  `POST /api/outreach/gmail-sync` for all linked rows). The backend reads **thread
  metadata only** for the stored thread and updates sent/reply state and the row status
  (never overwriting `Meeting scheduled`/`Rejected`). **Draft follow-up** calls
  `POST /api/outreach/{id}/follow-up-draft`, which writes a grounded follow-up into the
  saved draft fields locally — it never opens Gmail and never sends.
- All saved/outreach/note data lives in `professors.db`, scoped to the signed-in account.
  `/account` offers the one-time **Import my local data** action that migrates pre-sign-in
  `local-owner` rows and the Gmail connection into that account.

## Routes

| Route | Screen | Backing |
| --- | --- | --- |
| `/` | Homepage | fixture |
| `/discover` | Discover / manual search | **live FastAPI** (public) |
| `/researchers/[id]` | Professor profile | **live FastAPI** + personalized (public) |
| `/account` | Account + import local data | **live FastAPI** (sign-in) |
| `/account/onboarding` | 5-step onboarding wizard | **live FastAPI** (sign-in) |
| `/for-you` | For You recommendations | **live FastAPI** (sign-in) |
| `/saved` | Saved researchers | **live FastAPI** (sign-in) |
| `/outreach` | Outreach dashboard | **live FastAPI** (sign-in) |
| `/outreach/compose/[id]` | Outreach email composer | **live FastAPI** (sign-in) |

## Commands

```bash
npm ci
npm run dev            # http://localhost:3000
npm run lint           # ESLint
npm run typecheck      # tsc --noEmit
npm run build          # next build
npm run smoke          # requires build first; starts server on :3210 and asserts routes
npm run integration:smoke   # advanced integration check; requires an isolated test database and explicit local dev-login configuration
```

## Notes

- Accounts are backend Google Sign-In (`AUTH_CLIENT_ID`/`AUTH_CLIENT_SECRET` in `.env`) with
  HttpOnly session cookies and CSRF protection; the local developer account signs in
  without Google keys only if expressly enabled with `APP_MODE=local` and
  `AUTH_ALLOW_DEV_LOGIN=true`. The student profile lives per-account on the backend;
  only the résumé file name stays in the browser.
- The app never writes to professor rows; recommendations, explanations, saving, and
  outreach updates write only to user-scoped rows.
- Gmail is **drafts + metadata only**: the backend requests a Google OAuth client id/secret
  from `.env` (`GMAIL_CLIENT_ID`, `GMAIL_CLIENT_SECRET`) with the `gmail.compose` and
  `gmail.metadata` scopes; it never calls a send endpoint and never reads message bodies.
  Per-account tokens live under `data/gmail_tokens/`, encrypted only if
  `GMAIL_TOKEN_ENCRYPTION_KEY` (Fernet + `cryptography`) is set.
- ⚠️ If FastAPI is shut down while you browse: live pages show a clear error card with the
  exact command to restart the backend (SSR still renders the page headers).
