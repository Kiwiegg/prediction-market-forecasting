"""Offline, append-only prospective reporting. Never fetches outcomes or evidence."""
import argparse
import json
import math
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from evidence_documents import canonical, digest
from evaluate_forecasts import brier, calibration, log_loss
from forecast_split import immutable_json

ROOT = Path(__file__).resolve().parents[1]
PROTOCOL = ROOT / 'reports/final_research/update_protocol.json'
METHODS = ('direct', 'leap_v1_raw', 'leap_v1_conservative', 'leap_v2_raw', 'leap_v2_conservative', 'kalshi', 'constant_50')


def clock(value):
    t = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if t.tzinfo is None: raise ValueError('Timezone-aware clock required')
    return t.timestamp()


def protocol(): return json.loads(PROTOCOL.read_text())


def summarize_audit(a, amendment=None):
    """Project the existing private auditor's output, without publishing source bodies."""
    required = ('private_replay', 'primary_pair_eligible', 'same_packet_all_methods',
                'source_retrievals_by_cutoff', 'packet_frozen_by_deadline', 'forecasts_sealed_by_deadline',
                'native_schema_and_wire_isolation', 'statistical_feature_clocks_eligible',
                'injury_issue_creation_capture_eligible', 'news_supported_and_pre_cutoff')
    ok = a['mode'] == 'live_explicit_opt_in' and a['private_replay']['verified'] and all(a['checks'][k] for k in required)
    before = max(clock(a[k]) for k in ('cutoff_utc', 'frozen_at_utc', 'sealed_at_utc')) < clock(protocol()['capture_cutoff_exclusive_utc'])
    ps = {}
    for method in a['methods'].values():
        if method['parent_hash'] != a['packet_sha256']: raise ValueError('Parent evidence hash differs')
        if method['status'] == 'success': ps.update(method['probabilities'])
    ps['leap_v1_raw'] = ps.pop('leap_raw', None)
    ps['leap_v1_conservative'] = ps.pop('leap_conservative', None)
    ps['kalshi'] = a['market']['midpoint'] if a['market']['eligible'] else None
    ps['constant_50'] = .5
    for p in ps.values():
        if p is not None and (isinstance(p, bool) or not math.isfinite(p) or not 0 <= p <= 1): raise ValueError('Invalid probability')
    primary = ok and before and all(ps.get(k) is not None for k in ('direct', 'leap_v2_raw'))
    return {'game_id': a['game_id'], 'game': a['game'], 'cohort': a['cohort'],
            'operational_amendment': amendment, 'cutoff_utc': a['cutoff_utc'],
            'frozen_at_utc': a['frozen_at_utc'], 'sealed_at_utc': a['sealed_at_utc'],
            'packet_sha256': a['packet_sha256'], 'private_replay_verified': a['private_replay']['verified'],
            'primary_eligible': primary, 'exclusion_reason': None if primary else ('after_reporting_cutoff' if not before else 'failed_existing_eligibility_or_primary_pair'),
            'probabilities': {m: ps.get(m) for m in METHODS}, 'outcome': None, 'outcome_verification': None,
            'source_audit_sha256': digest(canonical(a))}


def join_outcome(row, folder):
    # Reuse the original captured-byte parser; no live API path is called.
    from prospective_evaluate import verify_source_capture
    result = verify_source_capture(folder, 'outcome')
    game = result['game']
    if result['game_id'] != row['game_id']: raise ValueError('Outcome game identity mismatch')
    for k in ('home_name', 'away_name', 'recorded_start_utc', 'season_year', 'season_type', 'neutral_site'):
        if game.get(k) != row['game'].get(k): raise ValueError('Outcome fixture/schedule mismatch')
    if clock(result['retrieved_at_utc']) <= clock(row['sealed_at_utc']): raise ValueError('Outcome predates forecast seal')
    if clock(result['retrieved_at_utc']) > datetime.now(timezone.utc).timestamp(): raise ValueError('Future outcome retrieval')
    row = {**row, 'outcome_verification': {'capture_manifest_sha256': digest((Path(folder)/'manifest.json').read_bytes()),
           'retrieved_at_utc': result['retrieved_at_utc'], 'source_replayed': True, 'reason': result['reason']}}
    if result['eligible']:
        if type(result['outcome']) is not int or result['outcome'] not in (0, 1): raise ValueError('Invalid binary result')
        row['outcome'] = result['outcome']
    else:
        row.update(primary_eligible=False, exclusion_reason=result['reason'])
    return row


def score_rows(rows):
    """Separate amendment strata; missing Kalshi/v1 never remove a primary pair."""
    cohorts = {}
    for row in rows:
        key = row.get('cohort', 'unknown') + '/' + (row.get('operational_amendment') or 'original_policy')
        cohorts.setdefault(key, []).append(row)
    out = {}
    for key, group in sorted(cohorts.items()):
        eligible = [r for r in group if r['primary_eligible']]
        complete = [r for r in eligible if r['outcome'] is not None]
        sets = {'primary': ('direct', 'leap_v2_raw'), 'market': ('direct', 'leap_v2_raw', 'leap_v2_conservative', 'kalshi', 'constant_50'), 'seven_method': METHODS}
        scores = {}
        for name, methods in sets.items():
            paired = [r for r in complete if all(r['probabilities'].get(m) is not None for m in methods)]
            scores[name] = {'n': len(paired), 'game_ids': [r['game_id'] for r in paired], 'methods': {}}
            for m in methods:
                ps, ys = [r['probabilities'][m] for r in paired], [r['outcome'] for r in paired]
                scores[name]['methods'][m] = {'brier_score': sum(brier(p,y) for p,y in zip(ps,ys))/len(ps) if ps else None,
                    'log_loss': sum(log_loss(p,y) for p,y in zip(ps,ys))/len(ps) if ps else None,
                    'calibration': calibration([{'p':p,'outcome':y} for p,y in zip(ps,ys)],'p')}
            if name == 'primary':
                v = scores[name]['methods']
                scores[name]['v2_minus_direct_brier'] = v['leap_v2_raw']['brier_score']-v['direct']['brier_score'] if paired else None
        out[key] = {'enrolled': len(group), 'primary_eligible_captures': len(eligible), 'pending_outcomes': len(eligible)-len(complete), 'comparisons': scores}
    return out


def verify_bundle(folder):
    folder = Path(folder); manifest = json.loads((folder/'manifest.json').read_text())
    for name, sha in manifest.items():
        p = (folder/name).resolve()
        if folder.resolve() not in p.parents or digest(p.read_bytes()) != sha: raise ValueError('Update artifact integrity mismatch')
    if set(manifest) != {'observations.json', 'summary.json'}: raise ValueError('Incomplete reporting bundle')
    obs = json.loads((folder/'observations.json').read_text())
    if obs['protocol_sha256'] != digest(PROTOCOL.read_bytes()): raise ValueError('Reporting protocol changed')
    validate_rows(obs['rows'])
    if score_rows(obs['rows']) != json.loads((folder/'summary.json').read_text()): raise ValueError('Scores do not replay')
    return obs


def validate_rows(rows):
    if len({r['game_id'] for r in rows}) != len(rows): raise ValueError('Duplicate game IDs')
    for r in rows:
        for p in r['probabilities'].values():
            if p is not None and (isinstance(p,bool) or not math.isfinite(p) or not 0<=p<=1): raise ValueError('Invalid probability')
        if r['outcome'] is not None:
            if type(r['outcome']) is not int or r['outcome'] not in (0,1) or not r['outcome_verification'] or not r['outcome_verification']['source_replayed']:
                raise ValueError('Unverified outcome')
        if r['primary_eligible']:
            t=clock(r['cutoff_utc']);f=clock(r['frozen_at_utc']);s=clock(r['sealed_at_utc']);tip=clock(r['game']['recorded_start_utc'])
            if (t!=tip-86400 or not t<=f<=t+300 or not f<=s<=t+900 or s>=tip
                    or max(t,f,s)>=clock(protocol()['capture_cutoff_exclusive_utc'])
                    or not r['private_replay_verified'] or any(r['probabilities'].get(m) is None for m in ('direct','leap_v2_raw'))):
                raise ValueError('Ineligible capture cannot enter primary scoring')
        elif not r.get('exclusion_reason'): raise ValueError('Missing exclusion reason')


def save_bundle(rows, output, previous=None):
    validate_rows(rows)
    rows = sorted(rows, key=lambda r: (r.get('cutoff_utc') or '', r['game_id']))
    prior_hash = None
    if previous:
        prior = verify_bundle(previous); prior_hash = digest((Path(previous)/'manifest.json').read_bytes())
        new = {r['game_id']: r for r in rows}
        for old in prior['rows']:
            if old['game_id'] not in new: raise ValueError('Previously enrolled game removed')
            current = new[old['game_id']]
            # A fresh read-only audit also describes current campaign circuits
            # and checkpoint metadata. Its attestation hash can change without
            # changing any immutable per-game evidence or forecast field.
            stable = set(old)-{'outcome','outcome_verification','primary_eligible','exclusion_reason','game','source_audit_sha256'}
            if any(current[k] != old[k] for k in stable): raise ValueError('Prior forecast/capture changed')
            if any(current['game'].get(k)!=v for k,v in old['game'].items()): raise ValueError('Prior game identity changed')
            if old['outcome'] is not None and (current['outcome'] != old['outcome'] or current['outcome_verification'] != old['outcome_verification']): raise ValueError('Verified outcome changed')
            if not old['primary_eligible'] and current['primary_eligible']: raise ValueError('Failed capture cannot be rescued')
            if old['primary_eligible'] and not current['primary_eligible'] and not current['outcome_verification']:
                raise ValueError('Capture exclusion requires verified outcome disposition')
    output = Path(output); output.mkdir(parents=True, exist_ok=False)
    immutable_json(output/'observations.json', {'protocol_sha256': digest(PROTOCOL.read_bytes()), 'capture_cutoff_exclusive_utc': protocol()['capture_cutoff_exclusive_utc'],
        'previous_manifest_sha256': prior_hash, 'rows': rows})
    immutable_json(output/'summary.json', score_rows(rows))
    immutable_json(output/'manifest.json', {name: digest((output/name).read_bytes()) for name in ('observations.json','summary.json')})
    return verify_bundle(output)


def collect(state_root, outcomes=None):
    from audit_live_pilot import ReadOnlyState, audit
    import cloud_prospective as cloud
    state = ReadOnlyState(state_root, json.loads(cloud.CONFIG.read_text())); rows=[]
    # This is an offline reporting tool: any attempted source/model access fails.
    from unittest.mock import patch
    with patch('urllib.request.OpenerDirector.open', side_effect=AssertionError('Offline report cannot access network')):
        for key in state.jobs():
            job=state.job(key); game=job['game']; proof=cloud.replay_job(state,key)
            application=state.root/'news_policy_applications'/(key+'.json')
            amendment='prospective_news_denial_v1' if application.exists() else None
            with state.db() as c: stage=c.execute('SELECT status FROM stages WHERE job=? AND name=?',(key,'forecast')).fetchone()
            if stage and stage['status']=='done':
                row=summarize_audit(audit(state,key),amendment)
                if outcomes and (Path(outcomes)/game['game_id']).exists(): row=join_outcome(row,Path(outcomes)/game['game_id'])
            else:
                row={'game_id':game['game_id'],'game':game,'cohort':state.config['cohort'],'operational_amendment':amendment,
                     'cutoff_utc':cloud.iso(cloud.windows(game,state.config)['target']),'primary_eligible':False,
                     'exclusion_reason':'no_sealed_forecast_no_backfill','private_replay_verified':proof['verified'],
                     'probabilities':{m:None for m in METHODS},'outcome':None,'outcome_verification':None}
            rows.append(row)
    return rows


def saved_inventory():
    """Published, privately replayed historical failure audit; no new observation."""
    from replay_live_pilot_summary import verify
    source=ROOT/'reports/prospective_live_pilot_1';verify(source)
    pilot=summarize_audit(json.loads((source/'audit.json').read_text()))
    report=ROOT/'reports/prospective_news_recovery_v1/audit.json'
    audit=json.loads(report.read_text());rows=[pilot]
    for j in audit['jobs']:
        if j['game_id']==pilot['game_id']:continue
        if j['disposition']!='unrecoverable_expired_no_backfill' or not j['private_replay']['verified']:raise ValueError('Unverified saved exclusion')
        rows.append({'game_id':j['game_id'],'game':{'home_name':j['home'],'away_name':j['away'],'recorded_start_utc':j['tipoff_utc']},
            'cohort':pilot['cohort'],'operational_amendment':None,'cutoff_utc':j['target_cutoff_utc'],
            'primary_eligible':False,'exclusion_reason':'no_sealed_forecast_no_backfill','private_replay_verified':True,
            'probabilities':{m:None for m in METHODS},'outcome':None,'outcome_verification':None})
    return rows


def collect_r2(outcomes=None):
    """Storage GET only, idle checkpoint required; never take or release an owner."""
    from actions_storage import Checkpoints,S3Objects
    from actions_campaign import settings
    from inspect_actions_storage import sanitized
    objects=S3Objects(os.environ.get('NBA_ACTIONS_BUCKET'),settings()['storage_prefix'],os.environ.get('AWS_REGION'),os.environ.get('NBA_ACTIONS_ENDPOINT'))
    raw,_=objects.read('root.json');root=json.loads(raw or b'{}')
    if not os.environ.get('NBA_ACTIONS_STORE_UUID') or root.get('store_uuid')!=os.environ['NBA_ACTIONS_STORE_UUID'] or root.get('owner') is not None:
        raise ValueError('Original idle R2 store required; never clear an owner for reporting')
    cp=Checkpoints(objects,root['store_uuid']);cp.root=root
    with tempfile.TemporaryDirectory(prefix='nba-report-readonly-') as t:
        destination=Path(t)/'state';cp.restore(destination);rows=collect(destination,outcomes)
        if any(digest((destination/n).read_bytes())!=h for n,h in cp.files.items()):raise ValueError('Private capture changed')
    if objects.read('root.json')[0]!=raw:raise ValueError('Checkpoint changed during report inspection')
    return sanitized(rows,os.environ)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--private-state',type=Path);p.add_argument('--outcomes',type=Path)
    p.add_argument('--r2',action='store_true',help='GET-only restore with protected storage credentials; no publisher/provider calls')
    p.add_argument('--previous',type=Path);p.add_argument('--output',type=Path);p.add_argument('--verify',type=Path)
    p.add_argument('--pilot-only',action='store_true',help='Seed public snapshot; original pilot remains unscored')
    p.add_argument('--saved-inventory',action='store_true',help='Existing published pilot plus all six preserved unsuccessful jobs')
    a=p.parse_args()
    if a.verify:
        result=verify_bundle(a.verify)
    elif a.r2 and a.output and not a.private_state and not a.pilot_only and not a.saved_inventory:
        result=save_bundle(collect_r2(a.outcomes),a.output,a.previous)
    elif a.output and a.saved_inventory and not a.private_state and not a.outcomes and not a.pilot_only:
        from build_final_research import verify_sources
        verify_sources();result=save_bundle(saved_inventory(),a.output,a.previous)
    elif a.output and a.pilot_only and not a.private_state and not a.outcomes:
        from replay_live_pilot_summary import verify
        source=ROOT/'reports/prospective_live_pilot_1';verify(source)
        result=save_bundle([summarize_audit(json.loads((source/'audit.json').read_text()))],a.output,a.previous)
    elif a.output and a.private_state and not a.pilot_only:
        result=save_bundle(collect(a.private_state,a.outcomes),a.output,a.previous)
    else:p.error('Use --verify, --pilot-only --output, or --private-state --output [--outcomes]; all operations are offline')
    print(json.dumps({'verified':True,'rows':len(result['rows']),'network_calls':0}))


if __name__=='__main__':main()
