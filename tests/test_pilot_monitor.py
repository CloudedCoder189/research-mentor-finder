from datetime import datetime,timedelta,timezone
from scripts.check_pilot_monitor import stale,evaluate_health,transition

NOW=datetime(2026,10,7,tzinfo=timezone.utc)

def healthy():
    return {'retention':{'status':'ok','last_success':NOW.isoformat()},
        'offsite':{'status':'ok','last_success':NOW.isoformat(),'covered_backups':2}}

def test_missing_health_is_not_healthy():
    assert set(evaluate_health({},NOW))=={'retention_failed','offsite_failed','no_synchronized_backups'}

def test_successful_status_with_stale_sync_still_alerts():
    data=healthy()
    data['offsite']['last_success']=(NOW-timedelta(hours=4)).isoformat()
    assert evaluate_health(data,NOW)==['offsite_stale']

def test_missing_timezone_or_large_clock_skew_is_not_fresh():
    assert stale('2026-10-07T00:00:00',NOW,3)
    assert stale(NOW+timedelta(hours=1),NOW,3)
    assert not stale(NOW+timedelta(minutes=1),NOW,3)

def test_daily_backup_threshold_and_missing_timestamp():
    assert not stale(NOW-timedelta(hours=26),NOW,27)
    assert stale(NOW-timedelta(hours=28),NOW,27)
    assert stale(None,NOW,27)

def test_new_failure_notifies_and_unchanged_failure_is_quiet():
    first=transition({},['app_unreachable'])
    assert first['notify'] and first['event']=='failure'
    assert not transition(first,['app_unreachable'])['notify']

def test_new_incident_component_and_recovery_notify():
    previous={'problems':['app_unreachable']}
    assert transition(previous,['app_unreachable','backup_storage_check_failed'])['notify']
    recovered=transition(previous,[])
    assert recovered['notify'] and recovered['event']=='recovery'
    assert not transition(recovered,[])['notify']

def test_current_health_is_quiet():
    assert evaluate_health(healthy(),NOW)==[]
    assert not transition({},[])['notify']


def test_public_signal_requires_exact_success():
    from scripts.check_pilot_monitor import evaluate_public_signal
    assert evaluate_public_signal(200, "ready") == []
    assert evaluate_public_signal(503, "unavailable") == ["public_backup_signal_unavailable"]
    assert evaluate_public_signal(200, "unexpected") == ["public_backup_signal_unavailable"]
    assert evaluate_public_signal(404, "Not found") == ["public_backup_signal_unavailable"]
