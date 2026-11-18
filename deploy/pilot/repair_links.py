"""One reviewed, idempotent URL repair; preserve identities and private data."""
from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from pathlib import Path
from urllib.parse import urlsplit

FIELDS = frozenset({'profile_url', 'website_url', 'data_source_url', 'opportunity_source_url'})
WEBSITE_METADATA = frozenset({'website_status', 'website_issue', 'website_checked_at', 'website_final_url'})
MISSING = 'Not publicly available'
PLAN = Path(__file__).with_name('link-repairs-20261025.json')


def _norm(value):
    value = str(value or '').strip()
    return '' if value == MISSING else value


def load_plan(path=PLAN):
    plan = json.loads(Path(path).read_text(encoding='utf-8'))
    records = plan['records']
    if plan.get('schema') != 1 or not records or len(records) > 100:
        raise ValueError('Invalid reviewed link plan.')
    seen = set()
    for item in records:
        identifier = item['id']
        if type(identifier) is not int or identifier <= 0 or identifier in seen:
            raise ValueError('Duplicate or invalid researcher identity.')
        seen.add(identifier)
        if not item['name'] or not item['university'] or not item['changes']:
            raise ValueError('Incomplete researcher identity or empty repair.')
        for field, change in item['changes'].items():
            if field not in FIELDS or set(change) != {'before', 'after'}:
                raise ValueError('Only reviewed URL fields may be repaired.')
            if not all(isinstance(value, str) for value in change.values()):
                raise ValueError('URL fields must be strings.')
            if _norm(change['after']):
                url = urlsplit(change['after'])
                if url.scheme != 'https' or not url.hostname or url.username or url.password:
                    raise ValueError('Replacement requires a public HTTPS URL.')
    return plan


def _pending(conn, plan):
    updates = []
    for item in plan['records']:
        row = conn.execute('SELECT * FROM professors WHERE id=?', (item['id'],)).fetchone()
        if row is None:
            continue  # An isolated test store may not contain this batch.
        row = dict(row)
        if (row['name'], row['university']) != (item['name'], item['university']):
            raise ValueError('Researcher identity changed; repair refused.')
        changes = {}
        for field, change in item['changes'].items():
            current = _norm(row[field])
            if current == _norm(change['after']):
                continue
            if current != _norm(change['before']):
                raise ValueError('URL changed since review; repair refused.')
            changes[field] = change['after']
        if 'website_url' in changes:
            available = bool(_norm(changes['website_url']))
            changes.update(website_status='Verified' if available else 'Not provided',
                           website_issue='Public page and identity checked; mentoring availability not verified.' if available else 'Removed a missing or generic website link after review.',
                           website_checked_at=plan['reviewed_at'],
                           website_final_url=changes['website_url'] if available else MISSING)
        if changes:
            updates.append((item['id'], changes))
    return updates


def _private_state(conn):
    names = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
             if r[0] not in {'professors', 'sqlite_sequence', 'app_migrations'}]
    return {name: [tuple(row) for row in conn.execute('SELECT * FROM "'+name.replace('"','""')+'" ORDER BY rowid')]
            for name in names}


def apply_reviewed_links(expected_database, *, plan_path=PLAN, backup=None):
    import database
    target = Path(expected_database).absolute()
    if any(p.is_symlink() or p.is_junction() for p in (target, *target.parents)):
        raise ValueError('Linked database targets are forbidden.')
    target = target.resolve(strict=True)
    if target != Path(database.DB_PATH).resolve():
        raise ValueError('Explicit database identity mismatch.')
    plan = load_plan(plan_path)
    with closing(sqlite3.connect(target, timeout=30)) as conn:
        conn.row_factory = sqlite3.Row
        if not _pending(conn, plan):
            return {'updated_records': 0, 'idempotent': True, 'private_tables_unchanged': True}
    if backup is None:
        from api.retention import Store
        backup = lambda: Store().maintain(force_backup=True, cleanup=False)
    if not backup():
        raise ValueError('Fresh encrypted backup required; nothing repaired.')
    with closing(sqlite3.connect(target, timeout=30)) as conn:
        conn.row_factory = sqlite3.Row
        conn.execute('PRAGMA foreign_keys=ON')
        conn.execute('BEGIN IMMEDIATE')
        try:
            pending = _pending(conn, plan)
            before = {r['id']: dict(r) for r in conn.execute('SELECT * FROM professors')}
            private = _private_state(conn)
            allowed = {}
            for identifier, changes in pending:
                allowed[identifier] = changes
                conn.execute('UPDATE professors SET '+','.join('"'+k+'"=?' for k in changes)+' WHERE id=?',
                             (*changes.values(), identifier))
            after = {r['id']: dict(r) for r in conn.execute('SELECT * FROM professors')}
            if set(after) != set(before):
                raise ValueError('Researcher identities were not preserved.')
            for identifier, row in before.items():
                if after[identifier] != {**row, **allowed.get(identifier, {})}:
                    raise ValueError('Unreviewed researcher fields changed.')
            if _private_state(conn) != private:
                raise ValueError('Private data preservation failed.')
            if pending:
                database._bump_data_revision(conn)
            if conn.execute('PRAGMA quick_check').fetchone()[0] != 'ok':
                raise ValueError('Database integrity check failed.')
            conn.commit()
        except BaseException:
            conn.rollback()
            raise
    return {'updated_records': len(pending), 'idempotent': False,
            'private_tables_unchanged': True, 'other_researcher_fields_unchanged': True,
            'fresh_encrypted_backup': True, 'professor_records_deleted': 0, 'paid_ai_calls': 0}
