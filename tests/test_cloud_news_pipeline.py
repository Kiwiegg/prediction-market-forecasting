import copy
import io
import json
import os
import sys
import tempfile
import unittest
import urllib.error
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import cloud_prospective as cloud
import cloud_news
from cloud_state import State,durable_json,process_lock
from evidence_documents import DocumentStore,canonical,digest
from prospective_research import allowed_page,validate_page
from research_providers import BraveAnthropicProvider,CapturedHTTP
import test_prospective_pipeline as fixtures
from test_prospective_discovery import Response
import cloud_market


class FixtureBackend:
    """All publisher bytes and extraction outputs are artificial/offline."""
    allow_live=False
    def __init__(self,state):self.state=state;self.extract_calls=0
    def seed(self,folder,game):
        old=fixtures.event
        def event(*a,**kw):return old(*a,**kw) if a or kw else old(gid=game['game_id'],start=game['recorded_start_utc'])
        with patch.object(fixtures,'event',event):fixtures.fixture(folder)
        body=('<meta property="article:published_time" content="'+cloud.iso(self.state.clock()-100)+'"><article><p>'+fixtures.CLAIM+'</p></article>').encode()
        fixtures.capture(folder/'news_raw',fixtures.PAGE,body)
        for path in folder.rglob('*.json'):
            meta=json.loads(path.read_text())
            if 'body_sha256' in meta and 'retrieved_at_utc' in meta:
                meta['headers']={'set-cookie':'synthetic-private-publisher-cookie'}
                meta['retrieved_at_utc']=cloud.iso(self.state.clock()-1);path.write_bytes(canonical(meta))
    def collect(self,key,folder,slot):
        s=self.state;game=s.job(key)['game'];self.seed(folder,game)
        source=cloud.SourceSession(folder/'raw',True)
        history=cloud.native.collect_history(source,game,s.clock())
        with patch('prospective_sources.parse_pdf',side_effect=fixtures.parsed_fixture):
            injuries=cloud.native.collect_official(source,game,s.clock(),8,use_team_catalog=True)
        return {'history':history,'injuries':injuries,'sources':source.records,'started_at_utc':cloud.iso(s.clock()),'finished_at_utc':cloud.iso(s.clock()),'schedule_decisions':[{'fixture_only':True}],'fixture_only':True}
    def news(self,key,folder):
        s=self.state;game=s.job(key)['game'];self.seed(folder,game)
        class Search:
            search_token_bound=32768
            def search(self,*a):return [{'url':fixtures.PAGE}]
        docs=DocumentStore(folder/'news_raw',True,lambda u:allowed_page(u,dated_articles=True))
        value=cloud_news.acquire(game,cloud.windows(game,s.config)['retrieve'],Search(),docs,s.config['research'],s.clock)
        value['document_directory']='news_raw';return value
    def extract(self,key,folder,acquisition):
        self.extract_calls+=1;s=self.state;game=s.job(key)['game'];w=cloud.windows(game,s.config)
        ref=acquisition['context']['sources'][0]['snippets'][0]['source_ref']
        finding={'category':'injury_update','team':game['home_name'],'player':'Example Player','claim':fixtures.CLAIM,'source_ref':ref}
        op=Mock();op.open.return_value=Response(fixtures.model_response([finding]))
        provider=BraveAnthropicProvider(json.loads(cloud.native.CONFIG.read_text()),folder/'mock_provider',True,True,
            CapturedHTTP(folder/'mock_provider',True,op,s.clock))
        with patch.dict(os.environ,{'ANTHROPIC_API_KEY':'synthetic-not-a-real-key'}):
            result=cloud_news.extract(game,acquisition,provider,w['target'],w['freeze'],s.config['research'],folder,s.clock)
        result['audit']['fixture_only']=True
        return result


def setup(root,live=False):
    cfg=json.loads(cloud.CONFIG.read_text())
    game=cloud.discovery.project(fixtures.event(start=cloud.iso(fixtures.T+86520)))
    clock=[cloud.windows(game,cfg)['collect']];state=State(root,cfg,lambda:clock[0],True)
    approval=state.authorize([game['game_id']],mock=not live)
    key=state.enroll(game,approval)
    return state,key,clock,FixtureBackend(state)


def simulate(root,output=None):
    state,key,clock,backend=setup(root);engine=cloud.Engine(state,backend,True)
    with patch('urllib.request.OpenerDirector.open',side_effect=AssertionError('Offline simulation cannot use network')):
        engine.advance(key)
        clock[0]=cloud.windows(state.job(key)['game'],state.config)['refresh']
        engine.advance(key)
        clock[0]=cloud.windows(state.job(key)['game'],state.config)['target']+1
        engine.advance(key)
        proof=cloud.replay_job(state,key)
        if output:cloud.export_replay(state,key,output)
    return state,key,clock,backend,proof


class CloudPipelineTests(unittest.TestCase):
    def test_full_offline_shared_packet_news_and_native_methods(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);state,key,clock,backend,proof=simulate(root/'state',root/'public')
            self.assertTrue(proof['forecasts']);self.assertEqual(proof['mode'],'offline_mock')
            packet=cloud.load_game_snapshot(state.job_dir(key)/'freeze','900')
            self.assertNotIn('snapshot_timing',packet)
            self.assertEqual(len(packet['injury_news']['news']['findings']),1)
            self.assertEqual(packet['injury_news']['official_injury']['away']['state'],'not_yet_submitted')
            result=state.artifact(key,'forecast');self.assertTrue(result['primary_pair_available'])
            self.assertFalse(result['live_evaluation_eligible']);self.assertFalse(state.artifact(key,'freeze')['live_evaluation_eligible'])
            self.assertEqual({r['evidence_sha256'] for r in result['records'].values()},{packet['evidence_snapshot_sha256']})
            self.assertEqual(cloud.replay_public(root/'public')['packet_sha256'],packet['evidence_snapshot_sha256'])
            self.assertNotIn('synthetic-private-publisher-cookie',(root/'public/audit.json').read_text())
            before={p:digest(p.read_bytes()) for p in (state.root/'jobs').rglob('*') if p.is_file() and p.suffix!='.lock'}
            cloud.Engine(State(state.root,state.config,lambda:clock[0]),backend,True).advance(key)
            self.assertEqual(before,{p:digest(p.read_bytes()) for p in before});self.assertEqual(backend.extract_calls,1)
            self.assertEqual(state.status()['reservations'],[])

    def test_config_windows_utc_dst_and_deadline_boundaries(self):
        cfg=json.loads(cloud.CONFIG.read_text());game=cloud.discovery.project(fixtures.event(start='2026-11-02T00:00:00Z'))
        w=cloud.windows(game,cfg)
        self.assertEqual(cloud.iso(w['target']),'2026-11-01T00:00:00Z')
        self.assertEqual(w['collect'],w['target']-1800);self.assertEqual(w['freeze'],w['target']+300);self.assertEqual(w['forecast'],w['target']+900)
        self.assertTrue(cloud.eligibility(game,cfg,w['collect'],w['freeze'],w['forecast'])['forecast_eligible'])
        self.assertFalse(cloud.eligibility(game,cfg,w['collect']-.001,w['freeze'])['forecast_eligible'])
        self.assertFalse(cloud.eligibility(game,cfg,w['collect'],w['freeze']+.001)['forecast_eligible'])
        self.assertFalse(cloud.eligibility(game,cfg,w['collect'],w['freeze'],w['forecast']+.001)['forecast_eligible'])
        equiv=dict(game,recorded_start_utc='2026-11-01T19:00:00-05:00');self.assertEqual(cloud.windows(equiv,cfg),w)
        midnight=dict(game,recorded_start_utc='2026-10-22T00:15:00Z')
        self.assertEqual(cloud.target_discovery_days(midnight,cloud.native.aware('2026-10-20T23:45:00Z')),3)
        for field,value in (('target_hours_before_tipoff',23),('retrieval_deadline_offset_minutes',1),('collection_lead_minutes',float('nan'))):
            bad=copy.deepcopy(cfg);bad['evidence'][field]=value
            with self.assertRaises(ValueError):cloud.checked(bad)

    def test_retrieval_after_exact_target_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            state,key,clock,backend=setup(Path(tmp));game=state.job(key)['game'];cut=cloud.windows(game,state.config)['target']
            data=backend.collect(key,state.job_dir(key)/'fixture','baseline')
            data['sources'][0]['retrieved_at_utc']=cloud.iso(cut+.001)
            with self.assertRaises(ValueError):cloud.build_packet(game,data,cloud.native.collection.no_research()['news'],cut)
            docs=cloud.CloudDocuments(state.job_dir(key)/'late',lambda u:True,state,key,'late',cut)
            clock[0]=cut+.001
            with patch('urllib.request.OpenerDirector.open',side_effect=AssertionError('No post-T fetch')):
                with self.assertRaises(ValueError):docs.get(fixtures.PAGE)

    def test_post_cutoff_extraction_uses_pre_cutoff_captured_bytes_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            state,key,clock,backend=setup(Path(tmp));engine=cloud.Engine(state,backend,True)
            data=state.stage(key,'baseline',lambda f:backend.collect(key,f,'baseline'))
            acquisition=state.stage(key,'news',lambda f:backend.news(key,f))
            clock[0]=cloud.windows(state.job(key)['game'],state.config)['target']+60
            with patch.object(backend,'news',side_effect=AssertionError('No post-T research')),patch('urllib.request.OpenerDirector.open',side_effect=AssertionError('No source fetch')):
                engine.advance(key)
            self.assertTrue(state.artifact(key,'freeze')['eligible'])
            audit=state.artifact(key,'extraction')['audit']
            self.assertEqual(audit['input_context_sha256'],acquisition['context_sha256'])
            self.assertGreater(cloud.native.aware(audit['finished_at_utc']),cloud.windows(state.job(key)['game'],state.config)['target'])

    def test_undated_future_modified_and_naive_article_metadata_rejected(self):
        cutoff=fixtures.T+120
        for metadata in ('', '<meta property="article:published_time" content="'+cloud.iso(cutoff+1)+'">',
            '<meta property="article:published_time" content="2026-10-20T00:00:00">',
            '<meta property="article:published_time" content="'+cloud.iso(fixtures.T-100)+'"><meta property="article:modified_time" content="'+cloud.iso(cutoff+1)+'">'):
            body=(metadata+'<article><p>'+fixtures.CLAIM+'</p></article>').encode()
            meta={'source_id':'fixture','http_status':200,'truncated':False,'retrieved_at_utc':cloud.iso(cutoff),'body_sha256':digest(body)}
            result=validate_page(fixtures.PAGE,body,meta,cutoff,True,dated_articles=True)
            self.assertFalse(result['usable'])
        body=('<meta property="article:published_time" content="'+cloud.iso(cutoff-5)+'"><article><p>'+fixtures.CLAIM+'</p></article>').encode()
        meta.update(retrieved_at_utc=cloud.iso(cutoff-10),body_sha256=digest(body))
        self.assertFalse(validate_page(fixtures.PAGE,body,meta,cutoff,True,dated_articles=True)['usable'])

    def test_missing_and_incomplete_official_reports_preserve_uncertainty(self):
        with tempfile.TemporaryDirectory() as tmp:
            state,key,clock,backend=setup(Path(tmp));game=state.job(key)['game'];data=backend.collect(key,state.job_dir(key)/'data','baseline')
            data['injuries']={'reports':{},'candidates':[],'archive':[]}
            packet,line=cloud.build_packet(game,data,cloud.native.collection.no_research()['news'],cloud.windows(game,state.config)['target'])
            self.assertTrue(line['evidence_complete']);self.assertEqual(packet['injury_news']['official_injury']['home']['state'],'unavailable')
            data['history']['complete']['away']=False
            self.assertFalse(cloud.build_packet(game,data,packet['injury_news']['news'],cloud.windows(game,state.config)['target'])[1]['evidence_complete'])

    def test_late_freeze_blocks_forecasts(self):
        with tempfile.TemporaryDirectory() as tmp:
            state,key,clock,backend=setup(Path(tmp));engine=cloud.Engine(state,backend,True);engine.advance(key)
            clock[0]=cloud.windows(state.job(key)['game'],state.config)['freeze']+.01
            engine.advance(key);self.assertIsNone(engine.artifact(key,'freeze'));self.assertFalse(state.has(key,'forecast'))

    def test_restart_uncertain_stage_and_request_are_not_resent(self):
        with tempfile.TemporaryDirectory() as tmp:
            state,key,clock,backend=setup(Path(tmp))
            with state.db() as c:c.execute('INSERT INTO stages VALUES(?,?,?,NULL)',(key,'baseline','claimed'))
            with patch.object(backend,'collect',side_effect=AssertionError('No retry')):cloud.Engine(state,backend,True).advance(key)
            state.reserve('abc',key,'search',.01)
            restarted=State(state.root,state.config,lambda:clock[0])
            with self.assertRaises(ValueError):restarted.reserve('abc',key,'search',.01)

    def test_completed_stage_commit_gap_recovers_without_operation(self):
        with tempfile.TemporaryDirectory() as tmp:
            state,key,clock,backend=setup(Path(tmp));value={'safe':'captured'}
            with state.db() as c:c.execute('INSERT INTO stages VALUES(?,?,?,NULL)',(key,'example','claimed'))
            durable_json(state.job_dir(key)/'example/result.json',{'value':value,'files':{},'finished_at_utc':cloud.iso(clock[0])})
            self.assertEqual(state.artifact(key,'example'),value)

    def test_overlapping_jobs_share_atomic_global_budget_and_unique_identity(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg=json.loads(cloud.CONFIG.read_text());state=State(Path(tmp),cfg,initialize=True)
            g1=cloud.discovery.project(fixtures.event());g2=dict(g1,game_id='901')
            auth=state.authorize(['900','901'],2,.015,mock=True)
            keys=[state.enroll(g,auth) for g in (g1,g2)]
            def reserve(key):
                try:state.reserve(digest(key.encode()),key,'search',.01);return True
                except ValueError:return False
            with ThreadPoolExecutor(max_workers=2) as pool:self.assertEqual(sum(pool.map(reserve,keys)),1)
            self.assertNotEqual(*keys)
            with self.assertRaises(ValueError):state.enroll(dict(g1,recorded_start_utc=cloud.iso(fixtures.T+99999)),auth)
            with process_lock(state.job_dir(keys[0])/'test.lock'):
                with self.assertRaises(RuntimeError):
                    with process_lock(state.job_dir(keys[0])/'test.lock'):pass

    def test_paid_403_stops_new_search_and_forecast_calls(self):
        with tempfile.TemporaryDirectory() as tmp:
            state,key,clock,backend=setup(Path(tmp),live=True);op=Mock()
            op.open.side_effect=urllib.error.HTTPError('https://api.anthropic.com/v1/messages',403,'Denied',{},io.BytesIO(b'{}'))
            http=cloud.CloudHTTP(state.job_dir(key)/'provider',state,key,'extraction',clock[0]+100,True,opener=op)
            payload={'max_tokens':128,'model':'fixture','messages':[]}
            with self.assertRaises(ValueError):http.request('anthropic','POST','https://api.anthropic.com/v1/messages',payload,{},8192)
            with self.assertRaises(ValueError):state.reserve('after',key,'forecast',.01)
            with self.assertRaises(ValueError):http.request('anthropic','POST','https://api.anthropic.com/v1/messages',payload,{},8192)
            self.assertEqual(op.open.call_count,1)

    def test_source_denial_circuit_blocks_other_url_on_same_host(self):
        with tempfile.TemporaryDirectory() as tmp:
            state,key,clock,backend=setup(Path(tmp));op=Mock()
            op.open.side_effect=urllib.error.HTTPError(fixtures.PAGE,403,'Denied',{},io.BytesIO(b'no'))
            docs=cloud.CloudDocuments(state.job_dir(key)/'docs',lambda u:True,state,key,'test',clock[0]+50,opener=op)
            with self.assertRaises(ValueError):docs.get(fixtures.PAGE)
            with self.assertRaises(ValueError):docs.get(fixtures.PAGE+'-different')
            self.assertEqual(op.open.call_count,1)
            with self.assertRaises(ValueError):state.reserve('after-source-denial',key,'forecast',.01)

    def test_legacy_pilot_exclusion_missing_volume_and_authorization_guards(self):
        cfg=json.loads(cloud.CONFIG.read_text())
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError):State(Path(tmp)/'missing',cfg)
            state=State(Path(tmp)/'new',cfg,initialize=True)
            with self.assertRaises(ValueError):state.authorize(['401909861'],mock=True)
            with self.assertRaises(ValueError):state.authorization('missing')

    def test_missing_database_cannot_reset_an_existing_volume(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg=json.loads(cloud.CONFIG.read_text());root=Path(tmp);state=State(root,cfg,initialize=True)
            (root/'state.sqlite').unlink()
            with self.assertRaises(ValueError):State(root,cfg)
            with self.assertRaises(ValueError):State(root,cfg,initialize=True)
            self.assertFalse((root/'state.sqlite').exists())

    def test_tampering_and_inference_outcome_market_isolation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);state,key,clock,backend=setup(root/'state');engine=cloud.Engine(state,backend,True);engine.advance(key)
            clock[0]=cloud.windows(state.job(key)['game'],state.config)['target']+1
            original=Path.open
            def guarded(p,*a,**kw):
                if 'market' in p.parts or p.name in ('evaluation.csv','outcome.json'):raise AssertionError('Leakage')
                return original(p,*a,**kw)
            with patch.object(Path,'open',guarded):engine.advance(key)
            cloud.export_replay(state,key,root/'public');(root/'public/audit.json').write_text('{}')
            with self.assertRaises(ValueError):cloud.replay_public(root/'public')
            stage=state.job_dir(key)/'news/result.json';stage.write_text('{}')
            with self.assertRaises(ValueError):state.artifact(key,'news')

    def test_native_provider_requests_cache_v2_identity_and_first403(self):
        for deny in (False,True):
            with self.subTest(deny=deny),tempfile.TemporaryDirectory() as tmp:
                state,key,clock,backend=setup(Path(tmp),live=True);backend.allow_live=True
                engine=cloud.Engine(state,backend,False);engine.advance(key)
                clock[0]=cloud.windows(state.job(key)['game'],state.config)['target']+1
                count=[0]
                def send(req,**kw):
                    count[0]+=1
                    if deny and count[0]==2:raise urllib.error.HTTPError(req.full_url,403,'Denied',{},io.BytesIO(b'{}'))
                    payload=json.loads(req.data);properties=payload['output_config']['format']['schema']['properties']
                    out={'home_win_probability':.6} if 'home_win_probability' in properties else {'likelihood_ratio':1.25,'evidence_sufficiency':'adequate'} if 'likelihood_ratio' in properties else {'favored_side':'neither','strength':'neutral','evidence_sufficiency':'limited'}
                    return Response({'role':'assistant','model':payload['model'],'stop_reason':'end_turn','usage':{'input_tokens':100,'output_tokens':10},'content':[{'type':'text','text':json.dumps(out)}]})
                op=Mock();op.open.side_effect=send;original=cloud.CloudHTTP.__init__
                def init(instance,*args,**kwargs):kwargs['opener']=op;original(instance,*args,**kwargs)
                with patch.object(cloud.CloudHTTP,'__init__',init),patch.dict(os.environ,{'ANTHROPIC_API_KEY':'synthetic-not-real'}):
                    engine.advance(key);result=state.artifact(key,'forecast');engine.advance(key)
                if deny:
                    self.assertEqual(count[0],2);self.assertFalse(result['primary_pair_available'])
                    with self.assertRaises(ValueError):state.check_circuit('paid')
                else:
                    self.assertEqual(set(result['successful_methods']),set(cloud.native.ORDER));self.assertGreater(count[0],4)
                    self.assertTrue(cloud.replay_job(state,key)['forecasts'])
                self.assertEqual(sum(r['calls'] for r in state.status()['reservations'] if r['kind']=='forecast'),count[0])

    def test_delayed_forecast_response_is_retained_but_ineligible(self):
        with tempfile.TemporaryDirectory() as tmp:
            state,key,clock,backend=setup(Path(tmp),live=True);backend.allow_live=True;engine=cloud.Engine(state,backend,False);engine.advance(key)
            target=cloud.windows(state.job(key)['game'],state.config)['target'];clock[0]=target+1
            op=Mock()
            def send(req,**kw):
                clock[0]=target+901
                return Response({'role':'assistant','model':'claude-haiku-4-5-20251001','stop_reason':'end_turn','usage':{'input_tokens':100,'output_tokens':10},'content':[{'type':'text','text':'{"home_win_probability":0.6}'}]})
            op.open.side_effect=send;original=cloud.CloudHTTP.__init__
            def init(instance,*args,**kwargs):kwargs['opener']=op;original(instance,*args,**kwargs)
            with patch.object(cloud.CloudHTTP,'__init__',init),patch.dict(os.environ,{'ANTHROPIC_API_KEY':'fixture'}):engine.advance(key)
            result=state.artifact(key,'forecast');self.assertFalse(result['timing_eligible']);self.assertFalse(result['primary_pair_available']);self.assertEqual(op.open.call_count,1)

    def test_independent_cloud_market_uses_native_quote_rule_and_replays(self):
        with tempfile.TemporaryDirectory() as tmp:
            state,key,clock,backend=setup(Path(tmp),live=True);g=state.job(key)['game'];w=cloud.windows(g,state.config);clock[0]=w['target']-55
            folder=state.job_dir(key)/'market';backend.seed(folder,g)
            event=cloud_market.event_ticker(g)
            ms={'milestones':[{'type':'basketball_game','related_event_tickers':[event],'start_date':g['recorded_start_utc'],'details':{'home_team_id':'fixture-home'}}]}
            quote={'market':{'ticker':event+'-'+g['home_code'],'event_ticker':event,'custom_strike':{'basketball_team':'fixture-home'},'status':'active','open_time':cloud.iso(w['target']-999),'close_time':g['recorded_start_utc'],'yes_bid_dollars':'0.5','yes_ask_dollars':'0.6'}}
            op=Mock();op.open.side_effect=[Response(ms),Response(quote)]
            def docs(folder,policy,state,key,slot,cutoff):return cloud.native.OneShotDocuments(folder,False,policy,clock=state.clock,opener=op)
            session=cloud.SourceSession(folder/'raw',True)
            def sleep(seconds):clock[0]+=seconds
            with patch.object(cloud_market,'TargetSession',return_value=session),patch.object(cloud_market,'CloudDocuments',side_effect=docs),patch.object(cloud_market,'check_assets'):
                result=cloud_market.MarketEngine(state,True,sleep).advance(key)
            self.assertTrue(result['eligible'],result);self.assertEqual(op.open.call_count,2)
            self.assertEqual(cloud_market.verify_source_capture(folder,'quote')['deviation_seconds'],-5)
            self.assertFalse(state.has(key,'baseline'))

    def test_late_market_is_missing_without_invalidating_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            state,key,clock,backend,proof=simulate(Path(tmp))
            clock[0]=cloud.windows(state.job(key)['game'],state.config)['target']+1
            result=cloud_market.MarketEngine(state,False).advance(key)
            self.assertFalse(result['eligible']);self.assertTrue(state.artifact(key,'forecast')['primary_pair_available'])

    def test_benchmark_denial_is_not_an_evidence_or_paid_provider_denial(self):
        with tempfile.TemporaryDirectory() as tmp:
            state,key,clock,backend=setup(Path(tmp));op=Mock();u='https://api.elections.kalshi.com/trade-api/v2/markets/fixture'
            op.open.side_effect=urllib.error.HTTPError(u,403,'Denied',{},io.BytesIO(b'blocked'))
            docs=cloud.CloudDocuments(state.job_dir(key)/'market-fixture',lambda value:value==u,state,key,'market',clock[0]+10,opener=op)
            with self.assertRaises(ValueError):docs.get(u)
            state.check_circuit('paid');state.check_circuit('network')
            with self.assertRaises(ValueError):docs.get(u+'-other')
            self.assertEqual(op.open.call_count,1)

    def test_two_overlapping_game_pipelines_keep_separate_packets_and_groups(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg=json.loads(cloud.CONFIG.read_text());clock=[fixtures.T+20];state=State(Path(tmp),cfg,lambda:clock[0],True)
            game=cloud.discovery.project(fixtures.event(start=cloud.iso(fixtures.T+86520)))
            auth=state.authorize(['900','901'],2,2.7,True);keys=[state.enroll(dict(game,game_id=i),auth) for i in ('900','901')]
            engine=cloud.Engine(state,FixtureBackend(state),True)
            for key in keys:engine.advance(key)
            clock[0]=cloud.windows(game,cfg)['target']+1
            for key in keys:engine.advance(key)
            self.assertTrue(all(state.artifact(k,'forecast')['primary_pair_available'] for k in keys))
            self.assertNotEqual(*(state.artifact(k,'freeze')['packet_sha256'] for k in keys))
            self.assertTrue(all(cloud.replay_job(state,k)['forecasts'] for k in keys))

    def test_no_eligible_article_skips_model_and_never_implies_health(self):
        with tempfile.TemporaryDirectory() as tmp:
            state,key,clock,backend=setup(Path(tmp));game=state.job(key)['game'];folder=state.job_dir(key)/'capture'
            acquisition=backend.news(key,folder);acquisition['sources_and_validation']=[];acquisition['context']['sources']=[]
            acquisition['context_sha256']=digest(canonical(acquisition['context']))
            provider=Mock();provider.usage=[];provider.http.calls=[];provider.extract.side_effect=AssertionError('No source -> no model')
            result=cloud_news.extract(game,acquisition,provider,cloud.windows(game,state.config)['target'],clock[0]+100,state.config['research'],folder,state.clock)
            self.assertEqual(result['news']['state'],'no_usable_evidence');self.assertIn('does_not_imply',result['news']['missing_reason'])

    def test_deployment_gates_and_monitor_heartbeats_do_not_enroll_jobs(self):
        root=Path(__file__).resolve().parents[1]
        for lane in ('evidence','market'):
            unit=(root/'deploy/cloud-news'/('nba-cloud-'+lane+'.service')).read_text()
            for value in ('ConditionPathExists=/etc/nba-cloud/activated','RequiresMountsFor=/var/lib/nba-cloud-news','NTPSynchronized','ProtectSystem=strict'):
                self.assertIn(value,unit)
        self.assertNotIn('secrets.env',(root/'deploy/cloud-news/nba-cloud-market.service').read_text())
        with tempfile.TemporaryDirectory() as tmp:
            state=State(Path(tmp),json.loads(cloud.CONFIG.read_text()),initialize=True)
            state.heartbeat('evidence');state.heartbeat('market');state.heartbeat('evidence')
            self.assertEqual(state.status()['jobs'],0);self.assertEqual(len(state.status()['heartbeat']),2)


if __name__=='__main__':
    if len(sys.argv)>1 and sys.argv[1]=='--export-simulation':
        root=Path(sys.argv[2]);output=Path(sys.argv[3]);_,_,_,_,proof=simulate(root,output);print(json.dumps(proof))
    else:unittest.main()
