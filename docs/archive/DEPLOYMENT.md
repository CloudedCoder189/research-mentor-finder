# Historical Streamlit deployment checklist (V8)

**Not the deployment guide for the current application.** These notes describe an
earlier Streamlit build, not the live Next.js/FastAPI application. To run the
current application locally, use the [main README](../../README.md). The separate
pilot deployment code is in [deploy/pilot](../../deploy/pilot), with production
configuration checks in [api/production_config.py](../../api/production_config.py).
The steps below are preserved as historical context, not a complete or
validated production deployment recipe.

## Before publishing

1. Confirm the local database contains only public professional information.
2. Confirm all changed records are AI-indexed.
3. Run targeted audits for `Not checked` and `Failed` records.
4. Revoke any API key that was ever shared in a ZIP, screenshot, or chat.
5. Keep `.env`, `venv`, caches, SQLite sidecar files, and logs out of GitHub.
6. Run `python scripts/security_check.py` before committing.

## Public secrets

```toml
OPENAI_API_KEY = "your deployment key"
OPENAI_TEXT_MODEL = "gpt-5-mini"
OPENAI_EMBEDDING_MODEL = "text-embedding-3-small"
APP_MODE = "public"
ENABLE_DEMO_DATA = false
ENABLE_AI_SEARCH = true
ENABLE_ADMIN_TOOLS = false
MAX_AI_SEARCHES_PER_SESSION = 25
MAX_AI_SEARCHES_PER_DAY = 500
```

Public visitors search the prepared SQLite database. They cannot trigger scraping,
AI indexing, or verification audits.

## Database deployment

All runtime SQLite databases and sidecar files are ignored. The current database
also holds private profiles, sessions, and outreach. Do not publish it. Export a
separate dataset containing only allowlisted public researcher fields.

The current Next.js/FastAPI implementation has different deployment
configuration and AI usage controls. Use the main README for local setup;
do not treat the legacy budget settings below as production safeguards.

## Cost controls

- Repeated semantic queries are cached persistently in SQLite.
- Each browser session has a limit.
- The whole deployment has a daily query-embedding budget.
- After either limit is reached, the app automatically uses keyword ranking.

The daily budget is global, not per IP or per account. A larger launch should use
an external rate limiter or authenticated accounts.
