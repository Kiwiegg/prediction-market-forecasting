"""GET-only inspection of a frozen Actions checkpoint; never acquires ownership."""
import json
import os
import re
import sqlite3
import tempfile
from contextlib import closing
from pathlib import Path

from actions_campaign import settings
from actions_storage import S3Objects, StorageStop
from evidence_documents import digest
from prospective_sources import allowed_source

CLOCK_FAILURE_RUN = '40321487047-1'
CLOCK_FAILURE_DAY = '2026-10-26'
CLOCK_FAILURE_SNAPSHOT = '48ba34a01f6678f6b2233929f37255804ea9e50a590e1161b31c82821be6971f'


def inspect(objects, expected_uuid):
    def read(key, sha=None):
        body, _ = objects.read(key)
        if body is None or sha is not None and digest(body) != sha:
            raise ValueError('Saved object missing or hash mismatch')
        return body
    root = json.loads(read('root.json'))
    if not expected_uuid or root['store_uuid'] != expected_uuid:
        raise ValueError('Store UUID mismatch; nothing modified')
    snapshot = root.get('snapshot')
    if not snapshot: raise ValueError('No committed checkpoint')
    files = json.loads(read('snapshots/'+snapshot, snapshot))['files']
    result = {'read_only': True, 'uuid_matches': True, 'snapshot_sha256': snapshot,
              'owner_run': (root.get('owner') or {}).get('run'),
              'file_count': len(files), 'stage_errors': [], 'source_requests': []}
    for name, sha in sorted(files.items()):
        if name.startswith('events/') and name.endswith('.json'):
            value = json.loads(read('blobs/'+sha, sha))
            if value.get('kind') in ('stage_failed', 'worker_error'):
                result['stage_errors'].append({k: value.get(k) for k in
                    ('job','stage','kind','at_utc','error_type','reason')})
        elif name.startswith('jobs/catalog/') and '/raw/' in name and name.endswith('.json'):
            value = json.loads(read('blobs/'+sha, sha))
            if allowed_source(value.get('url','')) and 'http_status' in value:
                result['source_requests'].append({k:value.get(k) for k in
                    ('source_id','url','http_status','retrieved_at_utc','body_sha256','truncated')})
    if 'state.sqlite' in files:
        sha = files['state.sqlite']; body = read('blobs/'+sha, sha)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/'snapshot.sqlite'; path.write_bytes(body)
            with closing(sqlite3.connect(path.as_uri()+'?mode=ro&immutable=1', uri=True)) as db:
                db.row_factory = sqlite3.Row
                result['stages'] = [dict(r) for r in db.execute('SELECT job,name,status FROM stages')]
                result['circuits'] = [dict(r) for r in db.execute('SELECT id,body FROM circuits')]
                result['paid_claim_count'] = db.execute("SELECT count(*) FROM requests WHERE kind!='article'").fetchone()[0]
    return result


def sanitized(value, environment):
    # No source bytes, response headers or credentials. Also redact any configured
    # secret inadvertently embedded in an old free-form exception message.
    secrets = [v for k,v in environment.items() if v and len(v)>5 and any(
        word in k for word in ('SECRET','TOKEN','API_KEY','ACCESS_KEY','NBA_ACTIONS_'))]
    def clean(v):
        if isinstance(v,dict):return {k:clean(x) for k,x in v.items()}
        if isinstance(v,list):return [clean(x) for x in v]
        if isinstance(v,str):
            for secret in sorted(secrets,key=len,reverse=True):v=v.replace(secret,'[redacted]')
            return re.sub(r'sk-ant-[A-Za-z0-9_-]+','[redacted]',v)
        return v
    return clean(value)


def clock_repair_owner(objects, expected_uuid):
    """Permit only the inspected, zero-request constructor failure; no writes."""
    audit=inspect(objects,expected_uuid)
    expected_stage={'job':'catalog','name':CLOCK_FAILURE_DAY,'status':'failed'}
    if (audit['snapshot_sha256']!=CLOCK_FAILURE_SNAPSHOT or audit['owner_run']!=CLOCK_FAILURE_RUN
            or audit['stages']!=[expected_stage] or audit['source_requests'] or audit['circuits']
            or audit['paid_claim_count']!=0 or len(audit['stage_errors'])!=1):
        raise ValueError('Not the explicitly approved zero-request clock failure')
    error=audit['stage_errors'][0]
    if error['error_type']!='AttributeError' or error['reason']!="'SourceBudget' object has no attribute 'clock'":
        raise ValueError('Failure reason changed; recovery forbidden')
    body,_=objects.read('root.json');root=json.loads(body)
    if root['snapshot']!=audit['snapshot_sha256'] or (root.get('owner') or {}).get('run')!=CLOCK_FAILURE_RUN:
        raise ValueError('Root changed during read-only repair validation')
    return root['owner']


def main():
    objects = S3Objects(os.environ.get('NBA_ACTIONS_BUCKET'),settings()['storage_prefix'],
        os.environ.get('AWS_REGION'),os.environ.get('NBA_ACTIONS_ENDPOINT'))
    try:
        result = inspect(objects,os.environ.get('NBA_ACTIONS_STORE_UUID'))
    except (Exception,StorageStop) as exc:
        cause = exc.__context__
        response = getattr(cause,'response',{})
        result = {'read_only':True,'inspection_failed':True,'error_type':type(exc).__name__,
                  'reason':str(exc),'http_status':response.get('ResponseMetadata',{}).get('HTTPStatusCode'),
                  'storage_error_code':response.get('Error',{}).get('Code')}
        print(json.dumps(sanitized(result,os.environ),indent=2));raise SystemExit(1)
    print(json.dumps(sanitized(result,os.environ),indent=2))


if __name__=='__main__':main()
