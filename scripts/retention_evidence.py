"""Preserve scoped evidence, excluding private runtime storage and secrets."""
import difflib
import hashlib
import json
import re
from pathlib import Path
from scripts.release_readiness_evidence import fingerprints, ORIGINAL

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "evidence/retention-2026-10-06"
CHECKPOINT = ROOT / "test-runtime/retention-checkpoint-20261006"
FILES = ["api/retention.py", "api/main.py", "api/auth/account_deletion.py",
         "scripts/restore_private_backup.py", "scripts/managed_retention.py",
         "scripts/run_managed_api.py", "scripts/retention_evidence.py",
         "frontend/scripts/run_managed_frontend.mjs", "frontend/scripts/retention_acceptance.mjs",
         "frontend/scripts/retention_passive.mjs", "frontend/app/privacy/page.tsx",
         "tests/test_retention.py", "tests/conftest.py", "requirements.txt",
         "Start-LocalPrototype.ps1", "Restart-HardenedApi.ps1", "Start-UpgradedFrontend.ps1",
         "Stop-ManagedPrototype.ps1", "Restore-ManagedBackup.ps1", "RETENTION_STATUS.md", "ACCOUNT_LIFECYCLE_STATUS.md"]


def gmail_hashes():
    folder = ROOT / "test-runtime/gmail-isolated"
    return {hashlib.sha256(str(p.relative_to(folder)).encode()).hexdigest(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in folder.rglob("*") if p.is_file()}


def finish():
    before = json.loads((EVIDENCE / "before.json").read_text(encoding="utf-8"))
    after = fingerprints()
    changed = [table for table in set(before["working_tables"]) | set(after["working_tables"])
               if before["working_tables"].get(table) != after["working_tables"].get(table)]
    assert not set(changed) - {"app_migrations"}, "Unexpected working table changes"
    assert all(before[k] == after[k] for k in ("original_sha256", "original_mtime_ns")), "Original DB changed"
    assert gmail_hashes() == json.loads((EVIDENCE / "gmail-before.json").read_text(encoding="utf-8")), "Gmail storage changed"
    backups = {p.name: {"size": p.stat().st_size, "mtime_ns": p.stat().st_mtime_ns} for p in (ORIGINAL / "data/backups").glob("*.db")}
    assert backups == json.loads((EVIDENCE / "original-backups-before.json").read_text(encoding="utf-8")), "Original backup metadata changed"
    (EVIDENCE / "preservation.json").write_text(json.dumps({"passed": True, "changed_tables": changed,
        "original_backups_metadata_unchanged": True, "gmail_hashes_unchanged": True,
        "exception": "Initialization refreshes app_migrations marker timestamps; no per-row metadata snapshot is claimed.",
        **after}, indent=2), encoding="utf-8")
    patches = []
    for name in FILES:
        old = (CHECKPOINT / name).read_text(encoding="utf-8").splitlines(True) if (CHECKPOINT / name).exists() else []
        new = (ROOT / name).read_text(encoding="utf-8").splitlines(True)
        patches.extend(difflib.unified_diff(old, new, fromfile="checkpoint/"+name, tofile="working/"+name))
        destination = EVIDENCE / "source" / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text("".join(new), encoding="utf-8")
    (EVIDENCE / "scoped-changes.diff").write_text("".join(patches), encoding="utf-8")
    (EVIDENCE / "baseline-notes.json").write_text((CHECKPOINT / "reconstructed-baselines.json").read_text(encoding="utf-8"), encoding="utf-8")
    texts = [p for p in EVIDENCE.rglob("*") if p.is_file() and p.suffix in {".txt", ".json", ".md", ".diff", ".py", ".ps1", ".mjs", ".tsx"}]
    count = 0
    for p in texts:
        text = p.read_text(encoding="utf-8")
        redacted = text.replace("C:\\\\Users\\\\nirmi", "C:\\\\Users\\\\<user>").replace("C:\\Users\\nirmi", "C:\\Users\\<user>").replace("C:/Users/nirmi", "C:/Users/<user>")
        if redacted != text:
            count += 1
            p.write_text(redacted, encoding="utf-8")
        assert not re.search(r"(?:sk-(?:proj-)?[A-Za-z0-9_-]{20,}|GOCSPX-[A-Za-z0-9_-]{15,}|ya29\.[A-Za-z0-9_-]{15,}|-----BEGIN (?:RSA |EC |OPENSSH |ENCRYPTED )?PRIVATE KEY-----)", redacted), "Sensitive content found; do not share"
    (EVIDENCE / "redaction.json").write_text(json.dumps({"text_files_scanned":len(texts), "files_with_os_path_redacted":count,
       "excluded": [".env", "runtime databases", "Gmail token files", "managed ledger", "encryption keys", "encrypted private backups"],
       "synthetic_test_accounts_retained":True}, indent=2), encoding="utf-8")
    print("Preservation checks passed; scoped evidence retained without private runtime files.")


if __name__ == "__main__":
    finish()
