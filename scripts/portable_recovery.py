"""Open a portable password-encrypted recovery bundle; never display secrets."""
from __future__ import annotations
import argparse
import base64
import getpass
import json
import os
from pathlib import Path
from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives.kdf.argon2 import Argon2id

FORMAT = 'professor-finder-recovery-v1'
MAX_BYTES = 65536


def password_cipher(password, salt):
    # RFC 9106 memory-constrained profile: 64 MiB, three iterations, four lanes.
    key = Argon2id(salt=salt,length=32,iterations=3,lanes=4,memory_cost=2**16).derive(password.encode('utf-8'))
    return Fernet(base64.urlsafe_b64encode(key))


def validate(payload):
    if not isinstance(payload,dict) or payload.get('format') != FORMAT:
        raise ValueError('Unsupported recovery contents.')
    Fernet(payload['backup_encryption_key'].encode('ascii'))
    storage = payload['storage']
    for name in ('accessKeyId','bucketName','endpoint','region','secretAccessKey'):
        if not isinstance(storage.get(name),str) or not storage[name]:
            raise ValueError('Incomplete recovery contents.')
    return payload


def seal(payload, password):
    validate(payload)
    if len(password) < 20:
        raise ValueError('Use a long recovery password.')
    salt = os.urandom(16)
    token = password_cipher(password,salt).encrypt(json.dumps(payload,sort_keys=True).encode())
    return json.dumps({'format':FORMAT,'salt':base64.b64encode(salt).decode(),
        'ciphertext':token.decode()},sort_keys=True).encode()


def open_bundle(content,password):
    if len(content) > MAX_BYTES:
        raise ValueError('Recovery bundle is too large.')
    try:
        envelope=json.loads(content)
        if envelope['format'] != FORMAT:
            raise ValueError('Unsupported recovery format.')
        salt=base64.b64decode(envelope['salt'],validate=True)
        if len(salt) != 16:
            raise ValueError('Invalid salt.')
        decoded=password_cipher(password,salt).decrypt(envelope['ciphertext'].encode())
        return validate(json.loads(decoded))
    except (KeyError,TypeError,AttributeError,ValueError,InvalidToken,UnicodeError):
        raise ValueError('Wrong password, damaged bundle, or unsupported recovery contents.') from None


def export_new(payload,directory):
    directory=Path(directory)
    # Existing folders are refused; only files created here may be cleaned up.
    directory.mkdir(mode=0o700)
    created=[]
    try:
        for name,content in (
            ('retention-key.txt',payload['backup_encryption_key'].encode()),
            ('storage-credentials.json',json.dumps(payload['storage'],indent=2).encode())):
            path=directory/name
            descriptor=os.open(path,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
            created.append(path)
            with os.fdopen(descriptor,'wb') as stream:
                stream.write(content)
    except BaseException:
        for path in created:
            path.unlink(missing_ok=True)
        directory.rmdir()
        raise
    return directory


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('bundle',type=Path)
    parser.add_argument('--output',type=Path,help='Export secrets to a NEW private directory. Omit to verify only.')
    args=parser.parse_args()
    try:
        if args.bundle.stat().st_size > MAX_BYTES:
            raise ValueError('Bundle too large.')
        payload=open_bundle(args.bundle.read_bytes(),getpass.getpass('Recovery password: '))
        if args.output:
            export_new(payload,args.output)
            print('Recovery secrets exported to the new directory. Keep it private and remove it after recovery.')
        else:
            print('Recovery bundle verified. No secrets exported or displayed.')
        return 0
    except (OSError,ValueError):
        print('Could not open/export recovery bundle. Check the password, file and new destination.')
        return 1


if __name__=='__main__':
    raise SystemExit(main())
