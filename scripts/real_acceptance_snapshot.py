"""Read-only source snapshot and content fingerprints; no source imports."""
import hashlib
import json
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = Path(r'C:\Users\nirmi\Downloads\college-professor-finder-v9.3.1-complete - Copy\college-professor-finder-v9.3.1-complete\data\professors.db')
DEST = ROOT / 'test-runtime' / 'real-acceptance-20261004.db'
EVIDENCE = ROOT / 'evidence' / 'real-acceptance-2026-10-04'

def fingerprint(path):
    return {'sha256': hashlib.sha256(path.read_bytes()).hexdigest(), 'bytes': path.stat().st_size, 'mtime_ns': path.stat().st_mtime_ns}

def professors(connection):
    rows = connection.execute('SELECT * FROM professors ORDER BY id').fetchall()
    return {'rows': len(rows), 'content_sha256': hashlib.sha256(json.dumps(rows, ensure_ascii=False, default=str).encode()).hexdigest(), 'statuses': dict(connection.execute('SELECT verification_status, count(*) FROM professors GROUP BY verification_status')), 'missing_embeddings': connection.execute("SELECT count(*) FROM professors WHERE embedding_json = ''").fetchone()[0]}

if __name__ == '__main__':
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    DEST.parent.mkdir(parents=True, exist_ok=True)
    if DEST.exists():
        raise SystemExit('Refusing to overwrite existing acceptance database')
    before = fingerprint(SOURCE)
    with sqlite3.connect(SOURCE.as_uri() + '?mode=ro', uri=True) as source:
        baseline = professors(source)
        with sqlite3.connect(DEST) as isolated:
            source.backup(isolated)
            assert isolated.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
            assert professors(isolated) == baseline
    after = fingerprint(SOURCE)
    assert before == after
    (EVIDENCE / 'snapshot.json').write_text(json.dumps({'source': str(SOURCE), 'isolated': str(DEST), 'source_before': before, 'source_after_snapshot': after, 'professors': baseline}, indent=2), encoding='utf-8')
    print(json.dumps(baseline))
