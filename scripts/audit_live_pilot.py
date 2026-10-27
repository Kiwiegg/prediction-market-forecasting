"""Read-only saved-capture audit. No source retrieval, inference or outcome join."""
import argparse
import contextlib
import gzip
import json
import math
import os
import sqlite3
import tempfile
import time
from collections import Counter
from pathlib import Path

import cloud_prospective as cloud
from actions_campaign import settings
from actions_storage import Checkpoints,S3Objects
from cloud_state import State
from evidence_documents import canonical,digest
from inspect_actions_storage import sanitized


class ReadOnlyState(State):
    """Use existing replay/artifact readers without State's initializer/writes."""
    def __init__(self,root,config):
        self.root,self.config,self.clock=Path(root),config,time.time
        self.config_sha=digest(canonical(config));self.registry_sha=digest(cloud.REGISTRY.read_bytes())
        self.uuid=json.loads((self.root/'volume.json').read_text())['store_uuid']
        with self.db() as c:
            if [r[0] for r in c.execute('SELECT uuid FROM store_identity')]!=[self.uuid]:raise ValueError('Volume/database identity differs')

    @contextlib.contextmanager
    def db(self):
        with contextlib.closing(sqlite3.connect((self.root/'state.sqlite').resolve().as_uri()+'?mode=ro&immutable=1',uri=True)) as c:
            c.row_factory=sqlite3.Row
            yield c


def read_json(path):return json.loads(Path(path).read_text())


def observations(state,key,packet,records,configs):
    specs={'direct':[cloud.native.direct.request_spec(packet,configs['direct'])],
           'v1':[cloud.native.v1.group_spec(g,configs['v1']) for g in cloud.native.v1.build_groups(packet)],
           'v2':[cloud.native.v2_evidence.group_spec(g,configs['v2']) for g in cloud.native.v2_evidence.build_groups(packet)]}
    result={}
    for name in cloud.native.ORDER:
        game=records[name];rows=[game] if name=='direct' else game['groups'];out=[]
        for record,spec in zip(rows,specs[name]):
            cache=state.root/'shared_cache'/name/spec['key'];raw=record.get('raw_response')
            raw_verified=False
            if raw:
                cloud.native.direct.verify_raw(record,cache)
                request_sha=digest(canonical(spec['wire']))
                if (cache/'raw'/(request_sha+'.request.json')).read_bytes()!=canonical(spec['wire'])+b'\n':
                    raise ValueError('Actual model wire differs from frozen evidence-only specification')
                try:response=json.loads(gzip.decompress((cache/raw['body_file']).read_bytes()))
                except (ValueError,UnicodeError):
                    if record['status'] in ('success','insufficient'):raise
                    response=None
                if record['status'] in ('success','insufficient'):
                    if name=='direct':
                        if cloud.native.direct.validated_response(response,spec,configs[name])!=record['home_win_probability']:raise ValueError('Parsed direct response differs')
                    elif name=='v1':
                        parsed=cloud.native.v1.validate_response(response,spec,configs[name])
                        if any(record[k]!=v for k,v in parsed.items()):raise ValueError('Parsed v1 response differs')
                    else:
                        parsed=cloud.native.v2.parse_response(response,spec,configs[name])
                        if any(record[k]!=v for k,v in parsed.items()):raise ValueError('Parsed v2 response differs')
                raw_verified=True
            row={k:record.get(k) for k in ('group','status','request_sha256','evidence_sha256','group_evidence_sha256',
                'likelihood_ratio','assessment','evidence_sufficiency','missing_reason','usage','estimated_cost_usd',
                'estimated_cost_kind','latency_seconds','request_started_at_utc','response_retrieved_at_utc','returned_model')}
            row.update(raw_response_hash_verified=raw_verified,request_identity=spec['key'])
            out.append(row)
        result[name]={'status':game['status'],'parent_hash':game['evidence_sha256'],
            'probabilities':{'direct':game['home_win_probability']} if name=='direct' else
                {variant:data['home_win_probability'] for variant,data in game['variants'].items()},
            'observations':out,'rates':configs[name]['prices']}
    return result


def audit(state,key):
    job=state.job(key);game=job['game'];folder=state.job_dir(key);w=cloud.windows(game,state.config)
    proof=cloud.replay_job(state,key)
    frozen=state.artifact(key,'freeze');forecast=state.artifact(key,'forecast')
    packet=cloud.load_game_snapshot(folder/'freeze',game['game_id'])
    lineage=read_json(folder/'freeze/lineage.json');run=read_json(folder/'forecast/run.json')
    methods=observations(state,key,packet,forecast['records'],run['configs'])
    stages={};source_rows=[]
    for name in ('baseline','refresh','news','extraction'):
        value=state.artifact(key,name)
        stages[name]={'started_at_utc':value.get('started_at_utc') or value.get('audit',{}).get('started_at_utc'),
                      'finished_at_utc':value.get('finished_at_utc') or value.get('captured_at_utc') or value.get('audit',{}).get('finished_at_utc')}
        if name in ('baseline','refresh'):
            for meta in value['sources']:
                source_rows.append({k:meta.get(k) for k in ('source_id','url','http_status','retrieved_at_utc','body_sha256')})
    acquisition=state.artifact(key,'news');extraction=state.artifact(key,'extraction')
    for page in acquisition['sources_and_validation']:
        source_rows.append({k:page.get(k) for k in ('source_id','url','retrieved_at_utc','published_at_utc','body_sha256')})
    retrievals=[r for r in source_rows if r.get('retrieved_at_utc')]
    retrieval_ok=all(cloud.native.aware(r['retrieved_at_utc'])<=w['retrieve'] for r in retrievals)
    findings=[]
    for finding in packet['injury_news']['news']['findings']:
        refs=finding['source_references']
        supported=bool(refs) and any(finding['claim']==r['supported_claim'] and r['supported_claim'] in r['supporting_excerpt'] for r in refs)
        clocks=all(cloud.native.aware(r[k])<=w['target'] for r in [finding,*refs] for k in ('published_at_utc','retrieved_at_utc'))
        findings.append({k:finding[k] for k in ('category','team','player','claim','source_url','published_at_utc','retrieved_at_utc')})
        findings[-1].update(verbatim_supported=supported,timestamps_eligible=clocks,source_references=[
            {k:r[k] for k in ('source_ref','source_id','url','published_at_utc','retrieved_at_utc')} for r in refs])
    official=packet['injury_news']['official_injury']
    # Reuse the same successful source set as freeze, and inspect only facts
    # actually used for features; rejected/unavailable rows are not imputed.
    try:chosen=state.artifact(key,'refresh')
    except (ValueError,FileNotFoundError):chosen=state.artifact(key,'baseline')
    used={gid for side in ('home','away') for ids in lineage['statistics'][side].get('feature_game_ids',{}).values() for gid in ids}
    facts={h['game_id']:h for h in chosen['history']['history']}
    statistical_clocks_ok=all(gid!=game['game_id'] and gid in facts and facts[gid].get('available_by_utc') and facts[gid].get('end_utc')
        and all(cloud.native.aware(facts[gid][k])<=w['target'] for k in ('end_utc','available_by_utc','recap_published_utc','recap_modified_utc','event_updated_utc') if facts[gid].get(k)) for gid in used)
    injury_clocks_ok=True
    if official['report_source_id']:
        report=chosen['injuries']['reports'][official['report_source_id']]
        injury_clocks_ok=(cloud.native.aware(report['issue_utc'])<=cloud.native.aware(report['creation_utc'])<=
                          cloud.native.aware(report['retrieved_at_utc'])<=w['target'])
    injury={k:official[k] for k in ('publication_verification','report_url','report_issue_utc','published_at_utc',
        'independent_historical_public_capture_verified','latest_report_globally_verified','selection_scope')}
    for side in ('home','away'):
        team=official[side]
        injury[side]={'state':team['state'],'player_count':len(team['players']),
            'statuses':dict(Counter(p['status'] for p in team['players'])),'uncertainty_flags':team['uncertainty_flags'],
            'players':[{k:p[k] for k in ('player','status','reason','page','source_ref','uncertainty_flags')} for p in team['players']]}
    with state.db() as c:
        stage_rows=[dict(r) for r in c.execute('SELECT name,status FROM stages WHERE job=?',(key,))]
        claims=[dict(r) for r in c.execute('SELECT id,kind,usd,status FROM requests WHERE job=?',(key,))]
        circuits=[dict(r) for r in c.execute('SELECT id,body FROM circuits')]
    market={'eligible':False,'midpoint':None,'missing_reason':'market_stage_not_completed'}
    if any(r['name']=='market' and r['status']=='done' for r in stage_rows):
        from prospective_evaluate import verify_source_capture
        quote=verify_source_capture(folder/'market','quote')
        market={k:quote[k] for k in ('eligible','missing_reason','ticker','retrieved_at_utc','target_cutoff_utc',
            'yes_bid','yes_ask','spread','midpoint','deviation_seconds','actual_quote_age_seconds','method')}
        market['raw_source_replay_verified']=True
    else:
        errors=[]
        for path in (state.root/'events').glob('*.json'):
            e=read_json(path)
            if e.get('job')==key and e.get('stage')=='market' and e.get('kind')=='stage_failed':errors.append({k:e.get(k) for k in ('error_type','reason','at_utc')})
        market['failure_events']=errors
    provider_calls=[];metadata_paths=[]
    for stage in ('news','extraction','forecast'):
        metadata_paths.extend((folder/stage).rglob('*.json'))
    for name,method in methods.items():
        for o in method['observations']:
            metadata_paths.extend((state.root/'shared_cache'/name/o['request_identity']/'raw').glob('*.json'))
    seen=set()
    for path in metadata_paths:
        meta=read_json(path)
        if isinstance(meta,dict) and all(k in meta for k in ('provider','method','http_status','source_id','body_sha256','started_at_utc')) and meta['source_id'] not in seen:
            seen.add(meta['source_id'])
            provider_calls.append({k:meta.get(k) for k in ('provider','method','http_status','source_id','body_sha256','started_at_utc','retrieved_at_utc','latency_seconds','error')})
    direct_and_groups=[o for m in methods.values() for o in m['observations']]
    tokens={k:sum((o['usage'] or {}).get(k,0) for o in direct_and_groups) for k in ('input_tokens','output_tokens')}
    extraction_usage=extraction['audit']['reported_provider_usage']
    extraction_tokens={k:sum(u.get('usage',{}).get(k,0) for u in extraction_usage) for k in ('input_tokens','output_tokens')}
    research_config=read_json(cloud.native.CONFIG)
    extraction_cost=(extraction_tokens['input_tokens']*research_config['prices']['input_usd_per_million']+
                     extraction_tokens['output_tokens']*research_config['prices']['output_usd_per_million'])/1e6
    search_count=sum(c['provider']=='brave' for c in provider_calls)
    forecast_cost=sum(o.get('estimated_cost_usd') or 0 for o in direct_and_groups)
    known_estimate=forecast_cost+extraction_cost+search_count*research_config['prices']['query_usd']
    same_hash=all(m['parent_hash']==frozen['packet_sha256'] for m in methods.values())
    model_times_ok=all(not o['request_started_at_utc'] or cloud.native.aware(o['request_started_at_utc'])>=cloud.native.aware(frozen['frozen_at_utc']) for o in direct_and_groups)
    receipt_times=[read_json(state.root/'requests'/(r['id']+'.json'))['at_utc'] for r in claims]
    approval=read_json(state.root/'campaign.json')
    authorized=all(cloud.native.aware(approval['authorized_at_utc'])<=cloud.native.aware(t)<=cloud.native.aware(approval['expires_at_utc']) for t in receipt_times)
    checks={'private_replay':proof['verified'],'source_retrievals_by_cutoff':retrieval_ok,
        'packet_frozen_by_deadline':cloud.native.aware(frozen['frozen_at_utc'])<=w['freeze'],
        'forecasts_sealed_by_deadline':cloud.native.aware(forecast['sealed_at_utc'])<=w['forecast'],
        'same_packet_all_methods':same_hash,'model_requests_after_freeze':model_times_ok,'requests_within_authorization':authorized,
        'model_responses_before_seal':all(not o['response_retrieved_at_utc'] or cloud.native.aware(o['response_retrieved_at_utc'])<=cloud.native.aware(forecast['sealed_at_utc']) for o in direct_and_groups),
        'news_supported_and_pre_cutoff':all(f['verbatim_supported'] and f['timestamps_eligible'] for f in findings),
        'statistical_feature_clocks_eligible':bool(statistical_clocks_ok),'injury_issue_creation_capture_eligible':injury_clocks_ok,
        'native_schema_and_wire_isolation':True,'primary_pair_eligible':forecast['live_evaluation_eligible'],
        'all_three_methods_successful':all(m['status']=='success' for m in methods.values())}
    return {'schema_version':1,'game_id':game['game_id'],'game':{k:game[k] for k in
        ('home_name','away_name','recorded_start_utc','season_year','season_type','neutral_site')},
        'mode':job['mode'],'cohort':state.config['cohort'],'packet_sha256':frozen['packet_sha256'],
        'private_replay':proof,'checks':checks,'stages':stage_rows,'capture_clocks':stages,
        'cutoff_utc':cloud.iso(w['target']),'freeze_deadline_utc':cloud.iso(w['freeze']),'forecast_deadline_utc':cloud.iso(w['forecast']),
        'frozen_at_utc':frozen['frozen_at_utc'],'inference_started_at_utc':run['started_at_utc'],'sealed_at_utc':forecast['sealed_at_utc'],
        'source_retrieval_min_utc':min(r['retrieved_at_utc'] for r in retrievals),'source_retrieval_max_utc':max(r['retrieved_at_utc'] for r in retrievals),
        'source_metadata':source_rows,'source_freshness':lineage['freshness'],'statistical_lineage':lineage['statistics'],
        'statistics':{side:{k:v for k,v in packet[side].items() if k!='regular_season_scoring'} for side in ('home','away')},
        'scoring_summaries':{side:{k:v for k,v in packet[side].get('regular_season_scoring',{}).items() if k!='per_game'} for side in ('home','away')},
        'injury':injury,'news':{'state':packet['injury_news']['news']['state'],'missing_reason':packet['injury_news']['news']['missing_reason'],
            'queries':[r['query'] for r in acquisition['raw_search_results']],
            'result_count':sum(len(r['results']) for r in acquisition['raw_search_results']),
            'page_validation':acquisition['sources_and_validation'],'decisions':acquisition['decisions'],
            'finding_decisions':extraction['audit']['finding_decisions'],'findings':findings},
        'methods':methods,'market':market,'costs':{'reservations_usd':sum(r['usd'] for r in claims),
            'claims_by_kind':dict(Counter(r['kind'] for r in claims)),'forecast_tokens':tokens,'extraction_tokens':extraction_tokens,
            'forecast_configured_rate_estimate_usd':forecast_cost,'extraction_configured_rate_estimate_usd':extraction_cost,
            'search_configured_rate_estimate_usd':search_count*research_config['prices']['query_usd'],
            'combined_configured_rate_estimate_usd':known_estimate,'provider_invoice_known':False,
            'all_anthropic_reported_token_estimate_at_1_5_usd_per_million':(tokens['input_tokens']+extraction_tokens['input_tokens']+5*(tokens['output_tokens']+extraction_tokens['output_tokens']))/1e6},
        'resources':cloud.resources(state,key),'provider_calls':provider_calls,'circuits':circuits,
        'raw_provider_responses_included':False,'outcome_verified':False,'brier_score':None,'log_loss':None}


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--game-id',default='401909877');parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();cloud.check_assets()
    objects=S3Objects(os.environ.get('NBA_ACTIONS_BUCKET'),settings()['storage_prefix'],os.environ.get('AWS_REGION'),os.environ.get('NBA_ACTIONS_ENDPOINT'))
    raw,_=objects.read('root.json');root=json.loads(raw or b'{}')
    if root.get('store_uuid')!=os.environ.get('NBA_ACTIONS_STORE_UUID'):raise ValueError('Private store identity mismatch')
    cp=Checkpoints(objects);cp.root=root
    with tempfile.TemporaryDirectory(prefix='nba-private-pilot-audit-') as tmp:
        cp.restore(Path(tmp)/'state');state=ReadOnlyState(Path(tmp)/'state',read_json(cloud.CONFIG))
        keys=[key for key in state.jobs() if state.job(key)['game']['game_id']==args.game_id]
        if len(keys)!=1:raise ValueError('A unique saved pilot is required')
        # Disallow every HTTP transport during source replay and response parsing.
        from unittest.mock import patch
        with patch('urllib.request.OpenerDirector.open',side_effect=AssertionError('Audit cannot retrieve sources or call models')):
            result=audit(state,keys[0])
        result['r2_checkpoint_sha256']=root['snapshot'];result['r2_owner_present']=root.get('owner') is not None
    result=sanitized(result,os.environ)
    # Page validation excerpts and raw acquisition text stay private. Publish only
    # the parser's decisions and timestamp metadata, not article/source bodies.
    result['news']['page_validation']=[{k:p.get(k) for k in ('source_id','url','usable','reason','published_at_utc','retrieved_at_utc','body_sha256')} for p in result['news']['page_validation']]
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_bytes(canonical(result)+b'\n')
    print(json.dumps({'game_id':result['game_id'],'checks':result['checks'],'packet_sha256':result['packet_sha256'],'raw_provider_responses_included':False},indent=2))


if __name__=='__main__':main()
