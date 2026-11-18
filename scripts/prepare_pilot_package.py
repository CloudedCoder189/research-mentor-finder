"""Stage only allowlisted source and a new public seed. Never upload a workspace."""
import argparse
import hashlib
import json
import re
import shutil
from pathlib import Path

from scripts.export_public_seed import export

ROOT = Path(__file__).resolve().parents[1]
SECRET = re.compile(r"(?:sk-(?:proj-)?[A-Za-z0-9_-]{20,}|GOCSPX-[A-Za-z0-9_-]{15,}|ya29\.[A-Za-z0-9_-]{15,}|-----BEGIN (?:RSA |EC |OPENSSH |ENCRYPTED )?PRIVATE KEY-----)")
FRONT_FILES = {"package.json", "package-lock.json", "next.config.mjs", "next-env.d.ts",
               "tsconfig.json", "tailwind.config.ts", "postcss.config.mjs", "eslint.config.mjs"}
FRONT_DIRS = {"app", "components", "data", "hooks", "lib", "public", "styles", "types"}
PILOT_FILES = {"Dockerfile", "Caddyfile", "Caddyfile.public", "provision.py", "start.py", "monitor.py", "railway.json", "pilot.env.example", "reviewed-professors.json", "repair_links.py", "link-repairs-20261025.json"}


def selected_files(root):
    result = [root / "database.py", root / "runtime_config.py", root / "requirements.txt"]
    for folder in ("api", "services", "scrapers"):
        result.extend(p for p in (root / folder).rglob("*.py") if "__pycache__" not in p.parts)
    result.extend(root / "frontend" / name for name in FRONT_FILES if (root / "frontend" / name).is_file())
    for directory in FRONT_DIRS:
        for p in (root / "frontend" / directory).rglob("*"):
            if p.is_file() and p.suffix.lower() in {".ts", ".tsx", ".mjs", ".js", ".css", ".json", ".svg", ".png", ".jpg", ".jpeg", ".webp", ".ico", ".woff", ".woff2"}:
                result.append(p)
    result.append(root / "frontend/scripts/run_managed_frontend.mjs")
    for name in ("run_managed_api.py", "managed_retention.py", "restore_private_backup.py", "plan_professor_expansion.py", "import_reviewed_professors.py"):
        result.append(root / "scripts" / name)
    for name in PILOT_FILES:
        result.append(root / "deploy/pilot" / name)
    for name in ("index.html", "about.html", "privacy.html", "terms.html", "contact.html"):
        result.append(root / "deploy/pilot/public-info" / name)
    return sorted(set(result))


def prepare(source, destination):
    destination = Path(destination).absolute()
    allowed_root = ROOT / "test-runtime"
    if destination.exists() or destination.is_symlink() or not destination.resolve().is_relative_to(allowed_root.resolve()):
        raise ValueError("Choose a new staging folder under test-runtime.")
    if any(p.is_symlink() or p.is_junction() for p in destination.parents):
        raise ValueError("Linked staging paths are forbidden.")
    files = selected_files(ROOT)
    for p in files:
        if p.is_symlink() or any(ancestor.is_symlink() or ancestor.is_junction() for ancestor in p.parents):
            raise ValueError("Linked deployment source is forbidden.")
        if p.suffix not in {".png", ".jpg", ".jpeg", ".webp", ".ico", ".woff", ".woff2"} and SECRET.search(p.read_text(encoding="utf-8")):
            raise ValueError("Potential credential in source; do not deploy.")
    destination.mkdir(parents=True, exist_ok=False)
    manifest = {}
    for p in files:
        rel = p.relative_to(ROOT)
        target = destination / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(p, target)
        manifest[rel.as_posix()] = hashlib.sha256(target.read_bytes()).hexdigest()
    seed = destination / "deploy/pilot/public-seed.db"
    result = export(source, seed)
    (destination / "deploy/pilot/seed-report.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    shutil.copyfile(destination / "deploy/pilot/railway.json", destination / "railway.json")
    (destination / ".dockerignore").write_text("**/.env\n**/.env.*\n!deploy/pilot/pilot.env.example\n**/__pycache__\n**/.next\n**/node_modules\n", encoding="utf-8")
    for p in destination.rglob("*"):
        if p.is_file():
            rel = p.relative_to(destination).as_posix()
            manifest[rel] = hashlib.sha256(p.read_bytes()).hexdigest()
    summary = {"source_files":len(files), "package_files":len(manifest), "public_seed":result,
               "private_runtime_files_copied":False, "source_secret_heuristic_passed":True,
               "manifest":manifest}
    (destination / "package-manifest.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True)
    parser.add_argument("--destination", required=True)
    args = parser.parse_args()
    result = prepare(args.source, args.destination)
    print(f"Prepared {result['package_files']} files and {result['public_seed']['rows']} public researcher rows. Nothing uploaded.")
