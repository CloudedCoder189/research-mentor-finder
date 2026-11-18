import io,json
from datetime import datetime,timedelta,timezone
import pytest
from deploy.pilot.monitor import monitoring_healthy
from deploy.pilot.start import Health

NOW=datetime(2026,10,7,tzinfo=timezone.utc)
def healthy():
    return {'retention':{'status':'ok','last_success':NOW.isoformat()},
        'offsite':{'status':'ok','last_success':NOW.isoformat(),
        'covered_backups':2,'latest_backup_at':NOW.isoformat()}}

def test_current_backups_are_healthy():
    assert monitoring_healthy(healthy(),NOW)

@pytest.mark.parametrize('change',[
    ('offsite','status','error'),('offsite','covered_backups',0),
    ('offsite','last_success',(NOW-timedelta(hours=4)).isoformat()),
    ('retention','last_success',(NOW-timedelta(hours=4)).isoformat()),
    ('offsite','latest_backup_at',(NOW-timedelta(hours=28)).isoformat()),
    ('offsite','latest_backup_at','2026-10-07T00:00:00'),
    ('offsite','latest_backup_at',(NOW+timedelta(hours=1)).isoformat()),
])
def test_failure_and_stale_backup_refuse_healthy_signal(change):
    data=healthy()
    component,key,value=change
    data[component][key]=value
    assert not monitoring_healthy(data,NOW)

def test_missing_health_is_not_healthy():
    assert not monitoring_healthy({},NOW)
    assert not monitoring_healthy(None,NOW)

def invoke(monkeypatch,path,data,*,head=False):
    import deploy.pilot.start as start
    class Reply(io.BytesIO):
        status=200
    responses=iter([Reply(json.dumps(data).encode()),Reply()])
    monkeypatch.setattr(start.urllib.request,'urlopen',lambda *args,**kwargs:next(responses))
    handler=object.__new__(Health)
    handler.path=path
    handler.wfile=io.BytesIO()
    statuses=[]
    headers=[]
    handler.send_response=lambda code:statuses.append(code)
    handler.send_header=lambda name,value:headers.append((name,value))
    handler.end_headers=lambda:None
    handler.do_HEAD() if head else handler.do_GET()
    return statuses[0],handler.wfile.getvalue(),headers

def test_backup_outage_does_not_block_deployment_readiness(monkeypatch):
    data=healthy()
    data['offsite']['status']='error'
    assert invoke(monkeypatch,'/__pilot_health',data)[:2]==(200,b'ready')
    assert invoke(monkeypatch,'/__pilot_monitor',data)[:2]==(503,b'unavailable')

def test_external_response_has_no_private_details(monkeypatch):
    data=healthy()
    # Use real current time for the HTTP handler's freshness check.
    now=datetime.now(timezone.utc).isoformat()
    data['retention']['last_success']=now
    data['offsite'].update(last_success=now,latest_backup_at=now)
    data['account']='private account marker'
    status,body,headers=invoke(monkeypatch,'/__pilot_monitor',data)
    assert (status,body)==(200,b'ready')
    assert ('Cache-Control','no-store') in headers
    assert b'private' not in body

def test_query_string_cannot_skip_backup_check(monkeypatch):
    data=healthy()
    data['offsite']['status']='error'
    assert invoke(monkeypatch,'/__pilot_monitor?cache=1',data)[:2]==(503,b'unavailable')

def test_head_reports_status_without_body(monkeypatch):
    data=healthy()
    now=datetime.now(timezone.utc).isoformat()
    data['retention']['last_success']=now
    data['offsite'].update(last_success=now,latest_backup_at=now)
    assert invoke(monkeypatch,'/__pilot_monitor',data,head=True)[:2]==(200,b'')
