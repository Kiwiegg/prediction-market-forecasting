"""Versioned cloud-news enrollment and shared campaign cap; no scoring imports."""
import json
import math
from pathlib import Path

import cloud_prospective as cloud
from actions_storage import RemoteState, StorageStop
from cloud_state import durable_json
from evidence_documents import canonical, digest

CONFIG=cloud.ROOT/'examples/prospective_github_actions_v1.json'
REGISTRY=cloud.ROOT/'experiments/prospective_github_actions_v1_assets.json'
RENEWAL=cloud.ROOT/'experiments/prospective_campaign_renewal_v1.json'


def renewal_migration():
    """One reviewed operational transition; frozen evidence/config stays identical."""
    policy=json.loads(RENEWAL.read_text())
    source=(cloud.ROOT/policy['source_registry_path']).read_bytes()
    if digest(source)!=policy['source_registry_sha256']:raise ValueError('Archived operational registry corrupt')
    before=json.loads(source);after=json.loads(REGISTRY.read_text())
    changed={name for name in before.keys() & after.keys() if before[name]!=after[name]}
    added=after.keys()-before.keys()
    if before.keys()-after.keys() or not changed<=set(policy['allowed_changed_assets']) or set(added)!=set(policy['allowed_added_assets']):
        raise ValueError('Operational migration exceeds reviewed file allowlist')
    # These two unchanged manifests bind budgets, all evidence and frozen methods.
    for name in ('examples/prospective_github_actions_v1.json','experiments/prospective_cloud_news_v1_assets.json'):
        if before[name]!=after[name] or digest((cloud.ROOT/name).read_bytes())!=before[name]:
            raise ValueError('Renewal cannot change evidence, methods or budget configuration')
    return {'protocol':policy['protocol'],'policy_sha256':digest(RENEWAL.read_bytes()),
            'from_assets_sha256':digest(source),'to_assets_sha256':digest(REGISTRY.read_bytes())}


def settings():
    cfg=json.loads(CONFIG.read_text())
    if cfg['campaign_ceiling_usd']!=50 or cfg['per_game_ceiling_usd']!=1.35 or cfg['automatic_enrollment_enabled'] is not False:
        raise ValueError('Commit a versioned protocol to change ceilings/activation defaults')
    return cfg


def verify_assets(committed=False):
    cloud.check_assets(committed)
    assets=json.loads(REGISTRY.read_text())
    for name,sha in assets.items():
        if digest((cloud.ROOT/name).read_bytes())!=sha:raise ValueError('Actions asset changed: '+name)
        if committed:
            import subprocess
            if subprocess.check_output(['git','show','HEAD:'+name],cwd=cloud.ROOT)!=(cloud.ROOT/name).read_bytes():
                raise ValueError('Commit Actions assets before network activation')
    if committed:
        import subprocess
        if subprocess.check_output(['git','show','HEAD:'+str(REGISTRY.relative_to(cloud.ROOT))],cwd=cloud.ROOT)!=REGISTRY.read_bytes():raise ValueError('Commit Actions asset registry')
    renewal_migration()
    return digest(REGISTRY.read_bytes())


class CampaignState(RemoteState):
    def enroll(self,game,auth):
        with self.checkpoints.lock:
            approval=self.campaign()
            if not approval['automatic_enrollment'] and game['game_id'] not in approval['game_ids']:raise ValueError('Campaign game not authorized')
            existing=[self.job(k)['game']['game_id'] for k in self.jobs()]
            if game['game_id'] not in existing and len(existing)>=approval['max_games']:raise ValueError('Campaign game cap reached')
            if self.authorization(auth)['mode']!=approval['mode']:raise ValueError('Campaign/job mode mismatch')
            return super().enroll(game,auth)

    def campaign_history(self):
        """Validate history without granting permission to spend under an old expiry."""
        path=self.root/'campaign.json'
        if not path.is_file():raise ValueError('Campaign authorization missing; worker remains disabled')
        approval=json.loads(path.read_text());self._validate_approval(approval)
        migration=renewal_migration();known={migration['from_assets_sha256'],migration['to_assets_sha256']}
        if approval['assets_sha256'] not in known:raise ValueError('Unapproved historical operational registry')
        for number,amendment in enumerate(sorted((self.root/'campaign_amendments').glob('*.json')),1):
            if amendment.name!='%04d.json'%number:raise ValueError('Noncontiguous campaign amendment chain')
            newer=json.loads(amendment.read_text())
            if newer.get('previous_sha256')!=digest(canonical(approval)):raise ValueError('Campaign amendment chain broken')
            self._validate_approval(newer)
            if newer['assets_sha256'] not in known:raise ValueError('Unapproved amended operational registry')
            if cloud.native.aware(newer['authorized_at_utc'])<cloud.native.aware(approval['authorized_at_utc']) or newer['mode']!=approval['mode']:
                raise ValueError('Invalid campaign amendment chronology/mode')
            if newer.get('transition_kind')=='renewal':
                scope=('game_ids','max_games','max_usd','per_game_usd','automatic_enrollment')
                if any(newer[k]!=approval[k] for k in scope):raise ValueError('Renewal cannot expand campaign scope or budget')
                if newer.get('renewal_protocol')!=migration['protocol'] or cloud.native.aware(newer['expires_at_utc'])<=cloud.native.aware(approval['expires_at_utc']):
                    raise ValueError('Invalid renewal protocol/expiry')
                expected=migration if newer['assets_sha256']!=approval['assets_sha256'] else None
                if newer.get('operational_migration')!=expected:raise ValueError('Operational migration proof mismatch')
                if expected and (approval['assets_sha256']!=expected['from_assets_sha256'] or newer['assets_sha256']!=expected['to_assets_sha256']):
                    raise ValueError('Unauthorized registry migration direction')
            else:
                if newer.get('transition_kind') not in (None,'expansion') or newer['assets_sha256']!=approval['assets_sha256']:
                    raise ValueError('Registry transition requires explicit renewal')
                if newer['max_games']<=approval['max_games'] or newer['max_usd']<approval['max_usd']:
                    raise ValueError('Expansion cannot reset campaign scope/budget')
            approval=newer
        return approval

    def _validate_approval(self,approval):
        cfg=settings()
        expected={'version':1,'campaign_id':cfg['campaign_id'],'store_uuid':self.uuid,
                  'config_sha256':digest(CONFIG.read_bytes())}
        if any(approval.get(k)!=v for k,v in expected.items()):raise ValueError('Campaign/store/protocol authorization mismatch')
        start,end=(cloud.native.aware(approval[k]) for k in ('authorized_at_utc','expires_at_utc'))
        if not 0<end-start<=cfg['authorization_max_days']*86400:raise ValueError('Invalid campaign authorization interval')
        if (not math.isfinite(approval['max_usd']) or not 0<approval['max_usd']<=cfg['campaign_ceiling_usd']
                or type(approval['max_games']) is not int or not 1<=approval['max_games']<=cfg['maximum_game_cap']
                or approval['per_game_usd']!=cfg['per_game_ceiling_usd']
                or type(approval['automatic_enrollment']) is not bool):raise ValueError('Invalid campaign limits')
        ids=approval['game_ids']
        if not isinstance(ids,list) or any(not isinstance(g,str) for g in ids) or sorted(set(ids))!=ids or set(ids)&set(self.config['excluded_game_ids']):
            raise ValueError('Invalid campaign allowlist')
        if not approval['automatic_enrollment'] and len(ids)<approval['max_games']:raise ValueError('Campaign allowlist incomplete')
        if approval['mode'] not in ('live_explicit_opt_in','offline_mock'):raise ValueError('Invalid campaign mode')

    def campaign(self):
        approval=self.campaign_history()
        if approval['assets_sha256']!=digest(REGISTRY.read_bytes()):raise ValueError('Explicit operational authorization migration required')
        if not cloud.native.aware(approval['authorized_at_utc'])<=self.clock()<=cloud.native.aware(approval['expires_at_utc']):
            raise ValueError('Campaign authorization expired/not yet valid')
        return approval

    def renewal_plan(self):
        old=self.campaign_history();migration=renewal_migration()
        with self.db() as c:
            rows=[dict(r) for r in c.execute('SELECT * FROM requests ORDER BY id')]
            circuits=[dict(r) for r in c.execute('SELECT * FROM circuits ORDER BY id')]
        return {'status':'renewal_plan_only_no_authorization','predecessor_sha256':digest(canonical(old)),
                'expires_at_utc':old['expires_at_utc'],'expired':self.clock()>cloud.native.aware(old['expires_at_utc']),
                'max_games':old['max_games'],'max_usd':old['max_usd'],'per_game_usd':old['per_game_usd'],
                'game_ids':old['game_ids'],'automatic_enrollment':old['automatic_enrollment'],
                'migration_required':old['assets_sha256']!=migration['to_assets_sha256'],
                'source_assets_sha256':old['assets_sha256'],'target_assets_sha256':migration['to_assets_sha256'],
                'request_count':len(rows),'reserved_usd':sum(r['usd'] for r in rows),
                'request_ledger_sha256':digest(canonical(rows)),'denial_journal_sha256':digest(canonical(circuits)),
                'denial_count':len(circuits),'paid_calls':0}

    def renew(self,expires,expected_predecessor,confirm=False,accept_migration=False):
        if not confirm:raise ValueError('Explicit campaign renewal approval required')
        with self.checkpoints.lock:
            old=self.campaign_history()
            if expected_predecessor!=digest(canonical(old)):raise ValueError('Renewal predecessor differs; inspect fresh state')
            if cloud.native.aware(old['authorized_at_utc'])>self.clock():raise ValueError('Cannot renew a future authorization')
            end=cloud.native.aware(expires)
            if not max(self.clock(),cloud.native.aware(old['expires_at_utc']))<end<=self.clock()+settings()['authorization_max_days']*86400:
                raise ValueError('Renewal requires a new bounded future expiry')
            migration=renewal_migration();changing=old['assets_sha256']!=migration['to_assets_sha256']
            if changing and not accept_migration:raise ValueError('Explicit operational migration approval required')
            value={**old,'previous_sha256':digest(canonical(old)),'transition_kind':'renewal',
                   'renewal_protocol':migration['protocol'],'operational_migration':migration if changing else None,
                   'authorized_at_utc':cloud.iso(self.clock()),'expires_at_utc':cloud.iso(end),
                   'assets_sha256':migration['to_assets_sha256']}
            number=len(list((self.root/'campaign_amendments').glob('*.json')))+1
            durable_json(self.root/'campaign_amendments'/('%04d.json'%number),value);self.sync()
            return self.campaign()

    def expand(self,expires,max_games,max_usd,automatic=False,game_ids=()):
        old=self.campaign()
        if not self.first_success():raise ValueError('Genuine first live primary pair required before expansion')
        if not old['max_games']<max_games<=100 or not old['max_usd']<=max_usd<=50:raise ValueError('Expansion cannot reset/exceed campaign budget')
        end=cloud.native.aware(expires)
        if not self.clock()<end<=self.clock()+settings()['authorization_max_days']*86400:raise ValueError('Invalid expiry')
        if not automatic and len(set(game_ids))<max_games:raise ValueError('Explicit complete allowlist or automatic authorization required')
        value={**old,'previous_sha256':digest(canonical(old)),'authorized_at_utc':cloud.iso(self.clock()),
               'expires_at_utc':cloud.iso(end),'max_games':max_games,'max_usd':max_usd,
               'game_ids':sorted(set(game_ids)),'automatic_enrollment':automatic,
               'transition_kind':'expansion','renewal_protocol':None,'operational_migration':None}
        number=len(list((self.root/'campaign_amendments').glob('*.json')))+1
        durable_json(self.root/'campaign_amendments'/('%04d.json'%number),value);self.sync();return self.campaign()

    def approve(self, game_ids, expires, max_games=1, max_usd=50, automatic=False, mock=False):
        cfg=settings();now=self.clock();end=cloud.native.aware(expires)
        if not math.isfinite(max_usd) or not 0<max_usd<=50 or type(max_games) is not int or not 1<=max_games<=100:
            raise ValueError('Campaign limits exceeded')
        if not now<end<=now+cfg['authorization_max_days']*86400:raise ValueError('Bounded future authorization expiry required')
        if not automatic and (len(set(game_ids))!=max_games or not game_ids):raise ValueError('Explicit IDs required for pilot')
        if automatic or max_games>1:
            if not self.first_success():raise ValueError('Automatic/multi-game collection disabled until genuine live primary pair succeeds')
        if set(game_ids)&set(self.config['excluded_game_ids']):raise ValueError('Legacy missed attempt is protected')
        body={'version':1,'campaign_id':cfg['campaign_id'],'store_uuid':self.uuid,
              'config_sha256':digest(CONFIG.read_bytes()),'assets_sha256':digest(REGISTRY.read_bytes()),
              'authorized_at_utc':cloud.iso(now),'expires_at_utc':cloud.iso(end),'max_games':max_games,'max_usd':max_usd,
              'per_game_usd':1.35,'automatic_enrollment':automatic,'game_ids':sorted(set(game_ids)),
              'mode':'offline_mock' if mock else 'live_explicit_opt_in'}
        # Initial approval immutable. A future expansion needs a new versioned
        # authorization file and reviewed code, not a hidden reset of this cap.
        durable_json(self.root/'campaign.json',body);self.campaign();self.sync();return body

    def first_success(self):
        for key in self.jobs():
            if self.job(key)['mode']!='live_explicit_opt_in':continue
            try:
                proof=cloud.replay_job(self,key)
                frozen=self.artifact(key,'freeze');forecast=self.artifact(key,'forecast')
                if proof['forecasts'] and frozen['live_evaluation_eligible'] and forecast['live_evaluation_eligible']:return True
            except (ValueError,FileNotFoundError):pass
        return False

    def reserve(self,key,job,kind,usd):
        with self.checkpoints.lock:
            approval=self.campaign()
            if self.job(job)['mode']!=approval['mode']:raise ValueError('Campaign/job mode mismatch')
            with self.db() as c:
                total=c.execute('SELECT coalesce(sum(usd),0) FROM requests').fetchone()[0]
                game_total=c.execute('SELECT coalesce(sum(usd),0) FROM requests WHERE job=?',(job,)).fetchone()[0]
            if total+usd>approval['max_usd']+1e-12 or game_total+usd>approval['per_game_usd']+1e-12:raise ValueError('Campaign/per-game reservation budget exhausted')
            # Native reserve uses BEGIN IMMEDIATE and a unique request key. The
            # single remote owner + local lock covers the global check and commit.
            result=super().reserve(key,job,kind,usd)
            self.campaign()  # Approval may expire during a slow remote checkpoint.
            w=cloud.windows(self.job(job)['game'],self.config)
            deadline=w['forecast'] if kind=='forecast' else w['freeze'] if kind=='extraction' else w['retrieve']
            if self.clock()>deadline:raise ValueError('Durable reservation finished after request deadline; claim retained without send')
            return result


def enroll_catalog(state,catalog,session_deadline=None):
    approval=state.campaign();cfg=settings();now=state.clock();decisions=[]
    # Catalog is a completed, hashed state stage, not arbitrary input game IDs.
    games=sorted(catalog['games'],key=lambda g:(cloud.windows(g,state.config)['target'],g['game_id']))
    existing={state.job(k)['game']['game_id'] for k in state.jobs()}
    for game in games:
        gid=game['game_id'];w=cloud.windows(game,state.config);reason=None;key=None
        if gid in existing:reason='already_enrolled'
        elif gid in state.config['excluded_game_ids']:reason='protected_legacy_attempt'
        elif now>w['collect']:reason='missed_collection_start_no_backfill'
        elif w['collect']>now+cfg['dispatch_lookahead_minutes']*60:reason='outside_dispatch_horizon'
        elif session_deadline is not None and w['forecast']>session_deadline:reason='handoff_to_later_dispatch'
        elif not approval['automatic_enrollment'] and gid not in approval['game_ids']:reason='not_authorized'
        elif len(state.jobs())>=approval['max_games']:reason='campaign_game_cap'
        else:
            with state.db() as c:reserved=c.execute('SELECT coalesce(sum(usd),0) FROM requests').fetchone()[0]
            if reserved>=approval['max_usd']:reason='campaign_budget_exhausted'
            else:
                cloud.native.game_guard(game,now,False)
                auth=state.authorize([gid],1,approval['per_game_usd'],approval['mode']=='offline_mock')
                key=state.enroll(game,auth);existing.add(gid);reason='enrolled_chronologically'
        decisions.append({'game_id':gid,'target_utc':cloud.iso(w['target']),'reason':reason,'job_id':key})
    return decisions


def campaign_report(state):
    approval=state.campaign();rows=[]
    for key in state.jobs():
        row={'job_id':key,'game_id':state.job(key)['game']['game_id'],'attempted':state.has(key,'baseline'),
             'captured':False,'primary_eligible':False}
        for stage,field in (('freeze','captured'),('forecast','primary_eligible')):
            try:
                data=state.artifact(key,stage)
                row[field]=data['live_evaluation_eligible']
            except (ValueError,FileNotFoundError):pass
        rows.append(row)
    with state.db() as c:reserved=c.execute('SELECT coalesce(sum(usd),0) FROM requests').fetchone()[0]
    return {'campaign_id':approval['campaign_id'],'enrolled':len(rows),'attempted':sum(r['attempted'] for r in rows),
            'captured':sum(r['captured'] for r in rows),'primary_eligible':sum(r['primary_eligible'] for r in rows),
            'reserved_usd':reserved,'ceiling_usd':approval['max_usd'],'games':rows,
            'resources':[cloud.resources(state,r['job_id']) for r in rows],
            'actual_cost_note':'Token-based configured-rate estimates and unknown-usage reserves are not provider invoices.'}
