"""Preserve frontend-only diffs and redacted evidence without visiting dependencies."""
import difflib
import hashlib
import json
import os
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "evidence/frontend-upgrade-2026-10-05"
OLD = ROOT / "test-runtime/frontend-before-next16-20261005"
NEW = ROOT / "frontend"

names = set()
for base in (OLD, NEW):
    for directory, directories, files in os.walk(base, followlinks=False):
        directories[:] = [d for d in directories if d not in {"node_modules", ".next"}]
        for name in files:
            if not name.startswith(".env") and not name.endswith(".tsbuildinfo"):
                names.add((Path(directory) / name).relative_to(base).as_posix())
changes, patches = [], []
for name in sorted(names):
    old = (OLD / name).read_text(encoding="utf-8") if (OLD / name).exists() else ""
    new = (NEW / name).read_text(encoding="utf-8") if (NEW / name).exists() else ""
    if old != new:
        changes.append(name)
        patches.extend(difflib.unified_diff(old.splitlines(True), new.splitlines(True),
                       fromfile="previous/" + name, tofile="upgraded/" + name))
(EVIDENCE / "frontend-changes.patch").write_text("".join(patches), encoding="utf-8")
(EVIDENCE / "changed-files.json").write_text(json.dumps(changes, indent=2), encoding="utf-8")
(EVIDENCE / "FRONTEND_UPGRADE_STATUS.md").write_bytes((ROOT / "FRONTEND_UPGRADE_STATUS.md").read_bytes())
for name in ("package.json", "package-lock.json"):
    (EVIDENCE / ("upgraded-" + name)).write_bytes((NEW / name).read_bytes())
patterns = [r"GOCSPX-[A-Za-z0-9_-]{20,}", r"sk-(?:proj-)?[A-Za-z0-9_-]{16,}", r"ya29\.[A-Za-z0-9_-]+"]
files = [p for p in EVIDENCE.rglob("*") if p.is_file() and p.name != "artifact-manifest.json"]
for file in files:
    if file.suffix in {".json", ".txt", ".md", ".log", ".patch"}:
        text = file.read_text(encoding="utf-8-sig").replace("nirmi", "<user>")
        if any(re.search(pattern, text) for pattern in patterns):
            raise RuntimeError("Credential pattern found in " + file.name)
        file.write_text(text, encoding="utf-8")
        if file.suffix == ".json":
            json.loads(text)
assert not any(p.suffix in {".db", ".sqlite"} or p.name.startswith(".env") for p in files)
results = json.loads((EVIDENCE / "browser/browser-results.json").read_text(encoding="utf-8"))
assert len(results["automatedAssertions"]) == 23 and all(r["passed"] for r in results["automatedAssertions"])
assert json.loads((EVIDENCE / "audit-runtime.json").read_text(encoding="utf-8"))["metadata"]["vulnerabilities"]["total"] == 0
manifest = [{"path": p.relative_to(EVIDENCE).as_posix(), "sha256": hashlib.sha256(p.read_bytes()).hexdigest()} for p in files]
(EVIDENCE / "artifact-manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
print(json.dumps({"changed_frontend_files": len(changes), "shared_artifacts": len(files) + 1,
                  "browser_passed": 23, "runtime_advisories": 0, "secret_pattern_scan": "passed"}))
