# Historical source snapshots and one-time maintenance tools

This directory contains historical scripts from the previous Streamlit application.
They are **not** part of the current Next.js/FastAPI setup or deployment and
should not be run against live or production data.

- `app.before-shortlist-fragment-fix-20260831-211333.py` — preserved pre-fix Streamlit source snapshot.
- `apply_shortlist_fragment_fix.py` — one-time patcher for the earlier root-level `app.py`. It can modify files; do not run unless intentionally restoring that historical build.
- `repair_audit_v94.py` — historical V9.4 database-repair entrypoint. It can modify the database; do not run against the live application.

The current backend entrypoint is `api.main:app`, and the current frontend
is in `frontend/`. See the [main README](../README.md) for current instructions.
