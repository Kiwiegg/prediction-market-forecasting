#!/usr/bin/env python3
"""Cloud news-v1 state machine. Offline plan by default; no Mac job access."""
import argparse
import copy
import json
import math
import os
import time
import urllib.parse
from datetime import datetime,timezone
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import cloud_news
from cloud_state import State, durable_json, process_lock, paid_gate
import prospective_discovery as discovery
import prospective_study as native
from evidence_documents import canonical, digest
from forecast_split import ROOT
from heldout_forecast import blank
from investigate_kalshi import iso, timestamp
from prospective_research import allowed_page
from prospective_sources import SourceSession, allowed_source
from research_providers import BraveAnthropicProvider, CapturedHTTP, ProviderError
from shared_evidence import freeze_packet, load_game_snapshot

CONFIG = ROOT / "examples/prospective_cloud_news_v1.json"
REGISTRY = ROOT / "experiments/prospective_cloud_news_v1_assets.json"


def checked(config):
    c = config["evidence"]; f = config["forecast"]
    values = [*c.values(), *f.values()]
    if any(type(v) not in (int, float) or not math.isfinite(v) for v in values): raise ValueError("Finite timing settings required")
    if (c["target_hours_before_tipoff"] != 24 or c["collection_lead_minutes"] <= 0
            or not -c["collection_lead_minutes"] < c["retrieval_deadline_offset_minutes"] <= 0
            or not 0 <= c["public_refresh_minutes_before_target"] < c["collection_lead_minutes"]
            or not 0 <= c["packet_freeze_grace_minutes"] <= f["completion_grace_minutes"] < 24*60):
        raise ValueError("Invalid fixed-cutoff windows")
    if config["protocol"] != "prospective_cloud_news_v1" or config["campaign_enabled"] is not False:
        raise ValueError("This deployment is disabled for automatic campaign enrollment")
    if '401909861' not in config['excluded_game_ids']:raise ValueError('Legacy scheduled pilot exclusion is mandatory')
    for section,fields in {'research':('max_queries','max_pages','max_tokens','max_output_tokens','max_extraction_calls'),
            'budgets':('forecast_calls',),'scheduler':('workers','market_workers','poll_seconds','discovery_days'),
            'market':('launch_seconds_before_target','quote_seconds_before_target')}.items():
        if any(type(config[section][k]) is not int or config[section][k]<0 for k in fields):raise ValueError('Nonnegative integer limits required')
    if any(type(v) not in (int,float) or not math.isfinite(v) or v<=0 for v in
            (config['research']['max_estimated_cost_usd'],config['budgets']['forecast_usd'],config['budgets']['per_game_usd'])):raise ValueError('Finite positive budget caps required')
    if not (1<=config['scheduler']['workers']<=32 and 1<=config['scheduler']['market_workers']<=16
            and 1<=config['scheduler']['poll_seconds']<=60 and 1<=config['scheduler']['discovery_days']<=7
            and 0<config['market']['quote_seconds_before_target']<config['market']['launch_seconds_before_target']<=300):raise ValueError('Invalid bounded scheduling/market configuration')
    return config


def windows(game, config):
    checked(config); target = native.aware(game["recorded_start_utc"]) - 86400
    c = config["evidence"]
    return {"target": target, "collect": target - c["collection_lead_minutes"]*60,
        "retrieve": target + c["retrieval_deadline_offset_minutes"]*60,
        "refresh": min(target-c["public_refresh_minutes_before_target"]*60, target+c["retrieval_deadline_offset_minutes"]*60),
        "freeze": target+c["packet_freeze_grace_minutes"]*60,
        "forecast": min(target+config["forecast"]["completion_grace_minutes"]*60, native.aware(game["recorded_start_utc"])),
        "tipoff": native.aware(game["recorded_start_utc"])}


def target_discovery_days(game,now):
    # A collection just before UTC midnight can target a tipoff two dates ahead.
    days=(datetime.fromtimestamp(native.aware(game['recorded_start_utc']),timezone.utc).date()-datetime.fromtimestamp(now,timezone.utc).date()).days+1
    if not 1<=days<=7:raise ValueError('Target fixture exceeds bounded discovery horizon')
    return days


def check_assets(committed=False):
    discovery.check_assets()
    expected = json.loads(REGISTRY.read_text())
    for name, sha in expected.items():
        if digest((ROOT/name).read_bytes()) != sha: raise ValueError("Cloud protocol asset changed: " + name)
        if committed:
            import subprocess
            if subprocess.check_output(["git", "show", "HEAD:"+name], cwd=ROOT) != (ROOT/name).read_bytes(): raise ValueError("Commit cloud protocol before activation")
    if committed:
        import subprocess
        if subprocess.check_output(['git','show','HEAD:'+str(REGISTRY.relative_to(ROOT))],cwd=ROOT)!=REGISTRY.read_bytes():raise ValueError('Commit cloud asset registry before activation')
    return expected


def eligibility(game, config, started, frozen, sealed=None):
    w = windows(game, config)
    ready = w["collect"] <= started <= w["retrieve"] and frozen <= w["freeze"] and frozen < w["tipoff"]
    return {"collection_window_eligible": w["collect"] <= started <= w["retrieve"], "freeze_eligible": frozen <= w["freeze"],
        "forecast_eligible": ready and (sealed is None or sealed <= w["forecast"] and sealed < w["tipoff"]),
        "exact_cutoff_capture_claimed": False}


class SourceBudget:
    def __init__(self, state, job, benchmark=False):
        self.state, self.job, self.reason, self.benchmark = state, job, None, benchmark
        self.clock = state.clock
    def reserve(self, key, kind, usd): self.state.reserve(digest((self.job+key).encode()), self.job, "article", usd)
    def stop(self, reason, **details):
        self.reason = reason
        self.state.circuit("host:"+urllib.parse.urlsplit(details["url"]).netloc, **details)
        if not self.benchmark:
            self.state.circuit('network',reason='source_access_denial',**details)
            self.state.circuit('paid',reason='source_access_denial',**details)


class CloudDocuments(discovery.ScheduleDocuments):
    def __init__(self, folder, policy, state, job, slot, cutoff, article=False, opener=None):
        self.state, self.job, self.slot, self.cutoff = state, job, slot, cutoff
        super().__init__(folder, False, policy, SourceBudget(state, job,slot.startswith('market')), article=article,
            clock=state.clock, guard=self.guard, opener=opener)
    def guard(self):
        self.state.check_circuit('network')
        if self.state.clock() > self.cutoff: raise ValueError("Hard retrieval deadline passed")
    def _get(self, value):
        cached = (self.folder/(digest(value.encode())+'.json')).exists()
        if not cached:
            self.guard(); self.state.check_circuit("host:"+urllib.parse.urlsplit(value).netloc)
            key = digest((self.job+self.slot+value).encode()); claim = self.state.root/'public_claims'/(key+'.json')
            with process_lock(self.state.root/'locks'/(key+'.lock')):
                if claim.exists(): raise ValueError("Uncertain public request cannot be retried")
                durable_json(claim, {"job": self.job, "slot": self.slot, "url": value, "at_utc": iso(self.state.clock())})
        try: return super()._get(value)
        except native.Halt as e: raise ValueError("Source denied; persistent host circuit retained") from e


class CloudSession(native.StudySession):
    def __init__(self, folder, state, job, slot, cutoff):
        super().__init__(folder, SourceBudget(state, job))
        self.store = CloudDocuments(folder, allowed_source, state, job, slot, cutoff)


class TargetSession(CloudSession):
    def json(self, value):
        meta, doc = super().json(value)
        if '/scoreboard?' in value and isinstance(doc, dict):
            doc = copy.deepcopy(doc); doc['events'] = [e for e in doc.get('events',[]) if str(e.get('id')) == self.registered_id]
        return meta, doc


class CloudHTTP(CapturedHTTP):
    def __init__(self, folder, state, job, kind, deadline, allow_live=False, expected=None, opener=None):
        super().__init__(folder, allow_live, opener, state.clock)
        self.state, self.job, self.kind, self.deadline, self.expected = state, job, kind, deadline, expected
    def request(self, provider, method, url, payload, headers, max_bytes):
        with paid_gate(self.state.root/'locks/paid.lock',self.deadline,self.state.clock):
            return self._request(provider,method,url,payload,headers,max_bytes)
    def _request(self, provider, method, url, payload, headers, max_bytes):
        if not self.allow_network: raise ProviderError("Paid network is disabled")
        job = self.state.job(self.job)
        if job['mode'] != 'live_explicit_opt_in': raise ProviderError("Mock authorization cannot make live requests")
        self.state.check_circuit('paid')
        self.state.check_circuit('network')
        if self.state.clock() > self.deadline or self.state.clock() >= native.aware(job['game']['recorded_start_utc']): raise ProviderError("Processing deadline/tipoff passed")
        wire = {"provider": provider, "method": method, "url": url, "payload": payload}; key = digest(canonical(wire))
        if self.kind == 'forecast':
            if self.expected is None or digest(canonical(self.expected['wire'])) != key or url != 'https://api.anthropic.com/v1/messages': raise ProviderError("Non-frozen forecast request")
            usd = self.expected['reserved_cost_usd']; claim = self.expected['key']
        elif self.kind == 'extraction':
            if provider != 'anthropic' or method != 'POST': raise ProviderError("Post-cutoff extraction cannot search/retrieve sources")
            usd = ((len(canonical(payload))+4096)*3+payload['max_tokens']*15)/1e6; claim = digest((self.job+self.kind+key).encode())
        else:
            if provider != 'brave' or method != 'GET': raise ProviderError("Search stage provider mismatch")
            usd = .01; claim = digest((self.job+self.kind+key).encode())
        self.state.reserve(claim, self.job, self.kind, usd)
        try:
            result = super().request(provider, method, url, payload, headers, max_bytes)
            if self.kind=='search' and self.state.clock()>self.deadline:raise ProviderError('Search response arrived after information cutoff')
            error = result.get('error',{})
            if isinstance(error,dict) and (error.get('type') in ('permission_error','authentication_error','forbidden') or any(x in str(error.get('message','')).lower() for x in ('access denied','request not allowed','unauthorized'))):
                self.state.circuit('paid',provider=provider,http_status=200);self.state.circuit('network',provider=provider,http_status=200); raise ProviderError('Provider access denial')
            return result
        except ProviderError:
            if self.calls and self.calls[-1]['http_status'] in (401,403,407,451):
                self.state.circuit('paid', provider=provider, http_status=self.calls[-1]['http_status'])
                self.state.circuit('network',provider=provider,http_status=self.calls[-1]['http_status'])
            raise


class LiveBackend:
    def __init__(self, state, allow_live=False): self.state, self.allow_live = state, allow_live
    def gate(self, key):
        if not self.allow_live or self.state.job(key)['mode'] != 'live_explicit_opt_in': raise ValueError('Live source/model opt-ins required')
        check_assets(True)
        if self.state.config!=json.loads(CONFIG.read_text()):raise ValueError('Commit/register changed timing configuration before live capture')
    def collect(self, key, folder, slot):
        self.gate(key); s=self.state; game=s.job(key)['game']; w=windows(game,s.config)
        if not w['collect'] <= s.clock() <= w['retrieve']: raise ValueError('Outside collection window')
        session=TargetSession(folder/'raw',s,key,slot,w['retrieve']);session.registered_id=game['game_id']
        start=s.clock();games,decisions=discovery.discover_verified(session,start,target_discovery_days(game,start))
        if len(games)!=1 or discovery.differences(game,games[0]): raise ValueError('Registered schedule changed/unavailable')
        session.target_id=game['game_id'];session.registry_game=game
        history_at=s.clock();history=native.collect_history(session,game,history_at)
        injury_at=s.clock();injuries=native.collect_official(session,game,injury_at,8,use_team_catalog=True)
        return {'history':history,'injuries':injuries,'sources':session.records,'started_at_utc':iso(start),'finished_at_utc':iso(s.clock()),
            'history_at_utc':iso(history_at),'injuries_at_utc':iso(injury_at),'schedule_decisions':decisions}
    def provider(self,key,folder,kind):
        self.gate(key);cfg=json.loads(native.CONFIG.read_text());w=windows(self.state.job(key)['game'],self.state.config)
        http=CloudHTTP(folder/'provider',self.state,key,kind,w['retrieve'] if kind=='search' else w['freeze'],True)
        return BraveAnthropicProvider(cfg,folder/'provider',True,kind=='extraction',http)
    def news(self,key,folder):
        self.gate(key);s=self.state;game=s.job(key)['game'];w=windows(game,s.config)
        if not w['collect']<=s.clock()<=w['retrieve']:raise ValueError('News collection window missed')
        provider=self.provider(key,folder,'search');docs=CloudDocuments(folder/'raw',lambda u:allowed_page(u,dated_articles=True),s,key,'news',w['retrieve'],article=True)
        result=cloud_news.acquire(game,w['retrieve'],provider,docs,s.config['research'],s.clock)
        result['provider_requests']=provider.http.calls;result['document_directory']='raw'
        return result
    def extract(self,key,folder,acquisition):
        s=self.state;game=s.job(key)['game'];w=windows(game,s.config)
        return cloud_news.extract(game,acquisition,self.provider(key,folder,'extraction'),w['target'],w['freeze'],s.config['research'],folder,s.clock)


def build_packet(game, collected, news, cutoff):
    history=copy.deepcopy(collected['history']); rejected=[]
    for fact in history['history']:
        if fact.get('available_by_utc') and native.aware(fact['available_by_utc'])>cutoff:
            fact['available_by_utc']=None;rejected.append(fact['game_id'])
    for m in collected['sources']:
        if native.aware(m['retrieved_at_utc'])>cutoff:
            raise ValueError('Collected source retrieval exceeds fixed cutoff')
    packet=native.collection.prospective_packet(game,cutoff,news)
    sections,stat_lineage=native.statistical_sections(game,history,cutoff,extended=True);packet.update(sections)
    official,injury_lineage=native.official_at_snapshot(game,collected['injuries'],cutoff)
    packet['injury_news']['official_injury']=official
    packet['reconstruction_status']='timestamped_history_unversioned_payloads'
    for finding in news['findings']:
        for ref in [finding,*finding['source_references']]:
            if any(native.aware(ref[k])>cutoff for k in ('published_at_utc','retrieved_at_utc')):raise ValueError('Post-cutoff news provenance')
    ready=all(history['complete'].get(side) and 'regular_season_record' in packet[side] for side in ('home','away'))
    freshness=[{'source_id':m['source_id'],'url':m['url'],'retrieved_at_utc':m['retrieved_at_utc'],
        'retrieval_age_at_T_seconds':cutoff-native.aware(m['retrieved_at_utc']),'underlying_update_age_known':False} for m in collected['sources']]
    for f in news['findings']:
        freshness.append({'url':f['source_url'],'published_age_at_T_seconds':cutoff-native.aware(f['published_at_utc']),
            'retrieval_age_at_T_seconds':cutoff-native.aware(f['retrieved_at_utc'])})
    if official.get('report_issue_utc'):
        freshness.append({'source_id':official['report_source_id'],'injury_issue_age_at_T_seconds':cutoff-native.aware(official['report_issue_utc']),
            'observed_availability_age_at_T_seconds':cutoff-native.aware(official['published_at_utc']),'first_publication_independently_verified':False})
    return packet,{'statistics':stat_lineage,'injuries':injury_lineage,'rejected_stat_facts':rejected,'sources':collected['sources'],'freshness':freshness,'evidence_complete':ready}


class Engine:
    def __init__(self,state,backend=None,mock_forecasts=False):self.state=state;self.backend=backend or LiveBackend(state);self.mock=mock_forecasts
    def artifact(self,key,name):
        try:return self.state.artifact(key,name)
        except ValueError:return None
    def freeze(self,key,folder):
        s=self.state;job=s.job(key);w=windows(job['game'],s.config);now=s.clock()
        if not w['target']<=now<=w['freeze']:raise ValueError('Freeze deadline/window missed')
        collected=self.artifact(key,'refresh') or self.artifact(key,'baseline')
        if collected is None:raise ValueError('No coherent captured statistical/official source set')
        research=self.artifact(key,'extraction')
        if research is None:raise ValueError('News research/extraction incomplete or failed')
        packet,lineage=build_packet(job['game'],collected,research['news'],w['target'])
        timing=eligibility(job['game'],s.config,native.aware(collected['started_at_utc']),now)
        lineage.update(protocol=s.config['protocol'],cohort=s.config['cohort'],information_cutoff_utc=iso(w['target']),
            physical_freeze_started_at_utc=iso(now),news_extraction=research['audit'],eligibility=timing,
            refresh_available=self.artifact(key,'refresh') is not None)
        frozen=freeze_packet(packet,folder/'evidence_captures')
        durable_json(folder/'evidence_snapshot_manifest.json',{'games':[{'game_id':job['game']['game_id'],'sha256':frozen['evidence_snapshot_sha256'],
            'capture_file':'evidence_captures/'+frozen['evidence_snapshot_sha256']+'.json','cutoff_utc':iso(w['target'])}]})
        finished=s.clock();lineage['physical_freeze_finished_at_utc']=iso(finished)
        lineage['eligibility']=eligibility(job['game'],s.config,native.aware(collected['started_at_utc']),finished)
        durable_json(folder/'lineage.json',lineage)
        if finished>w['freeze']:raise ValueError('Packet creation finished late; no eligible forecast')
        return {'packet_sha256':frozen['evidence_snapshot_sha256'],'eligible':lineage['evidence_complete'] and lineage['eligibility']['forecast_eligible'],
            'live_evaluation_eligible':job['mode']=='live_explicit_opt_in' and lineage['evidence_complete'] and lineage['eligibility']['forecast_eligible'],
            'frozen_at_utc':iso(finished),'cohort':s.config['cohort']}
    def forecast(self,key,folder):
        s=self.state;job=s.job(key);w=windows(job['game'],s.config);frozen=s.artifact(key,'freeze')
        if not frozen['eligible'] or s.clock()>w['forecast'] or s.clock()>=w['tipoff']:raise ValueError('Invalid/late frozen packet or inference deadline')
        packet=load_game_snapshot(s.job_dir(key)/'freeze',job['game']['game_id'])
        cfg={'direct':json.loads(native.direct.DEFAULT_CONFIG.read_text()),'v1':json.loads(native.v1.DEFAULT_CONFIG.read_text()),'v2':native.v2_evidence.config()}
        if self.mock:
            if job['mode']!='offline_mock':raise ValueError('Mock inference cannot produce live forecasts')
            for c in cfg.values():c['provider']='mock'
        elif job['mode']!='live_explicit_opt_in' or not getattr(self.backend,'allow_live',False):raise ValueError('Paid inference disabled')
        specs={'direct':[native.direct.request_spec(packet,cfg['direct'])],
            'v1':[native.v1.group_spec(g,cfg['v1']) for g in native.v1.build_groups(packet)],
            'v2':[native.v2_evidence.group_spec(g,cfg['v2']) for g in native.v2_evidence.build_groups(packet)]}
        durable_json(folder/'run.json',{'packet_sha256':frozen['packet_sha256'],'mode':job['mode'],'configs':cfg,'started_at_utc':iso(s.clock()),'assets':check_assets()})
        records={}; stopped=None
        for name in native.ORDER:
            observations=[];module=native.MODULES[name];cache=s.root/'shared_cache'/name
            for spec in specs[name]:
                final=cache/spec['key']/('forecast.json' if name=='direct' else 'group.json')
                marker=cache/spec['key']/'attempt.json'
                if marker.exists() and not final.exists():stopped='uncertain_native_claim'
                if s.clock()>w['forecast'] or s.clock()>=w['tipoff']:stopped='forecast_deadline'
                try:s.check_circuit('paid')
                except ValueError:stopped='paid_access_denial'
                if stopped and spec.get('usable',True) and not final.exists():
                    observation=blank(name,spec,cfg[name],stopped,marker.exists(),marker if marker.exists() else None)
                else:
                    factory=lambda path,allow_network=False,spec=spec:CloudHTTP(path,s,key,'forecast',w['forecast'],allow_network,spec)
                    observation=(native.direct.cached_forecast(spec,cfg[name],cache,not self.mock,factory) if name=='direct' else module.cached_group(spec,cfg[name],cache,not self.mock,factory))
                observations.append(observation)
            records[name]=observations[0] if name=='direct' else native.v1.game_record(job['game']['game_id'],frozen['packet_sha256'],observations) if name=='v1' else native.v2.game_record({'game_id':job['game']['game_id'],'evidence_sha256':frozen['packet_sha256']},observations)
            durable_json(folder/(name+'.json'),records[name])
        sealed=s.clock();eligible=sealed<=w['forecast'] and sealed<w['tipoff']
        result={'packet_sha256':frozen['packet_sha256'],'sealed_at_utc':iso(sealed),'timing_eligible':eligible,
            'successful_methods':[n for n,r in records.items() if r['status']=='success'],'stop_reason':stopped,'mode':job['mode'],
            'records':records,'primary_pair_available':eligible and records['direct']['status']=='success' and records['v2']['status']=='success'}
        result['live_evaluation_eligible']=job['mode']=='live_explicit_opt_in' and result['primary_pair_available']
        durable_json(folder/'seal.json',result);return result
    def advance(self,key):
        s=self.state;job=s.job(key);w=windows(job['game'],s.config)
        with process_lock(s.job_dir(key)/'evidence.lock'):
            if s.has(key,'forecast'):return {'status':'sealed_or_interrupted','job':key,'completion':self.artifact(key,'forecast') is not None}
            if s.has(key,'freeze') and (self.artifact(key,'freeze') is None or not self.artifact(key,'freeze')['eligible']):return {'status':'freeze_failed_or_ineligible','job':key}
            if s.clock()<w['collect']:return {'status':'pending'}
            for slot in ('baseline','news','refresh'):
                due=w['refresh'] if slot=='refresh' else w['collect']
                if slot=='news' and self.artifact(key,'baseline') is None and self.artifact(key,'refresh') is None:continue
                if due<=s.clock()<=w['retrieve'] and not s.has(key,slot):
                    try:s.stage(key,slot,lambda folder,slot=slot:self.backend.news(key,folder) if slot=='news' else self.backend.collect(key,folder,slot))
                    except (Exception,native.Halt):pass
            if self.artifact(key,'news') is not None and not s.has(key,'extraction') and s.clock()<=w['freeze']:
                try:s.stage(key,'extraction',lambda folder:self.backend.extract(key,folder,s.artifact(key,'news')))
                except (Exception,native.Halt):pass
            if w['target']<=s.clock() and not s.has(key,'freeze'):
                try:s.stage(key,'freeze',lambda folder:self.freeze(key,folder))
                except (Exception,native.Halt):pass
            frozen=self.artifact(key,'freeze')
            if frozen and frozen['eligible'] and not s.has(key,'forecast'):
                try:s.stage(key,'forecast',lambda folder:self.forecast(key,folder))
                except (Exception,native.Halt):pass
            if s.clock()>w['retrieve'] and not s.has(key,'baseline'):
                try:s.stage(key,'baseline',lambda folder:(_ for _ in ()).throw(ValueError('Missed collection deadline')))
                except ValueError:pass
            return {'status':'processed','job':key}


def replay_job(state,key):
    job=state.job(key);folder=state.job_dir(key)
    with state.db() as c:stages=[r['name'] for r in c.execute("SELECT name FROM stages WHERE job=? AND status='done'",(key,))]
    for name in stages:state.artifact(key,name)
    if 'news' in stages and 'extraction' in stages:
        cloud_news.replay_sources(job['game'],state.artifact(key,'news'),state.artifact(key,'extraction'),folder/'news',windows(job['game'],state.config)['retrieve'])
    for name in ('baseline','refresh'):
        if name not in stages:continue
        data=state.artifact(key,name)
        if data.get('fixture_only'):continue
        from evidence_documents import DocumentStore
        class OfflineSession(native.StudySession):
            def __init__(self,path):
                SourceSession.__init__(self,path,True,store=DocumentStore(path,True,allowed_source));self.target_id=job['game']['game_id'];self.registry_game=job['game']
        source=OfflineSession(folder/name/'raw')
        history=native.collect_history(source,job['game'],native.aware(data['history_at_utc']))
        injury=native.collect_official(source,job['game'],native.aware(data['injuries_at_utc']),8,use_team_catalog=True)
        if history!=data['history'] or injury!=data['injuries']:raise ValueError('Statistical/injury source replay differs')
    if 'freeze' not in stages:return {'verified':True,'mode':job['mode'],'stages':stages,'forecasts':False}
    data=state.artifact(key,'refresh') if 'refresh' in stages else state.artifact(key,'baseline')
    packet,_=build_packet(job['game'],data,state.artifact(key,'extraction')['news'],windows(job['game'],state.config)['target'])
    loaded=load_game_snapshot(folder/'freeze',job['game']['game_id'])
    if digest(canonical(packet))!=loaded['evidence_snapshot_sha256']:raise ValueError('Offline packet reconstruction differs')
    if 'forecast' in stages:
        run=json.loads((folder/'forecast/run.json').read_text());result=state.artifact(key,'forecast')
        verify_predictions(loaded,run['configs'],result['records'])
        for name,record in result['records'].items():
            observations=[record] if name=='direct' else record['groups']
            for observation in observations:
                if observation['status'].startswith('not_attempted'):continue
                cache=state.root/'shared_cache'/name
                spec_key=observation['request_sha256']
                target=cache/spec_key/('forecast.json' if name=='direct' else 'group.json')
                if not target.exists() or json.loads(target.read_text())!=observation:raise ValueError('Native immutable cache differs')
                native.direct.verify_raw(observation,cache/spec_key)
    return {'verified':True,'mode':job['mode'],'stages':stages,'forecasts':'forecast' in stages,'packet_sha256':loaded['evidence_snapshot_sha256']}


def verify_predictions(packet,configs,records):
    specs={'direct':[native.direct.request_spec(packet,configs['direct'])],
        'v1':[native.v1.group_spec(g,configs['v1']) for g in native.v1.build_groups(packet)],
        'v2':[native.v2_evidence.group_spec(g,configs['v2']) for g in native.v2_evidence.build_groups(packet)]}
    for name,record in records.items():
        observations=[record] if name=='direct' else record['groups']
        if len(observations)!=len(specs[name]):raise ValueError('Group count differs')
        for obs,spec in zip(observations,specs[name]):
            native.MODULES[name].verify_record(obs)
            if obs['request_sha256']!=spec['key'] or obs['evidence_sha256']!=packet['evidence_snapshot_sha256']:raise ValueError('Different shared parent or request')
        if name!='direct':
            expected=native.v1.game_record(packet['game_id'],packet['evidence_snapshot_sha256'],observations) if name=='v1' else native.v2.game_record({'game_id':packet['game_id'],'evidence_sha256':packet['evidence_snapshot_sha256']},observations)
            if expected!=record:raise ValueError('Native aggregation differs')


def export_replay(state,key,output):
    proof=replay_job(state,key);folder=state.job_dir(key);job=state.job(key)
    packet=load_game_snapshot(folder/'freeze',job['game']['game_id'])
    forecasts=state.artifact(key,'forecast');run=json.loads((folder/'forecast/run.json').read_text())
    result={'mode':job['mode'],'protocol':state.config,'job':job,'packet':packet,'configs':run['configs'],
        'live_evaluation_eligible':forecasts['live_evaluation_eligible'],
        'forecast':forecasts,'private_raw_responses_included':False,'private_replay':proof,
        'lineage':json.loads((folder/'freeze/lineage.json').read_text())}
    # Search/LLM raw payloads remain private; accepted model-facing citations stay.
    result['lineage']['news_extraction']={k:v for k,v in result['lineage']['news_extraction'].items() if k not in ('provider_requests','agent_candidates','acquisition')}
    def sanitize(value):
        if isinstance(value,dict):return {k:sanitize(v) for k,v in value.items() if k not in ('headers','payload')}
        if isinstance(value,list):return [sanitize(v) for v in value]
        return value
    result['lineage']=sanitize(result['lineage'])
    output=Path(output);durable_json(output/'audit.json',result)
    durable_json(output/'manifest.json',{'audit.json':digest((output/'audit.json').read_bytes())})
    return result


def replay_public(folder):
    check_assets()
    folder=Path(folder);m=json.loads((folder/'manifest.json').read_text())
    if m!={'audit.json':digest((folder/'audit.json').read_bytes())}:raise ValueError('Sanitized audit changed')
    a=json.loads((folder/'audit.json').read_text());p=a['packet']
    if a['private_raw_responses_included'] is not False or a['job']['config']!=a['protocol']:raise ValueError('Unsafe audit/config mismatch')
    if a['job']['config_sha256']!=digest(canonical(a['protocol'])):raise ValueError('Config hash mismatch')
    if a['job']['assets_sha256']!=digest(REGISTRY.read_bytes()):
        # Preserve existing immutable public captures after the source-session
        # constructor repair. All other original assets must still match exactly.
        original=ROOT/'experiments/prospective_cloud_news_v1_initial_assets.json'
        if a['job']['assets_sha256']!=digest(original.read_bytes()):raise ValueError('Code/protocol registry differs')
        for name,sha in json.loads(original.read_text()).items():
            if name!='scripts/cloud_prospective.py' and digest((ROOT/name).read_bytes())!=sha:
                raise ValueError('Original replay asset changed: '+name)
    if a['job']['config_sha256']!=digest(canonical(checked(a['protocol']))):raise ValueError('Invalid protocol settings')
    native.direct.validate_packet(p)
    if p['game_id']!=a['job']['game']['game_id'] or native.aware(p['cutoff_utc'])!=windows(a['job']['game'],a['protocol'])['target']:raise ValueError('Public cutoff/game differs from registered T')
    for f in p['injury_news']['news']['findings']:
        for ref in [f,*f['source_references']]:
            if any(native.aware(ref[k])>native.aware(p['cutoff_utc']) for k in ('published_at_utc','retrieved_at_utc')):raise ValueError('Public post-cutoff source')
    if p['evidence_snapshot_sha256']!=digest(canonical({k:v for k,v in p.items() if k!='evidence_snapshot_sha256'})):raise ValueError('Packet changed')
    verify_predictions(p,a['configs'],a['forecast']['records'])
    return {'verified':True,'mode':a['mode'],'packet_sha256':p['evidence_snapshot_sha256'],'scope':'sanitized shared packet, native requests and aggregation; not source/provider authentication'}


def resources(state,key):
    observations={};folder=state.job_dir(key)
    for name in native.ORDER:
        path=folder/'forecast'/(name+'.json')
        if not path.exists():continue
        record=json.loads(path.read_text())
        for r in [record] if name=='direct' else record['groups']:observations[r['request_sha256']]=r
    reported={k:sum((r.get('usage') or {}).get(k,0) for r in observations.values()) for k in ('input_tokens','output_tokens')}
    extract_path=folder/'extraction/extraction.json';extraction_usage=[];extraction_latency=0
    if extract_path.exists():
        audit=json.loads(extract_path.read_text())['audit'];extraction_usage=audit['reported_provider_usage']
        extraction_latency=sum(r.get('latency_seconds',0) for r in audit['provider_requests'])
    with state.db() as c:reserved=[dict(r) for r in c.execute('SELECT kind,count(*) AS claims,sum(usd) AS reserved_usd FROM requests WHERE job=? GROUP BY kind',(key,))]
    return {'mode':state.job(key)['mode'],'pre_call_reservations':reserved,'forecast_reported_tokens':reported,
        'forecast_usage_unavailable_observations':sum(r.get('usage') is None and r['status']=='failed' for r in observations.values()),
        'forecast_estimated_cost_usd':sum(r.get('estimated_cost_usd',0) for r in observations.values()),
        'forecast_summed_latency_seconds':sum(r.get('latency_seconds') or 0 for r in observations.values()),
        'extraction_reported_usage':extraction_usage,'extraction_latency_seconds':extraction_latency,
        'note':'Reservations include unknown usage. Reported-token estimates use frozen configured rates, not invoices. Mock usage is synthetic.'}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--state',type=Path);p.add_argument('--config',type=Path,default=CONFIG)
    p.add_argument('--init',action='store_true');p.add_argument('--authorize',action='store_true');p.add_argument('--game-id',action='append',default=[])
    p.add_argument('--confirm-authorized-cloud-game',action='store_true');p.add_argument('--max-usd',type=float,default=1.35)
    p.add_argument('--discover',action='store_true');p.add_argument('--enroll',type=Path);p.add_argument('--authorization')
    p.add_argument('--serve',action='store_true');p.add_argument('--tick',action='store_true');p.add_argument('--market-worker',action='store_true')
    p.add_argument('--allow-network',action='store_true');p.add_argument('--allow-search',action='store_true');p.add_argument('--allow-inference',action='store_true')
    p.add_argument('--replay');p.add_argument('--export-replay');p.add_argument('--output',type=Path);p.add_argument('--replay-public',type=Path)
    p.add_argument('--resources')
    a=p.parse_args();cfg=checked(json.loads(a.config.read_text()))
    if a.replay_public:
        if a.allow_network or a.allow_search or a.allow_inference:p.error('Replay is offline')
        print(json.dumps(replay_public(a.replay_public),indent=2));return
    if not a.state:print(json.dumps({'status':'deployment_disabled_plan','config':cfg,'network_calls':0,'paid_calls':0,'deployment':'persistent Linux VM; explicit private state and authorization required'},indent=2));return
    state=State(a.state,cfg,initialize=a.init)
    if a.resources:
        if a.allow_network or a.allow_search or a.allow_inference:p.error('Resource audit is offline')
        result=resources(state,a.resources)
    elif a.replay or a.export_replay:
        if a.allow_network or a.allow_search or a.allow_inference:p.error('Replay/export is offline')
        if a.export_replay:
            if not a.output:p.error('Separate sanitized output required')
            result=export_replay(state,a.export_replay,a.output)['private_replay']
        else:result=replay_job(state,a.replay)
    elif a.init:result={'store_uuid':state.uuid,'status':'initialized_without_activation'}
    elif a.authorize:
        if not a.confirm_authorized_cloud_game: p.error('Explicit future operator authorization required; not authorized by implementation task')
        check_assets(True);result={'authorization':state.authorize(a.game_id,len(a.game_id),a.max_usd)}
    elif a.discover:
        if not a.allow_network:p.error('Discovery requires explicit public network permission; it never enables paid calls')
        if a.authorization:state.authorization(a.authorization)
        check_assets(True)
        slot=time.strftime('%Y-%m-%d',time.gmtime())
        folder=state.root/'discovery'/slot;folder.mkdir(parents=True,exist_ok=False)
        session=CloudSession(folder/'raw',state,'discovery:'+slot,'discovery',time.time()+120)
        start=time.time();games,decisions=discovery.discover_verified(session,start,cfg['scheduler']['discovery_days'])
        result={'started_at':start,'games':games,'decisions':decisions};durable_json(folder/'discovery.json',result)
    elif a.enroll:
        if not a.authorization:p.error('Explicit activation record required')
        saved=json.loads(a.enroll.read_text());approved=state.authorization(a.authorization);now=time.time()
        games=sorted(saved['games'],key=lambda g:(g['recorded_start_utc'],g['game_id']))
        result=[]
        for game in games:
            if game['game_id'] in approved['game_ids'] and windows(game,cfg)['collect']>now:
                native.game_guard(game,now,False);result.append(state.enroll(game,a.authorization))
    elif a.serve or a.tick:
        if not all((a.allow_network,a.allow_search,a.allow_inference)):p.error('Worker stays disabled without all network/search/inference opt-ins')
        if not os.environ.get('NBA_CLOUD_STORE_UUID')==state.uuid:p.error('Persistent volume identity not confirmed')
        if not a.market_worker and any(not os.environ.get(k) for k in ('BRAVE_SEARCH_API_KEY','ANTHROPIC_API_KEY')):p.error('Both search and extraction/forecast credentials must be configured before worker startup')
        check_assets(True)
        if a.market_worker:
            from cloud_market import MarketEngine
            engine=MarketEngine(state,True)
        else:engine=Engine(state,LiveBackend(state,True))
        with ThreadPoolExecutor(max_workers=cfg['scheduler']['market_workers' if a.market_worker else 'workers']) as pool:
            while True:
                futures=[pool.submit(engine.advance,k) for k in state.jobs()]
                for f in futures:
                    try:f.result()
                    except (Exception,native.Halt) as e:state.event(None,'worker_error',error_type=type(e).__name__,reason=str(e)[:240])
                state.heartbeat('market' if a.market_worker else 'evidence')
                if a.tick:break
                time.sleep(cfg['scheduler']['poll_seconds'])
        result=state.status()
    else:result=state.status()
    print(json.dumps(result,indent=2))


if __name__=='__main__':main()
