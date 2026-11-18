"""Explicit setup and sanitized encrypted restore; never switches services."""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import runtime_config  # Load only the private runtime configuration.
from api.retention import Store, initialize, BACKUP_NAME, _plain
from scripts.restore_private_backup import restore

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["initialize", "maintain", "restore"])
    parser.add_argument("--backup")
    parser.add_argument("--destination")
    args = parser.parse_args()
    store = initialize() if args.action == "initialize" else Store()
    if args.action in {"initialize", "maintain"}:
        store.maintain()
        print("Managed backup and expiry check completed.")
    else:
        if not args.backup or not args.destination or not BACKUP_NAME.fullmatch(args.backup):
            parser.error("Restore needs a managed backup filename and a new destination.")
        with store.connect() as ledger:
            if not ledger.execute("SELECT 1 FROM backups WHERE name=?", (args.backup,)).fetchone():
                parser.error("Backup is not registered in the current store.")
        restore(_plain(store.root / "backups" / args.backup), store.ledger, args.destination, cipher=store.cipher)
        print("Sanitized encrypted restore completed; no services switched.")
