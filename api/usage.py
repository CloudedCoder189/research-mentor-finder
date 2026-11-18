"""Bounded first-party daily counters, with no visitor identifiers or payloads."""
from contextlib import closing
from datetime import datetime, timedelta, timezone
import os
from pathlib import Path
import re
import sqlite3

PAGES = frozenset({'home', 'discover', 'recommendations', 'researcher', 'saved', 'account', 'profile_setup', 'outreach', 'draft', 'resources', 'starter', 'pathways'})
METRICS = frozenset({'searches', 'recommendation_requests', 'profile_saves', 'researchers_saved', 'outreach_updates', 'resume_previews'}) | {f'page:{p}' for p in PAGES}


def enabled():
    from api.auth.config import app_mode
    return os.getenv('AGGREGATE_USAGE_ENABLED', 'true' if app_mode() in {'public', 'production'} else 'false').lower() in {'1', 'true'}


def admin_email(email, user_id):
    allowed = {s.strip().casefold() for s in os.getenv('USAGE_ADMIN_EMAILS', '').split(',') if s.strip()}
    return bool(user_id.startswith('google:') and email.casefold() in allowed)


def store_path():
    import database
    return Path(database.DB_PATH).with_name('aggregate-usage.sqlite')


def increment(metric):
    if not enabled() or metric not in METRICS:
        return
    now = datetime.now(timezone.utc)
    try:
        with closing(sqlite3.connect(store_path(), timeout=.15)) as c:
            with c:
                c.execute('CREATE TABLE IF NOT EXISTS daily_counts(day TEXT NOT NULL, metric TEXT NOT NULL, total INTEGER NOT NULL, PRIMARY KEY(day,metric))')
                c.execute('CREATE TABLE IF NOT EXISTS collection(started_at TEXT NOT NULL)')
                c.execute('INSERT INTO collection SELECT ? WHERE NOT EXISTS(SELECT 1 FROM collection)', (now.isoformat(timespec='seconds'),))
                c.execute('INSERT INTO daily_counts VALUES(?,?,1) ON CONFLICT(day,metric) DO UPDATE SET total=MIN(total+1,1000000)', (now.date().isoformat(),metric))
                c.execute('DELETE FROM daily_counts WHERE day < ?', ((now-timedelta(days=89)).date().isoformat(),))
    except (OSError, sqlite3.Error):
        pass  # Measurement must never prevent a normal student action.


def action_metric(method, path):
    exact = {('POST','/api/search'):'searches', ('POST','/api/recommendations'):'recommendation_requests', ('PUT','/api/profile'):'profile_saves', ('POST','/api/profile/resume-preview'):'resume_previews'}
    if (method,path) in exact:
        return exact[(method,path)]
    if method == 'POST' and re.fullmatch(r'/api/saved/[1-9][0-9]*', path):
        return 'researchers_saved'
    if method == 'PATCH' and re.fullmatch(r'/api/outreach/[1-9][0-9]*', path):
        return 'outreach_updates'
    return None


def report(days=30):
    days = max(1,min(int(days),90))
    since = (datetime.now(timezone.utc)-timedelta(days=days-1)).date().isoformat()
    rows=[]; started=None
    path=store_path()
    if path.exists():
        with closing(sqlite3.connect(f'file:{path.resolve().as_posix()}?mode=ro',uri=True,timeout=.2)) as c:
            if c.execute("SELECT 1 FROM sqlite_master WHERE name='daily_counts'").fetchone():
                rows=[{'day':day,'metric':metric,'count':count} for day,metric,count in c.execute('SELECT day,metric,total FROM daily_counts WHERE day>=? ORDER BY day,metric',(since,))]
                first=c.execute('SELECT started_at FROM collection LIMIT 1').fetchone();started=first[0] if first else None
    import database
    with database.connect() as c:
        accounts=c.execute("SELECT COUNT(*) FROM users WHERE user_id LIKE 'google:%'").fetchone()[0]
    return {'days':days,'started_at':started,'enabled':enabled(),'registered_accounts':accounts,'rows':rows,'limitations':'Counts include repeat actions and may include automated traffic. They are not unique visitors or active users. No historical traffic is reconstructed. Daily aggregates are retained for 90 days; no names, emails, IP addresses, search text, researcher IDs, or visitor identifiers are stored in these counters.'}
