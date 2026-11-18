"""Heuristic source scan; tracked databases and credential files are forbidden."""
from pathlib import Path
import os
import re
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
SKIP_PARTS = {"venv", ".venv", ".git", "__pycache__", ".pytest_cache", "node_modules", ".next", "test-runtime", "data", "logs"}
PATTERNS = {
    "OpenAI-style secret": re.compile(r"\bsk-(?:proj-)?[A-Za-z0-9_-]{16,}\b"),
    "Private key": re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    "Google client secret": re.compile(r"GOCSPX-[A-Za-z0-9_-]{20,}"),
}


def private_file(path):
    name = path.name.lower()
    return (name.endswith((".db", ".db-shm", ".db-wal", ".db-journal", ".sqlite", ".sqlite3"))
            or (name.startswith(".env") and not name.endswith("example"))
            or name == "secrets.toml" or "gmail_tokens" in path.parts)


findings = []
if (ROOT / ".git").exists():
    git = shutil.which("git")
    if not git:
        sys.exit("Git is required to verify tracked files in this checkout.")
    result = subprocess.run([git, "-C", str(ROOT), "ls-files", "-z"], capture_output=True, check=True)
    paths = [ROOT / name for name in result.stdout.decode("utf-8").split("\0") if name]
    scope = "tracked-file heuristic scan"
    for path in paths:
        if private_file(path):
            findings.append(f"Private runtime file is tracked: {path.relative_to(ROOT)}")
else:
    paths = []
    for directory, directories, filenames in os.walk(ROOT):
        directories[:] = [name for name in directories if name not in SKIP_PARTS]
        paths.extend(Path(directory) / name for name in filenames)
    scope = "local source heuristic scan (no Git history available; runtime data excluded)"

for path in paths:
    if not path.is_file() or private_file(path) or path.stat().st_size > 2_000_000:
        continue
    try:
        content = path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        continue
    for label, pattern in PATTERNS.items():
        if pattern.search(content):
            findings.append(f"{label}: {path.relative_to(ROOT)}")
if findings:
    print("Potential publication problems:")
    for finding in findings:
        print(f"- {finding}")
    sys.exit(1)
print(f"Passed {scope}. This is not a full credential or personal-data audit.")
