"""GET-only blocked checkpoint accounting; never sends sources/models or owns state."""
import argparse
import gzip
import json
import os
import tempfile
from collections import Counter
from pathlib import Path
from unittest.mock import patch

import cloud_prospective as cloud
from actions_campaign import settings
from actions_storage import Checkpoints,S3Objects,StorageStop
from audit_live_pilot import ReadOnlyState
from evidence_documents import canonical,digest
from inspect_actions_storage import sanitized

FAILED_RUN='40600612996-1'
FAILED_COMMIT='ba2507a12177811d27e469126d2e54858bca00d1'


def termination_proof(value):
    if any(value.get(k)!=v for k,v in {'id':40600612996,'status':'completed','conclusion':'failure',
            'run_attempt':1,'head_sha':FAILED_COMMIT}.items()):raise ValueError('Old runner termination proof differs')
    return {k:value[k] for k in ('id','status','conclusion','run_attempt','head_sha')}


def audit(state):
    with state.db() as c:
        ledger=[dict(r) for r in c.execute('SELECT * FROM requests ORDER BY id')]
        stages=[dict(r) for r in c.execute('SELECT job,name,status FROM stages ORDER BY job,name')]
        circuits=[dict(r) for r in c.execute('SELECT * FROM circuits ORDER BY id')]
    providers=[];source_denials=[]
    for p in state.root.rglob('*.json'):
        m=json.loads(p.read_text())
        if not isinstance(m,dict) or 'http_status' not in m or 'body_sha256' not in m:continue
        body=gzip.decompress(p.with_suffix('.body.gz').read_bytes())
        if digest(body)!=m['body_sha256']:raise ValueError('Raw body changed')
        if 'provider' in m:
            request=p.with_suffix('.request.json').read_bytes()
            wire={k:m[k] for k in ('provider','method','url','payload')}
            if request!=canonical(wire)+b'\n' or digest(canonical(wire))!=m['source_id']:raise ValueError('Provider request identity differs')
            try:usage=json.loads(body).get('usage',{})
            except (ValueError,AttributeError):usage={}
            providers.append((p,m,usage))
        elif m['http_status'] in (401,403,407,451):
            source_denials.append({k:m.get(k) for k in ('source_id','url','http_status','retrieved_at_utc','body_sha256')})
    claims=[r for r in ledger if r['kind']!='article']
    rows=[];matched=set()
    for r in claims:
        receipt=state.root/'requests'/(r['id']+'.json')
        rec=json.loads(receipt.read_text()) if receipt.exists() else None
        if not rec or any(rec.get(k)!=r[v] for k,v in [('key','id'),('job','job'),('kind','kind'),('reserved_usd','usd')]):
            raise ValueError('Claim/receipt mismatch')
        candidates=[]
        for p,m,u in providers:
            if r['kind']=='forecast':eligible=r['id'] in p.parts
            else:eligible=state.job_dir(r['job']) in p.parents and digest((r['job']+r['kind']+m['source_id']).encode())==r['id']
            if eligible:candidates.append((p,m,u))
        if len(candidates)>1:raise ValueError('Multiple responses for one paid claim')
        item={'claim_id':r['id'],'job_id':r['job'],'kind':r['kind'],'reserved_usd':r['usd'],
              'ledger_status':r['status'],'claimed_at_utc':rec['at_utc'],'receipt_verified':True,
              'attempt_state':'uncertain_no_saved_response','http_status':None,'usage':None,'response_hash_verified':False}
        if candidates:
            p,m,u=candidates[0];matched.add(str(p))
            item.update(attempt_state='saved_http_response',http_status=m['http_status'],provider=m['provider'],
                source_id=m['source_id'],usage={k:u[k] for k in ('input_tokens','output_tokens') if k in u},
                started_at_utc=m['started_at_utc'],retrieved_at_utc=m['retrieved_at_utc'],
                latency_seconds=m['latency_seconds'],response_hash_verified=True,body_sha256=m['body_sha256'])
        rows.append(item)
    if len(matched)!=len(providers):raise ValueError('Unaccounted paid-provider captures')
    jobs=[]
    for key in state.jobs():
        j=state.job(key);g=j['game'];w=cloud.windows(g,state.config)
        proof=cloud.replay_job(state,key)
        jobs.append({'job_id':key,'game_id':g['game_id'],'home':g['home_name'],'away':g['away_name'],
            'tipoff_utc':g['recorded_start_utc'],'target_cutoff_utc':cloud.iso(w['target']),
            'freeze_deadline_utc':cloud.iso(w['freeze']),'forecast_deadline_utc':cloud.iso(w['forecast']),
            'stages':[s for s in stages if s['job']==key],'private_replay':proof,
            'disposition':'preserved_completed' if proof['forecasts'] else 'unrecoverable_expired_no_backfill' if state.clock()>w['freeze'] else 'incomplete_not_authorized_to_retry',
            'reserved_usd':sum(r['usd'] for r in claims if r['job']==key)})
    public=[]
    for p in (state.root/'public_claims').glob('*.json'):
        rec=json.loads(p.read_text());job=rec['job']
        folder=(state.root/'jobs/catalog'/job[len('catalog:'):] if job.startswith('catalog:') else state.job_dir(job)/rec['slot'])
        meta=folder/'raw'/(digest(rec['url'].encode())+'.json')
        public.append({'claim_id':p.stem,**rec,'saved_response_present':meta.exists()})
    return {'claims':rows,'paid_claim_count':len(rows),'reserved_usd':sum(r['usd'] for r in claims),
            'unknown_usage_reserved_usd':sum(r['reserved_usd'] for r in rows if r['attempt_state']=='uncertain_no_saved_response'),
            'claims_by_kind':dict(Counter(r['kind'] for r in rows)),
            'reported_tokens':{k:sum((r['usage'] or {}).get(k,0) for r in rows) for k in ('input_tokens','output_tokens')},
            'request_ledger_sha256':digest(canonical(ledger)),
            'zero_cost_article_claims':[{'claim_id':r['id'],'job_id':r['job'],'reserved_usd':r['usd'],'status':r['status']} for r in ledger if r['kind']=='article'],
            'circuits':circuits,
            'circuits_sha256':digest(canonical(circuits)),'jobs':jobs,'source_denials':source_denials,
            'public_claims':sorted(public,key=lambda r:r['claim_id']),
            'all_stages':stages,'new_paid_calls':0,'new_source_calls':0,'remote_writes':0,'provider_invoice_verified':False}


def inspect(objects,expected_uuid,destination,proof,allow_released=False):
    proof=termination_proof(proof)
    raw,_=objects.read('root.json');root=json.loads(raw or b'{}')
    if not expected_uuid or root.get('store_uuid')!=expected_uuid:raise StorageStop('Original UUID required')
    owner=root.get('owner')
    if (not owner and not allow_released) or owner and owner.get('run')!=FAILED_RUN:raise StorageStop('Unexpected owner; recovery forbidden')
    cp=Checkpoints(objects,expected_uuid);cp.root=root;cp.restore(destination)
    state=ReadOnlyState(destination,json.loads(cloud.CONFIG.read_text()))
    with patch('urllib.request.OpenerDirector.open',side_effect=AssertionError('Offline audit only')):result=audit(state)
    if any(digest((Path(destination)/n).read_bytes())!=sha for n,sha in cp.files.items()):raise StorageStop('Saved captures modified during audit')
    if objects.read('root.json')[0]!=raw:raise StorageStop('Checkpoint changed during audit')
    result={**result,'owner_run':owner['run'] if owner else None,'owner_sha256':digest(canonical(owner)),
            'snapshot_sha256':root['snapshot'],'private_files_verified_unchanged':len(cp.files),
            'store_uuid_verified':True,'termination_proof':proof}
    from campaign_recovery import preconditions
    try:
        detail=preconditions(state,result)
        result['recovery_preconditions']={'verified':True,**detail}
    except ValueError as e:result['recovery_preconditions']={'verified':False,'reason':str(e)}
    return result


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--termination-proof',type=Path,required=True)
    p.add_argument('--release-owner',action='store_true');p.add_argument('--confirm-reviewed-release',action='store_true');p.add_argument('--audit-sha256')
    args=p.parse_args()
    objects=S3Objects(os.environ.get('NBA_ACTIONS_BUCKET'),settings()['storage_prefix'],os.environ.get('AWS_REGION'),os.environ.get('NBA_ACTIONS_ENDPOINT'))
    with tempfile.TemporaryDirectory(prefix='nba-blocked-audit-') as tmp:
        if args.release_owner:
            if os.environ.get('NBA_ACTIONS_LIVE_ENABLED')!='false':raise ValueError('Live flag must remain disabled')
            from actions_campaign import verify_assets
            from campaign_recovery import release
            verify_assets(True)
            result=release(objects,os.environ.get('NBA_ACTIONS_STORE_UUID'),Path(tmp)/'state',json.loads(args.termination_proof.read_text()),args.audit_sha256,args.confirm_reviewed_release)
        else:result=inspect(objects,os.environ.get('NBA_ACTIONS_STORE_UUID'),Path(tmp)/'state',json.loads(args.termination_proof.read_text()),allow_released=True)
    result=sanitized(result,os.environ)
    args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_bytes(canonical(result)+b'\n')
    print(json.dumps(result if args.release_owner else {k:result[k] for k in ('paid_claim_count','reserved_usd','claims_by_kind','unknown_usage_reserved_usd','owner_run','snapshot_sha256','new_paid_calls','remote_writes')},indent=2))


if __name__=='__main__':main()
