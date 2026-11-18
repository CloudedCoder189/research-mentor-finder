"""Private S3 ciphertext backups and synchronous deletion receipts."""
from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
import tempfile
from contextlib import closing
from datetime import datetime, timezone, timedelta
from pathlib import Path
from urllib.parse import urlsplit

from api.retention import Store, BACKUP_NAME

UTC = timezone.utc
MARKER = 'professor-finder-offsite-v1'


class OffsiteError(RuntimeError):
    pass


def enabled():
    return os.getenv('OFFSITE_BACKUPS', '').lower() == 'true'


class Archive:
    def __init__(self, store=None, client=None):
        self.store = store or Store()
        self.bucket = os.getenv('OFFSITE_BUCKET', '')
        self.prefix = os.getenv('OFFSITE_PREFIX', '')
        endpoint = os.getenv('OFFSITE_ENDPOINT', '')
        url = urlsplit(endpoint)
        if (url.scheme != 'https' or not url.hostname or url.username or url.password
                or url.query or url.fragment or url.path not in ('', '/')):
            raise OffsiteError('Configure a private HTTPS storage endpoint.')
        if not re.fullmatch(r'[a-z0-9][a-z0-9.-]{1,61}[a-z0-9]', self.bucket):
            raise OffsiteError('Configure a valid private bucket.')
        if not re.fullmatch(r'[a-zA-Z0-9_-]{1,64}', self.prefix):
            raise OffsiteError('Configure a dedicated backup namespace.')
        if client is None:
            import boto3
            from botocore.config import Config
            if not all(os.getenv(k) for k in ('OFFSITE_ACCESS_KEY_ID', 'OFFSITE_SECRET_ACCESS_KEY')):
                raise OffsiteError('Configure private storage credentials.')
            client = boto3.client('s3', endpoint_url=endpoint,
                aws_access_key_id=os.environ['OFFSITE_ACCESS_KEY_ID'],
                aws_secret_access_key=os.environ['OFFSITE_SECRET_ACCESS_KEY'],
                region_name=os.getenv('OFFSITE_REGION', 'auto'),
                config=Config(signature_version='s3v4', s3={'addressing_style':'virtual'},
                    connect_timeout=5, read_timeout=20, retries={'max_attempts':2,'mode':'standard'}))
        self.client = client

    def key(self, suffix):
        return self.prefix + '/' + suffix

    def get(self, key, *, missing=False):
        try:
            response = self.client.get_object(Bucket=self.bucket, Key=key)
            body = response['Body']
            try:
                return body.read()
            finally:
                body.close()
        except Exception as error:
            code = getattr(error, 'response', {}).get('Error', {}).get('Code')
            if missing and code in ('NoSuchKey', '404'):
                return None
            raise OffsiteError('Private storage could not be read.') from None

    def put_verified(self, key, content, **metadata):
        digest = hashlib.sha256(content).hexdigest()
        try:
            self.client.put_object(Bucket=self.bucket, Key=key, Body=content,
                ContentType='application/octet-stream',
                Metadata={'managed-by':MARKER, 'sha256':digest, **metadata})
            if hashlib.sha256(self.get(key)).hexdigest() != digest:
                raise OffsiteError('Private storage verification failed.')
        except OffsiteError:
            raise
        except Exception:
            raise OffsiteError('Private storage upload failed.') from None

    def publish_receipt(self, subject_hash, deleted_at):
        if not re.fullmatch(r'[0-9a-f]{64}', subject_hash):
            raise OffsiteError('Invalid deletion receipt.')
        stamp = datetime.fromisoformat(deleted_at)
        if stamp.tzinfo is None:
            raise OffsiteError('Deletion receipt needs a timezone.')
        key = self.key('receipts/' + subject_hash + '.fernet')
        existing = self.get(key, missing=True)
        if existing:
            prior = json.loads(self.store.cipher.decrypt(existing))
            if prior.get('subject_hash') != subject_hash:
                raise OffsiteError('Deletion receipt mismatch.')
            if datetime.fromisoformat(prior['deleted_at']) >= stamp:
                return
        content = self.store.cipher.encrypt(json.dumps({'schema':1,
            'subject_hash':subject_hash,'deleted_at':deleted_at}).encode())
        # Account locking serializes writes for this subject. The worker never
        # writes receipt keys, so it cannot overwrite a newer deletion receipt.
        self.put_verified(key, content)

    def sync(self, now=None):
        now = now or datetime.now(UTC)
        with closing(self.store.connect()) as ledger, closing(sqlite3.connect(':memory:')) as snapshot:
            ledger.backup(snapshot)
            rows = snapshot.execute('SELECT name,created_at FROM backups').fetchall()
            ledger_content = self.store.cipher.encrypt(snapshot.serialize())
        for name, stamp in rows:
            if not BACKUP_NAME.fullmatch(name):
                raise OffsiteError('Unexpected registered backup.')
            path = self.store.root/'backups'/name
            content = path.read_bytes()
            key = self.key('backups/' + name)
            expected = hashlib.sha256(content).hexdigest()
            try:
                head = self.client.head_object(Bucket=self.bucket, Key=key)
            except Exception as error:
                if getattr(error,'response',{}).get('Error',{}).get('Code') not in ('404','NoSuchKey'):
                    raise OffsiteError('Private backup inspection failed.') from None
                head = None
            if head is None:
                self.put_verified(key, content, **{'created-at':stamp})
            elif (head.get('ContentLength') != len(content)
                  or head.get('Metadata',{}).get('sha256') != expected):
                raise OffsiteError('Existing private backup differs; overwrite refused.')
        self.put_verified(self.key('current-ledger.fernet'), ledger_content)
        # Prune only our marked, expired backup objects after a successful sync.
        try:
            paginator = self.client.get_paginator('list_objects_v2')
            for page in paginator.paginate(Bucket=self.bucket, Prefix=self.key('backups/')):
                for item in page.get('Contents', []):
                    key = item['Key']
                    if not BACKUP_NAME.fullmatch(key.rsplit('/',1)[-1]):
                        continue
                    head = self.client.head_object(Bucket=self.bucket, Key=key)
                    metadata = head.get('Metadata',{})
                    if metadata.get('managed-by') != MARKER or not metadata.get('created-at'):
                        continue
                    created = datetime.fromisoformat(metadata['created-at'])
                    if created.tzinfo is not None and now-created >= timedelta(days=30):
                        self.client.delete_object(Bucket=self.bucket, Key=key)
        except Exception:
            raise OffsiteError('Private backup expiry could not finish.') from None
        latest=max((datetime.fromisoformat(stamp) for _,stamp in rows),default=None)
        return {'status':'ok','last_success':now.isoformat(),'covered_backups':len(rows),
            'latest_backup_at':latest.isoformat() if latest else None}

    def restore(self, name, destination):
        from scripts.restore_private_backup import restore
        if not BACKUP_NAME.fullmatch(name) or Path(destination).exists():
            raise OffsiteError('Choose a registered backup name and new destination.')
        # Promotion requires stopped writers. This helper writes only a new file.
        with tempfile.TemporaryDirectory(prefix='professor-finder-recovery-') as directory:
            root = Path(directory)
            encrypted = self.get(self.key('backups/'+name))
            backup = root/'backup.fernet'
            backup.write_bytes(encrypted)
            ledger = root/'ledger.db'
            ledger.write_bytes(self.store.cipher.decrypt(self.get(self.key('current-ledger.fernet'))))
            with closing(sqlite3.connect(':memory:')) as snapshot, closing(sqlite3.connect(ledger)) as current:
                snapshot.deserialize(self.store.cipher.decrypt(encrypted))
                current.execute('SELECT subject_hash,deleted_at FROM account_deletion_receipts LIMIT 0')
                for user_id, in snapshot.execute('SELECT user_id FROM users').fetchall():
                    subject = hashlib.sha256(user_id.encode()).hexdigest()
                    data = self.get(self.key('receipts/'+subject+'.fernet'), missing=True)
                    if data is None:
                        continue
                    receipt = json.loads(self.store.cipher.decrypt(data))
                    if receipt.get('schema') != 1 or receipt.get('subject_hash') != subject:
                        raise OffsiteError('Invalid remote deletion receipt.')
                    stamp = datetime.fromisoformat(receipt['deleted_at'])
                    if stamp.tzinfo is None:
                        raise OffsiteError('Invalid remote receipt timestamp.')
                    current.execute('INSERT INTO account_deletion_receipts VALUES(?,?) ON CONFLICT(subject_hash) DO UPDATE SET deleted_at=MAX(deleted_at,excluded.deleted_at)',(subject,receipt['deleted_at']))
                current.commit()
            return restore(backup,ledger,destination,cipher=self.store.cipher)


def publish_deletion_receipt(subject_hash, deleted_at):
    if enabled():
        try:
            Archive().publish_receipt(subject_hash, deleted_at)
        except Exception:
            raise OffsiteError('Deletion recovery receipt could not be secured.') from None
