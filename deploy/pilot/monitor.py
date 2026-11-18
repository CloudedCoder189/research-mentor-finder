"""Generic external-monitor signal; never returns private health details."""
from datetime import datetime,timedelta,timezone


def fresh(value,now,hours):
    try:
        stamp=datetime.fromisoformat(value.replace('Z','+00:00'))
        return stamp.tzinfo is not None and -timedelta(minutes=5)<=now-stamp<=timedelta(hours=hours)
    except (AttributeError,ValueError,TypeError):
        return False


def monitoring_healthy(data,now=None):
    now=now or datetime.now(timezone.utc)
    try:
        for component in ('retention','offsite'):
            status=data[component]
            if status.get('status')!='ok' or not fresh(status.get('last_success'),now,3):
                return False
        return (data['offsite'].get('covered_backups',0)>0
            and fresh(data['offsite'].get('latest_backup_at'),now,27))
    except (KeyError,AttributeError,TypeError):
        return False
