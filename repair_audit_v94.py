from __future__ import annotations

from services.audit_repair import preview_v94_repair, run_v94_repair


if __name__ == "__main__":
    preview = preview_v94_repair()
    if preview.get("already_applied"):
        print("V9.4 audit preparation was already applied. No changes were made.")
    else:
        print("Creating a database backup and safely preparing audited records...")
        result = run_v94_repair()
        for key, value in result.items():
            print(f"{key}: {value}")
        print(
            "No UCI or Cal Poly rows were deleted. Test each rebuilt connector, then run "
            "a full authoritative refresh to replace and prune stale rows safely."
        )
