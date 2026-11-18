import json
import pytest
from cryptography.fernet import Fernet
from scripts.portable_recovery import FORMAT,MAX_BYTES,seal,open_bundle,export_new

@pytest.fixture
def payload():
    return {'format':FORMAT,'backup_encryption_key':Fernet.generate_key().decode(),
        'storage':{'accessKeyId':'synthetic-access','secretAccessKey':'synthetic-secret',
        'bucketName':'synthetic-bucket','endpoint':'https://example.invalid','region':'auto'}}

def test_portable_roundtrip_has_no_windows_dependency(payload):
    password='synthetic-password-long-enough'
    content=seal(payload,password)
    assert open_bundle(content,password)==payload
    assert payload['backup_encryption_key'].encode() not in content
    assert b'synthetic-secret' not in content

def test_wrong_password_and_damaged_ciphertext_refused(payload):
    content=seal(payload,'synthetic-password-long-enough')
    with pytest.raises(ValueError): open_bundle(content,'wrong-password')
    damaged=json.loads(content)
    token=damaged['ciphertext']
    damaged['ciphertext']=token[:30]+('A' if token[30]!='A' else 'B')+token[31:]
    with pytest.raises(ValueError): open_bundle(json.dumps(damaged).encode(),'synthetic-password-long-enough')

def test_invalid_envelope_and_size_rejected():
    for data in (b'[]',b'{}',b'not json',b'x'*(MAX_BYTES+1)):
        with pytest.raises(ValueError): open_bundle(data,'any-password')

def test_different_salt_fails_authentication(payload):
    content=json.loads(seal(payload,'synthetic-password-long-enough'))
    content['salt']='AAAAAAAAAAAAAAAAAAAAAA=='
    with pytest.raises(ValueError): open_bundle(json.dumps(content).encode(),'synthetic-password-long-enough')

def test_short_password_refused(payload):
    with pytest.raises(ValueError): seal(payload,'short')

def test_export_refuses_existing_directory(payload,tmp_path):
    directory=tmp_path/'existing'
    directory.mkdir()
    marker=directory/'keep.txt'
    marker.write_text('untouched')
    with pytest.raises(FileExistsError): export_new(payload,directory)
    assert marker.read_text()=='untouched'

def test_explicit_export_only_expected_secrets(payload,tmp_path):
    destination=export_new(payload,tmp_path/'new')
    assert sorted(p.name for p in destination.iterdir())==['retention-key.txt','storage-credentials.json']
    assert (destination/'retention-key.txt').read_text()==payload['backup_encryption_key']
