# Legacy Streamlit application and maintenance tools

This folder preserves the previous Streamlit implementation for historical
reference. The current project uses FastAPI (`api.main:app`) and Next.js
(`frontend/`); follow the [main README](../README.md) to run it.

The archived files are not used for normal operation of the current app:

- `app.py` — previous Streamlit application, not the current FastAPI entrypoint.
- `setup_windows.bat` and `run_windows.bat` — legacy Windows launchers.
  They start from the repository root and target `legacy/app.py`. They have
  not been runtime-tested after relocation.
- `app.before-shortlist-fragment-fix-20260831-211333.py` — earlier source snapshot.
- `apply_shortlist_fragment_fix.py` — one-time historical patcher that
  targets the archived Streamlit source. It can modify files.
- `repair_audit_v94.py` — historical database repair entrypoint. It can
  modify the database.

Do not run these against a production database, active service, or personal
data. They may require private project files that are not distributed.
