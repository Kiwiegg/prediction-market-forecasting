"""Explicit, audited recovery administration. Never supplies provider credentials."""
import json
from pathlib import Path

import actions_campaign as campaign
import cloud_prospective as cloud
from actions_storage import Checkpoints,StorageStop
from audit_blocked_campaign import inspect,termination_proof,FAILED_RUN
from cloud_state import durable_json
from evidence_documents import canonical,digest,DocumentStore
from news_denial_policy import POLICY,AUTHORIZATION,ordinary_403


def preconditions(state,report):
    if (report['paid_claim_count']!=17 or abs(report['reserved_usd']-.282501)>1e-12
            or any(r['attempt_state']!='saved_http_response' or r['http_status']!=200 for r in report['claims'])):
        raise ValueError('Paid claims require fresh operator accounting review')
    if not all(j['disposition'] in ('preserved_completed','unrecoverable_expired_no_backfill') for j in report['jobs']):
        raise ValueError('Active partial game requires separate review')
    if not any(j['private_replay']['forecasts'] for j in report['jobs']):raise ValueError('Prior successful forecasts not verified')
    circuits={r['id']:json.loads(r['body']) for r in report['circuits']}
    if set(circuits)!={'host:apnews.com','network','paid'}:raise ValueError('Unexpected denial journals')
    url=circuits['host:apnews.com']['url']
    if any(r.get('http_status')!=403 or r.get('url')!=url for r in circuits.values()):raise ValueError('Denials are not one publisher HTTP403')
    if any(circuits[k].get('reason')!='source_access_denial' or 'provider' in circuits[k] for k in ('network','paid')):
        raise ValueError('Provider/account denial cannot be exempted')
    captures=[]
    for p in state.root.glob('jobs/*/news/raw/*.json'):
        m=json.loads(p.read_text())
        if m.get('url')==url:
            meta,body=DocumentStore(p.parent,True,lambda u:u==url).get(url)
            if not ordinary_403(meta,body):raise ValueError('Article denial is ambiguous/account restricted')
            captures.append(meta['body_sha256'])
    if len(captures)!=1:raise ValueError('Exactly one saved denied article required')
    return {'source_denial_url':url,'source_denial_body_sha256':captures[0]}


def release(objects,uuid,destination,proof,expected_audit_sha,confirm=False):
    if not confirm:raise ValueError('Explicit reviewed exact-owner release required')
    report=inspect(objects,uuid,destination,proof)
    if digest(canonical(report))!=expected_audit_sha:raise ValueError('Audit changed; no recovery mutation permitted')
    from audit_live_pilot import ReadOnlyState
    state=ReadOnlyState(destination,json.loads(cloud.CONFIG.read_text()));preconditions(state,report)
    raw,_=objects.read('root.json');root=json.loads(raw)
    if root['snapshot']!=report['snapshot_sha256'] or digest(canonical(root.get('owner')))!=report['owner_sha256']:
        raise StorageStop('Owner/checkpoint changed before release')
    termination_proof(proof)
    # Preserve a durable attestation before using the existing exact-owner CAS.
    objects.write('recovery_audits/'+expected_audit_sha,canonical(report),create=True)
    from actions_prospective import recover_owner
    recover_owner(objects,uuid,json.dumps(root['owner']),'CONFIRMED_OLD_RUNNER_TERMINATED',report['snapshot_sha256'])
    after=json.loads(objects.read('root.json')[0])
    if after['owner'] is not None or after['snapshot']!=report['snapshot_sha256']:raise StorageStop('Post-release root differs')
    return {'owner_released':True,'circuits_cleared':False,'audit_sha256':expected_audit_sha,
            'snapshot_preserved':True,'reserved_usd':report['reserved_usd'],'paid_calls':0,'policy_adopted':False}


def adopt(state,objects,audit_sha,expected_predecessor,confirm=False):
    if not confirm:raise ValueError('Explicit prospective article-policy approval required')
    raw,_=objects.read('recovery_audits/'+audit_sha)
    if raw is None or digest(raw)!=audit_sha:raise ValueError('Audited exact-owner release attestation missing')
    report=json.loads(raw);preconditions(state,report)
    with state.checkpoints.lock:
        old=state.campaign_history()
        if digest(canonical(old))!=expected_predecessor:raise ValueError('Campaign predecessor changed')
        if not cloud.native.aware(old['authorized_at_utc'])<=state.clock()<cloud.native.aware(old['expires_at_utc']):
            raise ValueError('Existing campaign expired; separately renew first')
        with state.db() as c:
            ledger=[dict(r) for r in c.execute('SELECT * FROM requests ORDER BY id')]
            circuits=[dict(r) for r in c.execute('SELECT * FROM circuits ORDER BY id')]
        if digest(canonical(ledger))!=report['request_ledger_sha256'] or digest(canonical(circuits))!=report['circuits_sha256']:
            raise ValueError('Ledger/denials changed; no policy adoption')
        value={**old,'previous_sha256':digest(canonical(old)),'transition_kind':'recovery_policy',
            'authorized_at_utc':cloud.iso(state.clock()),'assets_sha256':digest(campaign.REGISTRY.read_bytes()),
            'renewal_protocol':None,'operational_migration':campaign.renewal_migration(old['assets_sha256']),
            'recovery_policy_sha256':digest(POLICY.read_bytes()),'recovery_audit_sha256':audit_sha}
        number=len(list((state.root/'campaign_amendments').glob('*.json')))+1
        durable_json(state.root/'campaign_amendments'/('%04d.json'%number),value)
        durable_json(state.root/AUTHORIZATION,{'store_uuid':state.uuid,'policy_sha256':digest(POLICY.read_bytes()),
            'approval_sha256':digest(canonical(value)),'audit_sha256':audit_sha,'effective_after_utc':cloud.iso(state.clock()),
            'circuit_sha256':{r['id']:digest(r['body'].encode()) for r in circuits if r['id'] in ('network','paid')},
            'excluded_interrupted_games':[j['game_id'] for j in report['jobs'] if not j['private_replay']['forecasts']]})
        durable_json(state.root/'recovery_dispositions'/(audit_sha+'.json'),{'jobs':report['jobs'],
            'note':'Expired incomplete jobs remain excluded; no old stage/cache/claim was altered.'})
        state.sync();return state.campaign()
