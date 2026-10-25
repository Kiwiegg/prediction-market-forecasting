#!/usr/bin/env python3
"""GitHub Actions adapter. Offline plan by default; live mode explicitly gated."""
import argparse
import json
import os
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import cloud_prospective as cloud
from actions_campaign import CampaignState, settings, verify_assets, enroll_catalog, campaign_report
from actions_storage import S3Objects, Checkpoints, StorageStop
from cloud_state import durable_json
from evidence_documents import canonical, digest


def timing_plan(games,now,config):
    return [{'game_id':g['game_id'],'target_utc':cloud.iso(cloud.windows(g,config)['target']),
             'collection_start_utc':cloud.iso(cloud.windows(g,config)['collect']),
             'status':'missed_no_backfill' if now>cloud.windows(g,config)['collect'] else 'wait_on_runner'}
            for g in sorted(games,key=lambda g:(cloud.windows(g,config)['target'],g['game_id']))]


def preflight(environment, require_providers=True, clock_check=True):
    names=['NBA_ACTIONS_BUCKET','AWS_REGION','NBA_ACTIONS_STORE_UUID']
    if require_providers:names+=['BRAVE_SEARCH_API_KEY','ANTHROPIC_API_KEY']
    if any(not environment.get(k) for k in names):raise ValueError('Required storage/provider environment missing; values are never printed')
    if clock_check:
        result=subprocess.run(['timedatectl','show','-p','NTPSynchronized','--value'],capture_output=True,text=True)
        if result.returncode or result.stdout.strip()!='yes':raise ValueError('UTC clock synchronization not confirmed')


def catalog(state):
    slot=time.strftime('%Y-%m-%d',time.gmtime(state.clock()))
    def collect(folder):
        session=cloud.CloudSession(folder/'raw',state,'catalog:'+slot,'discovery',state.clock()+120)
        games,decisions=cloud.discovery.discover_verified(session,state.clock(),state.config['scheduler']['discovery_days'])
        return {'games':games,'decisions':decisions,'retrieved_at_utc':cloud.iso(state.clock())}
    # Claimed or failed catalog has no automatic retry. Completed catalog reused.
    return state.stage('catalog',slot,collect)


def run_worker(state,sleep=time.sleep):
    state.campaign();state.check_circuit('paid');state.check_circuit('network')
    started=state.clock();stop=started+settings()['worker_max_minutes']*60
    found=catalog(state);decisions=enroll_catalog(state,found,stop)
    state.event(None,'enrollment_decisions',decisions=decisions);state.sync()
    backend=cloud.LiveBackend(state,True);engine=cloud.Engine(state,backend)
    from cloud_market import MarketEngine
    market=MarketEngine(state,True)
    active=[]
    for key in state.jobs():
        w=cloud.windows(state.job(key)['game'],state.config)
        if state.clock()>w['collect'] and not state.has(key,'baseline'):
            state.event(key,'missed_window',reason='runner_not_ready_by_collection_start')
            # Durable terminal marker; neither collection nor inference may run.
            state.stage(key,'workflow_missed',lambda f:{'eligible':False,'reason':'late_start_no_backfill'})
        if not state.has(key,'workflow_missed') and not state.has(key,'forecast') and w['forecast']>=state.clock():active.append(key)
    with ThreadPoolExecutor(max_workers=state.config['scheduler']['workers']) as evidence_pool, ThreadPoolExecutor(max_workers=state.config['scheduler']['market_workers']) as market_pool:
        evidence_tasks={};market_tasks={};next_enrollment=started+60
        while active and state.clock()<stop:
            state.campaign();state.checkpoints.assert_owner();state.check_circuit('paid');state.check_circuit('network')
            if state.clock()>=next_enrollment:
                later=enroll_catalog(state,found,stop)
                new=[row for row in later if row['reason']=='enrolled_chronologically']
                if new:state.event(None,'enrollment_decisions',decisions=new);state.sync()
                active.extend(row['job_id'] for row in new)
                next_enrollment=state.clock()+60
            for key in active:
                for tasks,pool,worker in ((evidence_tasks,evidence_pool,engine),(market_tasks,market_pool,market)):
                    future=tasks.get(key)
                    if future is not None and future.done():future.result();tasks.pop(key)
                    if key not in tasks:tasks[key]=pool.submit(worker.advance,key)
            state.heartbeat('actions_worker')
            active=[k for k in active if not state.has(k,'forecast') and state.clock()<=cloud.windows(state.job(k)['game'],state.config)['forecast']]
            sleep(settings()['poll_seconds'])
        for future in [*evidence_tasks.values(),*market_tasks.values()]:future.result()
    state.sync();return campaign_report(state)


def recover_owner(objects, expected_uuid, expected_owner, confirmation):
    if confirmation!='CONFIRMED_OLD_RUNNER_TERMINATED':raise ValueError('Confirm old runner termination before recovery')
    raw,etag=objects.read(Checkpoints.ROOT)
    if raw is None:raise StorageStop('Missing root is not recoverable by reset')
    root=json.loads(raw)
    if root['store_uuid']!=expected_uuid or root['owner']!=json.loads(expected_owner):raise StorageStop('Recovery owner/UUID mismatch')
    # This preserves every snapshot, claim and denial; only ownership changes.
    audit=canonical({'old_owner':root['owner'],'snapshot':root['snapshot'],'recovered_at_utc':cloud.iso(time.time()),'confirmation':confirmation})
    objects.write('recoveries/'+digest(audit),audit,create=True)
    objects.write(Checkpoints.ROOT,canonical({**root,'owner':None}),etag)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--live',action='store_true');parser.add_argument('--allow-network',action='store_true')
    parser.add_argument('--allow-search',action='store_true');parser.add_argument('--allow-inference',action='store_true')
    parser.add_argument('--bootstrap',action='store_true');parser.add_argument('--authorize',action='store_true');parser.add_argument('--expand',action='store_true')
    parser.add_argument('--confirm-authorized-campaign',action='store_true');parser.add_argument('--automatic',action='store_true')
    parser.add_argument('--game-id',action='append',default=[]);parser.add_argument('--expires');parser.add_argument('--max-games',type=int,default=1);parser.add_argument('--max-usd',type=float,default=50)
    parser.add_argument('--discover-only',action='store_true');parser.add_argument('--status',action='store_true');parser.add_argument('--replay',action='store_true')
    parser.add_argument('--recover-owner');parser.add_argument('--confirm-old-runner-terminated')
    parser.add_argument('--state',type=Path);parser.add_argument('--run-id',default=os.environ.get('GITHUB_RUN_ID','operator')+'-'+os.environ.get('GITHUB_RUN_ATTEMPT','1'))
    parser.add_argument('--validate-assets',action='store_true')
    args=parser.parse_args();cfg=cloud.checked(json.loads(cloud.CONFIG.read_text()));deployment=settings()
    if args.validate_assets:print(json.dumps({'verified':True,'assets_sha256':verify_assets()}));return
    selected=args.live or args.bootstrap or args.authorize or args.expand or args.discover_only or args.status or args.replay or args.recover_owner
    if not selected:
        print(json.dumps({'mode':'offline_plan','paid_enabled':False,'settings':deployment,'evidence_windows':cfg['evidence'],
            'forecast_windows':cfg['forecast'],'network_calls':0,'paid_calls':0,'next_game':'unknown: explicit schedule discovery needed',
            'strategy':'20-minute off-hour dispatch, runner ready before T-30, 90-minute lookahead, strict missed-window exclusion'},indent=2));return
    if not args.allow_network or not args.state:parser.error('Remote state commands require explicit network opt-in and fresh --state directory')
    if args.live and not (args.allow_search and args.allow_inference):parser.error('Live mode requires explicit search and inference opt-ins')
    if args.live:preflight(os.environ)
    if args.authorize or args.expand:
        if not args.confirm_authorized_campaign or not args.expires:parser.error('Explicit campaign authorization and expiry required')
    verify_assets(True)
    objects=S3Objects(os.environ.get('NBA_ACTIONS_BUCKET'),deployment['storage_prefix'],os.environ.get('AWS_REGION'),os.environ.get('NBA_ACTIONS_ENDPOINT'))
    expected=os.environ.get('NBA_ACTIONS_STORE_UUID')
    if not args.bootstrap and not expected:parser.error('Original store UUID is mandatory; never reset missing state')
    if args.recover_owner:
        recover_owner(objects,expected,args.recover_owner,args.confirm_old_runner_terminated);print('Owner released; all request claims retained');return
    cp=Checkpoints(objects,expected)
    cp.open(args.run_id,args.bootstrap);state=None;success=False
    try:
        cp.restore(args.state)
        if sum(p.stat().st_size for p in args.state.rglob('*') if p.is_file())>deployment['maximum_snapshot_bytes']:raise StorageStop('Private state exceeds initial pilot storage bound; review architecture before growth')
        state=CampaignState(args.state,cfg,cp,time.time,initialize=args.bootstrap)
        if args.bootstrap:result={'store_uuid':state.uuid,'status':'private_store_initialized_no_collection'}
        elif args.authorize:result=state.approve(args.game_id,args.expires,args.max_games,args.max_usd,args.automatic)
        elif args.expand:result=state.expand(args.expires,args.max_games,args.max_usd,args.automatic,args.game_id)
        elif args.discover_only:
            found=catalog(state);result={'game_plan':timing_plan(found['games'],state.clock(),cfg),'paid_calls':0}
        elif args.replay:result={'replays':[cloud.replay_job(state,k) for k in state.jobs()]}
        elif args.status:result={'state':state.status(),'campaign':campaign_report(state)}
        else:result=run_worker(state)
        state.sync();success=True
        # Only aggregate monitoring goes to public Actions logs, never raw data,
        # source text, credentials, request headers or private forecast responses.
        if args.live:print(json.dumps({k:result[k] for k in ('campaign_id','enrolled','attempted','captured','primary_eligible','reserved_usd','ceiling_usd')}))
        elif args.authorize or args.expand:print(json.dumps({'status':'authorized_not_started','max_games':result['max_games'],'max_usd':result['max_usd']}))
        elif args.replay:print(json.dumps(result))
        elif args.status:print(json.dumps({'jobs':result['state']['jobs'],'circuits':result['state']['circuits'],'reserved_usd':result['campaign']['reserved_usd']}))
        else:print(json.dumps(result,indent=2))
    finally:
        if success and not cp.poisoned:cp.close()
        # Any interruption retains owner and durable claims. Never auto-takeover.


if __name__=='__main__':
    try:main()
    except (Exception,StorageStop):
        raise SystemExit('Actions worker stopped. Inspect private state/owner/claims; no automatic paid retry. Details intentionally withheld from public logs.')
