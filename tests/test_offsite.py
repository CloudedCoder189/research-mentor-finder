import hashlib
import io
import json
import sqlite3
from contextlib import closing
from datetime import datetime, timedelta, timezone

import pytest
import database
from api.retention import initialize
from api.offsite import Archive, OffsiteError, MARKER
from api.auth import account_deletion


class Missing(Exception):
    response={'Error':{'Code':'NoSuchKey'}}


class FakeS3:
    def __init__(self):
        self.objects={}
        self.fail=False
        self.deleted=[]
    def get_object(self, Bucket, Key):
        if self.fail:
            raise RuntimeError('unshared-credential-detail')
        if Key not in self.objects:
            raise Missing()
        return {'Body':io.BytesIO(self.objects[Key][0])}
    def put_object(self, Bucket, Key, Body, **kwargs):
        if self.fail:
            raise RuntimeError('unshared-credential-detail')
        self.objects[Key]=(Body,kwargs.get('Metadata',{}))
    def head_object(self, Bucket, Key):
        if Key not in self.objects:
            raise Missing()
        body,metadata=self.objects[Key]
        return {'ContentLength':len(body),'Metadata':metadata}
    def get_paginator(self, name):
        return self
    def paginate(self, Bucket, Prefix):
        yield {'Contents':[{'Key':k} for k in self.objects if k.startswith(Prefix)]}
    def delete_object(self, Bucket, Key):
        self.deleted.append(Key)
        del self.objects[Key]


@pytest.fixture
def archive(tmp_path, monkeypatch):
    monkeypatch.setattr(database,'DB_PATH',tmp_path/'runtime.db')
    monkeypatch.setenv('RETENTION_ROOT',str(tmp_path/'managed'))
    monkeypatch.setenv('RETENTION_KEY_FILE',str(tmp_path/'key'))
    monkeypatch.setenv('GMAIL_TOKEN_DIR',str(tmp_path/'tokens'))
    monkeypatch.setenv('OFFSITE_BUCKET','private-test-bucket')
    monkeypatch.setenv('OFFSITE_PREFIX','dedicated-test')
    monkeypatch.setenv('OFFSITE_ENDPOINT','https://storage.example.test')
    database.initialize_database(run_maintenance=False)
    database.upsert_user(user_id='google:synthetic-alice',email='alice@example.test')
    database.upsert_user(user_id='google:synthetic-bob',email='bob@example.test')
    with database.connect() as conn:
        conn.execute("INSERT INTO student_profiles(user_id,interest_text) VALUES('google:synthetic-alice','robotics')")
        conn.execute("INSERT INTO sessions(token_hash,user_id,expires_at) VALUES('synthetic-token','google:synthetic-alice','2035-01-01')")
    store=initialize()
    store.maintain()
    return Archive(store,FakeS3())


def backup_name(archive):
    with closing(archive.store.connect()) as ledger:
        return ledger.execute('SELECT name FROM backups').fetchone()[0]


def test_ciphertext_sync_and_remote_restore(archive,tmp_path):
    result=archive.sync()
    assert result['covered_backups']==1
    assert all(b'SQLite format' not in body and b'alice@example' not in body
               for body,meta in archive.client.objects.values())
    destination=tmp_path/'new-restored.db'
    archive.restore(backup_name(archive),destination)
    with closing(sqlite3.connect(destination)) as conn:
        assert conn.execute('SELECT COUNT(*) FROM users').fetchone()[0]==2
        assert conn.execute('SELECT COUNT(*) FROM sessions').fetchone()[0]==0
        assert conn.execute('PRAGMA integrity_check').fetchone()[0]=='ok'


def test_receipt_newer_than_uploaded_ledger_prevents_resurrection(archive,tmp_path):
    archive.sync()
    subject=hashlib.sha256(b'google:synthetic-alice').hexdigest()
    archive.publish_receipt(subject,'2030-01-01T00:00:00+00:00')
    archive.restore(backup_name(archive),tmp_path/'restored.db')
    with closing(sqlite3.connect(tmp_path/'restored.db')) as conn:
        assert conn.execute('SELECT user_id FROM users').fetchall()==[('google:synthetic-bob',)]
        assert conn.execute('SELECT COUNT(*) FROM student_profiles').fetchone()[0]==0


def test_failed_receipt_blocks_live_deletion_and_hides_provider_details(archive,monkeypatch):
    monkeypatch.setenv('OFFSITE_BACKUPS','true')
    archive.client.fail=True
    monkeypatch.setattr('api.offsite.Archive',lambda *args:archive)
    with pytest.raises(account_deletion.DeletionError,match='recovery receipt') as error:
        account_deletion.delete_account('google:synthetic-alice')
    assert 'credential' not in str(error.value)
    assert database.get_user('google:synthetic-alice') is not None
    with database.connect() as conn:
        assert conn.execute('SELECT COUNT(*) FROM student_profiles').fetchone()[0]==1
        assert conn.execute('SELECT COUNT(*) FROM sessions').fetchone()[0]==1


def test_newer_recreated_account_survives_older_receipt(archive,tmp_path):
    subject=hashlib.sha256(b'google:synthetic-alice').hexdigest()
    archive.publish_receipt(subject,'2020-01-01T00:00:00+00:00')
    archive.sync()
    archive.restore(backup_name(archive),tmp_path/'restored.db')
    with closing(sqlite3.connect(tmp_path/'restored.db')) as conn:
        assert conn.execute('SELECT COUNT(*) FROM users').fetchone()[0]==2


def test_receipt_never_moves_backward(archive):
    subject=hashlib.sha256(b'google:synthetic-alice').hexdigest()
    archive.publish_receipt(subject,'2030-01-01T00:00:00+00:00')
    archive.publish_receipt(subject,'2020-01-01T00:00:00+00:00')
    data=archive.store.cipher.decrypt(archive.client.get_object(Bucket=archive.bucket,
        Key=archive.key('receipts/'+subject+'.fernet'))['Body'].read())
    assert json.loads(data)['deleted_at'].startswith('2030')


def test_expiry_preserves_unknown_objects_and_receipts(archive):
    archive.sync()
    prefix=archive.key('backups/')
    old=prefix+'backup-'+('a'*32)+'.fernet'
    unknown=prefix+'backup-'+('b'*32)+'.fernet'
    archive.client.objects[old]=(b'old',{'managed-by':MARKER,'created-at':'2020-01-01T00:00:00+00:00'})
    archive.client.objects[unknown]=(b'foreign',{})
    subject=hashlib.sha256(b'google:synthetic-alice').hexdigest()
    archive.publish_receipt(subject,'2030-01-01T00:00:00+00:00')
    archive.sync()
    assert archive.client.deleted==[old]
    assert unknown in archive.client.objects
    assert archive.key('receipts/'+subject+'.fernet') in archive.client.objects


def test_missing_remote_receipt_is_not_confused_with_outage(archive,tmp_path):
    archive.sync()
    archive.client.fail=True
    destination=tmp_path/'restored.db'
    with pytest.raises(OffsiteError):
        archive.restore(backup_name(archive),destination)
    assert not destination.exists()


def test_tampering_and_existing_destination_refused(archive,tmp_path):
    archive.sync()
    key=archive.key('backups/'+backup_name(archive))
    body,metadata=archive.client.objects[key]
    archive.client.objects[key]=(body[:-5]+b'XXXXX',metadata)
    destination=tmp_path/'restored.db'
    with pytest.raises(Exception):
        archive.restore(backup_name(archive),destination)
    assert not destination.exists()
    destination.write_text('preserve')
    with pytest.raises(OffsiteError):
        archive.restore(backup_name(archive),destination)
    assert destination.read_text()=='preserve'


def test_successful_deletion_has_remote_receipt_before_rows_disappear(archive,monkeypatch):
    monkeypatch.setenv('OFFSITE_BACKUPS','true')
    monkeypatch.setattr('api.offsite.Archive',lambda *args:archive)
    original=archive.publish_receipt
    observed=[]
    def publishing(*args):
        observed.append(database.get_user('google:synthetic-alice') is not None)
        return original(*args)
    monkeypatch.setattr(archive,'publish_receipt',publishing)
    assert account_deletion.delete_account('google:synthetic-alice')['deleted']
    assert observed==[True]
    assert database.get_user('google:synthetic-alice') is None
    subject=hashlib.sha256(b'google:synthetic-alice').hexdigest()
    assert archive.key('receipts/'+subject+'.fernet') in archive.client.objects


def test_sync_outage_is_visible_and_background_retry_recovers(archive,monkeypatch):
    import time
    from fastapi.testclient import TestClient
    from api.main import create_app
    import api.retention as retention
    monkeypatch.setenv('APP_MODE','local')
    monkeypatch.setenv('OFFSITE_BACKUPS','true')
    monkeypatch.setattr('api.offsite.Archive',lambda *args:archive)
    monkeypatch.setattr(retention,'CHECK_SECONDS',0.05)
    archive.client.fail=True
    with TestClient(create_app()) as client:
        assert client.get('/api/health').json()['offsite']['status']=='error'
        archive.client.fail=False
        deadline=time.monotonic()+5
        while client.get('/api/health').json()['offsite']['status']!='ok' and time.monotonic()<deadline:
            time.sleep(0.01)
        assert client.get('/api/health').json()['offsite']['covered_backups']==1


def test_remote_restore_needs_only_escrow_key_not_original_volume(archive,tmp_path):
    from types import SimpleNamespace
    archive.sync()
    recovered=Archive(SimpleNamespace(cipher=archive.store.cipher),archive.client)
    recovered.restore(backup_name(archive),tmp_path/'recovered.db')
    with closing(sqlite3.connect(tmp_path/'recovered.db')) as conn:
        assert conn.execute('SELECT COUNT(*) FROM users').fetchone()[0]==2
