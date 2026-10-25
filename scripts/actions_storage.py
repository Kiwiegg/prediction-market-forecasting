"""Private S3 checkpoints; one non-expiring owner, CAS root, immutable SHA blobs.

No automatic takeover/retry. A lost/ambiguous write halts all local work. The
remote root, never the runner disk, is authoritative. SDK loaded only on opt-in.
"""
import contextlib
import json
import sqlite3
import threading
import uuid
from urllib.parse import urlsplit
from pathlib import Path

from cloud_state import State
from evidence_documents import canonical, digest


class StorageStop(BaseException):
    """Must escape legacy catch-and-record provider error handlers."""


class S3Objects:
    def __init__(self, bucket, prefix, region, endpoint=None):
        import boto3
        from botocore.config import Config
        if not bucket or not region or not prefix or prefix.startswith('/') or '..' in prefix.split('/'):
            raise ValueError('Explicit private bucket/region/prefix required')
        self.bucket, self.prefix = bucket, prefix.rstrip('/')+'/'
        self.r2=bool(endpoint)
        if endpoint and (urlsplit(endpoint).scheme!='https' or not urlsplit(endpoint).hostname.endswith('.r2.cloudflarestorage.com') or urlsplit(endpoint).path not in ('','/')):
            raise ValueError('Only explicit HTTPS R2 endpoints supported; AWS uses its SDK endpoint')
        self.client = boto3.client('s3', region_name=region,
            endpoint_url=endpoint,
            config=Config(retries={'total_max_attempts': 1}, connect_timeout=10, read_timeout=30,signature_version='s3v4'))

    def read(self, key):
        from botocore.exceptions import ClientError
        try:
            r=self.client.get_object(Bucket=self.bucket,Key=self.prefix+key)
            return r['Body'].read(),r['ETag']
        except ClientError as e:
            if e.response['Error']['Code'] in ('NoSuchKey','404'): return None,None
            raise StorageStop('Private storage read failed; no provider requests permitted') from None
        except Exception: raise StorageStop('Private storage read uncertain') from None

    def write(self, key, body, etag=None, create=False):
        args={'Bucket':self.bucket,'Key':self.prefix+key,'Body':body,'ContentType':'application/octet-stream'}
        if not self.r2:args['ServerSideEncryption']='AES256'
        if create: args['IfNoneMatch']='*'
        elif etag is not None: args['IfMatch']=etag
        else: raise StorageStop('Unconditional private writes forbidden')
        try: return self.client.put_object(**args)['ETag']
        except Exception as e:
            if create and getattr(e,'response',{}).get('Error',{}).get('Code') in ('PreconditionFailed','412'):
                existing,tag=self.read(key)
                if existing==body:return tag
            raise StorageStop('Storage CAS failed/uncertain; do not retry or send paid requests') from None


class Checkpoints:
    ROOT='root.json'
    def __init__(self, objects, expected_uuid=None):
        self.objects,self.expected_uuid=objects,expected_uuid
        self.root=None;self.etag=None;self.owner=None;self.poisoned=False
        self.lock=threading.RLock();self.files={};self.known=set()

    def _write_root(self, value, create=False):
        try: self.etag=self.objects.write(self.ROOT,canonical(value),self.etag,create)
        except BaseException:
            self.poisoned=True;raise
        self.root=value

    def open(self, run, initialize=False):
        body,self.etag=self.objects.read(self.ROOT)
        if body is None:
            if not initialize: raise StorageStop('Authoritative root missing; never initialize to recover lost state')
            if self.expected_uuid: raise StorageStop('Cannot reset a known store')
            self._write_root({'version':1,'store_uuid':str(uuid.uuid4()),'owner':None,'snapshot':None},True)
        else:
            self.root=json.loads(body)
            if initialize: raise StorageStop('Store exists; bootstrap is never a recovery operation')
        if self.expected_uuid and self.root['store_uuid']!=self.expected_uuid: raise StorageStop('Remote store identity mismatch')
        if self.root['owner'] is not None: raise StorageStop('Durable owner exists; confirm old runner stopped before explicit recovery')
        self.owner={'run':run,'nonce':str(uuid.uuid4())}
        self._write_root({**self.root,'owner':self.owner})
        return self.root['store_uuid']

    def assert_owner(self):
        if self.poisoned or not self.owner: raise StorageStop('Persistence unavailable/ownership absent')
        body,etag=self.objects.read(self.ROOT)
        if etag!=self.etag or json.loads(body or b'{}').get('owner')!=self.owner:
            self.poisoned=True;raise StorageStop('Owner fencing failed')

    def restore(self, destination):
        destination=Path(destination)
        if destination.exists() and any(destination.iterdir()):raise StorageStop('Restore only into a fresh runner directory')
        destination.mkdir(parents=True,exist_ok=True,mode=0o700)
        if not self.root['snapshot']:return
        raw,_=self.objects.read('snapshots/'+self.root['snapshot'])
        if raw is None or digest(raw)!=self.root['snapshot']:raise StorageStop('Snapshot manifest corrupt/missing')
        manifest=json.loads(raw);self.files=manifest['files'];self.known=set(self.files.values())
        for name,sha in self.files.items():
            p=(destination/name).resolve()
            if destination.resolve() not in p.parents:raise StorageStop('Unsafe captured path')
            body,_=self.objects.read('blobs/'+sha)
            if body is None or digest(body)!=sha:raise StorageStop('Private capture hash mismatch')
            p.parent.mkdir(parents=True,exist_ok=True,mode=0o700);p.write_bytes(body);p.chmod(0o600)

    def publish(self, directory, connection=None):
        with self.lock:
            self.assert_owner();directory=Path(directory);files={}
            paths=[p for p in directory.rglob('*') if p.is_file() and not p.name.startswith('.pending-') and not p.name.endswith(('.lock','-wal','-shm'))]
            for p in sorted(paths):
                name=str(p.relative_to(directory))
                if p.is_symlink():raise StorageStop('Symlink in private state')
                if name=='state.sqlite':
                    # SQLite backup is consistent even while the source uses WAL.
                    db=sqlite3.connect(':memory:')
                    own=connection is None
                    source=connection or sqlite3.connect(p)
                    try:source.backup(db);body=db.serialize()
                    finally:
                        db.close()
                        if own:source.close()
                else:body=p.read_bytes()
                sha=digest(body);files[name]=sha
                if sha not in self.known:
                    self.objects.write('blobs/'+sha,body,create=True);self.known.add(sha)
            manifest=canonical({'files':files,'previous':self.root['snapshot']})
            sha=digest(manifest)
            self.objects.write('snapshots/'+sha,manifest,create=True)
            self._write_root({**self.root,'snapshot':sha})
            self.files=files

    def close(self):
        with self.lock:
            self.assert_owner();self._write_root({**self.root,'owner':None});self.owner=None


class RemoteState(State):
    """Reuse native SQLite atomic budgets; commit remotely BEFORE returning a write.

    All worker threads share this lock/checkpointer. A failed commit is fatal,
    retains the remote owner, and cannot become a send-and-retry ambiguity.
    """
    def __init__(self, root, config, checkpoints, clock, initialize=False):
        self.checkpoints=checkpoints;self.ready=False;self.last_heartbeat={}
        super().__init__(root,config,clock,initialize)
        if initialize and checkpoints.root['snapshot'] is None:
            checkpoints._write_root({**checkpoints.root,'store_uuid':self.uuid})
        if checkpoints.root['store_uuid']!=self.uuid:raise StorageStop('SQLite/remote store identity mismatch')
        self.ready=True;self.sync()

    @contextlib.contextmanager
    def db(self):
        with self.checkpoints.lock:
            if self.checkpoints.poisoned:raise StorageStop('Authoritative storage unavailable')
            with super().db() as c:
                before=c.total_changes
                yield c
                c.commit()
                if self.ready and c.total_changes!=before:
                    try:self.checkpoints.publish(self.root,c)
                    except BaseException:
                        self.checkpoints.poisoned=True;raise

    def sync(self):
        try:self.checkpoints.publish(self.root)
        except BaseException:
            self.checkpoints.poisoned=True;raise

    def heartbeat(self,lane):
        if self.clock()-self.last_heartbeat.get(lane,0)>=60:
            super().heartbeat(lane);self.last_heartbeat[lane]=self.clock()

    def stage(self,*args,**kwargs):
        try:return super().stage(*args,**kwargs)
        finally:
            if not self.checkpoints.poisoned:self.sync()

    def reserve(self,*args,**kwargs):
        super().reserve(*args,**kwargs)
        # Also persist the immutable request receipt created after SQL commit.
        self.sync()

    def circuit(self,*args,**kwargs):
        super().circuit(*args,**kwargs);self.sync()

    def enroll(self,*args,**kwargs):
        result=super().enroll(*args,**kwargs);self.sync();return result

    def authorize(self,*args,**kwargs):
        result=super().authorize(*args,**kwargs);self.sync();return result
