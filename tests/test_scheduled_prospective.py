import copy
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import scheduled_prospective as pilot
import scheduled_market as market
from evidence_documents import canonical, digest
from forecast_split import immutable_json
import test_prospective_pipeline as sources
from test_prospective_discovery import opener
from test_prospective_study import live_fixture


def job_fixture(root, captured=False):
    p, line, run = live_fixture(root)
    if not captured:
        # Keep the immutable fixture under a different path for missed-window tests.
        (root / "evidence").rename(root / "unused_fixture")
    game = run["game"]; t = pilot.study.aware(game["recorded_start_utc"]) - 86400
    config = json.loads(pilot.CONFIG.read_text())
    job = {"job_id": "synthetic-scheduler-job", "mode": "fixture_only", "game": game,
        "plan": pilot.plan_for(game, t-1000, config), "config": config, "assets": {}, "allow_inference": True,
        "labels": {p: "org.test.nba."+p for p in ("evidence", "market")},
        "parent_journals": {str(p.relative_to(pilot.ROOT)): digest(p.read_bytes()) for p in (pilot.study.STOP, pilot.discovery.STOP) if p.exists()}}
    immutable_json(root / "job.json", job)
    immutable_json(root / "job_manifest.json", {"job.json": digest((root/"job.json").read_bytes())})
    return job, t


class ScheduledPilotTests(unittest.TestCase):
    def context(self, root):
        return (patch.object(pilot, "BASE", root), patch.object(pilot, "STOP", root/"denial.json"),
            patch.object(pilot, "assets", return_value={}), patch.object(pilot, "retire"))

    def test_next_game_rule_utc_dst_and_plists_have_no_credentials(self):
        g = pilot.discovery.project(sources.event(start="2026-11-02T00:00:00Z")); t=pilot.study.aware(g['recorded_start_utc'])-86400
        cfg=json.loads(pilot.CONFIG.read_text())
        self.assertEqual(pilot.choose_future([g],t-420,cfg),g)
        self.assertIsNone(pilot.choose_future([g],t-419,cfg))
        plan=pilot.plan_for(g,t-1000,cfg)
        self.assertEqual(plan['target_cutoff_utc'],'2026-11-01T00:00:00Z')
        equivalent=dict(g,recorded_start_utc='2026-11-01T19:00:00-05:00')
        self.assertEqual(pilot.plan_for(equivalent,t-1000,cfg)['evidence_launch_utc'],plan['evidence_launch_utc'])
        job={'game':g,'plan':plan,'labels':{'evidence':'fixture.evidence','market':'fixture.market'}}
        spec=pilot.launch_spec(job,'evidence')
        self.assertFalse(spec['KeepAlive']);self.assertTrue(spec['RunAtLoad'])
        self.assertIn('--allow-inference',spec['ProgramArguments']);self.assertNotIn('EnvironmentVariables',spec)
        self.assertNotIn('--allow-inference',pilot.launch_spec(job,'market')['ProgramArguments'])
        for delta,expected in ((-121,'pending'),(-120,'due'),(0,'due'),(.001,'missed_source_cutoff'),(301,'missed_source_cutoff')):
            self.assertEqual(pilot.phase_due(job,'evidence',t+delta),expected)

    def test_persistent_phase_lock(self):
        with tempfile.TemporaryDirectory() as tmp:
            with pilot.lock(tmp,'same'):
                with self.assertRaises(ValueError):
                    with pilot.lock(tmp,'same'):pass
            with pilot.lock(tmp,'same'):pass

    def test_early_wake_no_claim_or_network(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);job,t=job_fixture(root); a,b,c,d=self.context(root)
            with a,b,c,d,patch.object(pilot,'revalidate',side_effect=AssertionError('No early network')),patch.object(pilot,'forecast',side_effect=AssertionError('No early inference')):
                self.assertEqual(pilot.run_evidence(lambda:t-121)['status'],'pending')
                self.assertFalse((root/'capture_claim.json').exists())

    def test_missed_window_durable_and_never_retries(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);job,t=job_fixture(root);a,b,c,d=self.context(root)
            with a,b,c,d,patch.object(pilot,'revalidate',side_effect=AssertionError('No late network')):
                result=pilot.run_evidence(lambda:t+1)
                self.assertIn('missed_source_cutoff',result['reason'])
                self.assertEqual(pilot.run_evidence(lambda:t+400),result)
                self.assertFalse((root/'capture_claim.json').exists())

    def test_reschedule_or_cancellation_blocks_capture_and_paid_inference(self):
        for reason in ('changed tipoff','STATUS_POSTPONED','STATUS_CANCELED'):
            with self.subTest(reason=reason),tempfile.TemporaryDirectory() as tmp:
                root=Path(tmp);job,t=job_fixture(root);a,b,c,d=self.context(root)
                with a,b,c,d,patch.object(pilot,'revalidate',side_effect=ValueError(reason)),patch.object(pilot,'freeze_evidence',side_effect=AssertionError('No changed-fixture collection')),patch.object(pilot,'forecast',side_effect=AssertionError('No inference')):
                    result=pilot.run_evidence(lambda:t-100);self.assertEqual(result['reason'],reason)
                    self.assertTrue((root/'capture_claim.json').exists())

    def test_interrupted_capture_claim_never_recollects(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);job,t=job_fixture(root);immutable_json(root/'capture_claim.json',{'uncertain':True});a,b,c,d=self.context(root)
            with a,b,c,d,patch.object(pilot,'revalidate',side_effect=AssertionError('No repeat retrieval')):
                self.assertIn('Interrupted capture claim',pilot.run_evidence(lambda:t-100)['reason'])

    def test_delayed_revalidation_misses_cutoff_without_collection(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);job,t=job_fixture(root);a,b,c,d=self.context(root);now=[t-100]
            def late(*args):now[0]=t+1
            with a,b,c,d,patch.object(pilot,'revalidate',side_effect=late),patch.object(pilot,'freeze_evidence',side_effect=AssertionError('No late source capture')):
                self.assertIn('missed source cutoff',pilot.run_evidence(lambda:now[0])['reason'])
                self.assertFalse((root/'reservations').exists())

    def test_deterministic_freeze_has_explicit_injury_and_news_missingness_no_paid_calls(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);original=sources.event
            def event(*a,**kw):return original(*a,**kw) if a or kw else original(start=pilot.iso(sources.T+86520))
            with patch.object(sources,'event',event):sources.fixture(root/'evidence')
            game=pilot.discovery.project(event());cfg=json.loads(pilot.CONFIG.read_text())
            job={'job_id':'fixture-only','game':game,'parent_journals':{},'plan':pilot.plan_for(game,sources.T,cfg)}
            (root/'revalidation').mkdir();immutable_json(root/'revalidation/discovery.json',{'fixture':True})
            a,b,c,d=self.context(root);session=pilot.study.SourceSession(root/'evidence/raw',True)
            with a,b,c,d,patch.object(pilot,'check_stops'),patch.object(pilot.study,'StudySession',return_value=session),patch('prospective_sources.parse_pdf',side_effect=sources.parsed_fixture),patch('urllib.request.OpenerDirector.open',side_effect=AssertionError('No live API')):
                packet=pilot.freeze_evidence(job,pilot.JobBudget(root,stop_path=root/'denial.json'),clock=lambda:sources.T+20)
                self.assertEqual(packet['injury_news']['official_injury']['away']['state'],'not_yet_submitted')
                self.assertEqual(packet['injury_news']['news']['state'],'not_collected')
                self.assertIn('paid_news_not_collected',packet['injury_news']['news']['missing_reason'])
                self.assertNotIn('Kalshi',json.dumps(packet));self.assertNotIn('999',json.dumps(packet))
                self.assertEqual(pilot.valid_capture(job)['evidence_snapshot_sha256'],packet['evidence_snapshot_sha256'])

    def test_frozen_packet_all_native_methods_same_parent_no_market_reads(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);job,t=job_fixture(root,True);a,b,c,d=self.context(root)
            original=pilot.study.forecast_bundle; native_open=Path.open
            def guard(path,*args,**kw):
                if 'market' in path.parts or path.name=='evaluation.csv':raise AssertionError('Evaluation/market read')
                return native_open(path,*args,**kw)
            def native(*args,**kw):
                kw.update(mock=True,caches={n:root/'cache'/n for n in pilot.study.ORDER});kw.pop('transport_factory',None)
                return original(*args,**kw)
            with a,b,c,d,patch.object(pilot,'load_credentials'),patch.object(pilot.study,'forecast_bundle',side_effect=native),patch.object(Path,'open',guard),patch('urllib.request.OpenerDirector.open',side_effect=AssertionError('No live mock')):
                result=pilot.run_evidence(lambda:t+2);self.assertEqual(result['status'],'sealed_complete',result)
                verified=pilot.study.verify_forecasts(root/'evidence',root/'forecasts')
                self.assertEqual({r['evidence_sha256'] for r in verified['records'].values()},{result['packet_sha256']})
                self.assertEqual(pilot.run_evidence(lambda:t+4),result)

    def test_interrupted_inference_only_offline_seal_and_never_resends(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);job,t=job_fixture(root,True);a,b,c,d=self.context(root)
            immutable_json(root/'inference_claim.json',{'uncertain':True})
            with a,b,c,d,patch.object(pilot,'load_credentials',side_effect=AssertionError('No new paid credentials')):
                budget=pilot.JobBudget(root,stop_path=root/'denial.json')
                self.assertIn('uncertain',pilot.forecast(job,budget,lambda:t+2)['stop_reason'])
                (root/'forecasts').mkdir();immutable_json(root/'forecasts/run.json',{'fixture':True})
                with patch.object(pilot.study,'forecast_bundle',return_value={'offline':True}) as sealed:
                    self.assertEqual(pilot.forecast(job,budget,lambda:t+2),{'offline':True});self.assertTrue(sealed.call_args.kwargs['seal_only'])

    def test_tipoff_incomplete_evidence_and_job_tampering_block_calls(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);job,t=job_fixture(root,True);a,b,c,d=self.context(root)
            with a,b,c,d,patch.object(pilot,'load_credentials',side_effect=AssertionError('No after-tipoff inference')):
                with self.assertRaises(ValueError):pilot.forecast(job,pilot.JobBudget(root),lambda:t+86400)
                with patch.object(pilot,'valid_capture',side_effect=ValueError('incomplete source coverage')):
                    self.assertIn('incomplete',pilot.run_evidence(lambda:t+2)['reason'])
                (root/'job.json').write_text('{}')
                with self.assertRaises(ValueError):pilot.load_job()

    def test_new_paid_403_journal_blocks_every_following_reservation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);a,b,c,d=self.context(root)
            with a,b,c,d:
                budget=pilot.JobBudget(root,stop_path=root/'denial.json');budget.reserve('one','anthropic',.1)
                budget.stop('access_denial',http_status=403,provider='anthropic')
                with self.assertRaises(pilot.study.Halt):budget.reserve('two','anthropic',.1)
                self.assertEqual(len(budget.entries()),1)
                with self.assertRaises(pilot.study.Halt):pilot.check_stops()

    def test_bound_journal_cannot_be_removed_and_cost_reservations_are_bounded(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);a,b,c,d=self.context(root);parent=root/'parent.json';parent.write_text('{}')
            parents={str(p.relative_to(pilot.ROOT)):digest(p.read_bytes()) for p in (pilot.study.STOP,pilot.discovery.STOP) if p.exists()}
            job={'parent_journals':{**parents,str(parent):digest(parent.read_bytes())}}
            with a,b,c,d:
                pilot.check_stops(job);parent.unlink()
                with self.assertRaises(pilot.study.Halt):pilot.check_stops(job)
                budget=pilot.JobBudget(root,stop_path=root/'denial.json');budget.reserve('first','anthropic',.99)
                with self.assertRaises(pilot.study.Halt):budget.reserve('over','anthropic',.02)
                self.assertEqual(len(budget.entries()),1)

    def test_delayed_seal_is_explicitly_ineligible(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);job,t=job_fixture(root,True);a,b,c,d=self.context(root)
            with a,b,c,d,patch.object(pilot,'forecast',return_value={'before_tipoff':False,'successful_methods':['direct','v1','v2']}):
                self.assertEqual(pilot.run_evidence(lambda:t+2)['status'],'sealed_ineligible_after_tipoff')

    def test_independent_market_actual_clock_and_offline_quote_replay(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);job,t=job_fixture(root);a,b,c,d=self.context(root);now=[t-55]
            g=job['game'];ev=market.evaluation.event_ticker(g)
            milestone={'milestones':[{'type':'basketball_game','related_event_tickers':[ev],'start_date':g['recorded_start_utc'],'details':{'home_team_id':'fixture-home'}}]}
            quote={'market':{'ticker':ev+'-'+g['home_code'],'event_ticker':ev,'custom_strike':{'basketball_team':'fixture-home'},'status':'active','open_time':pilot.iso(t-5000),'close_time':g['recorded_start_utc'],'yes_bid_dollars':'0.5','yes_ask_dollars':'0.6'}}
            mu=pilot.discovery.url(market.MARKET_BASE+'/milestones',limit=100,related_event_ticker=ev);qu=market.MARKET_BASE+'/markets/'+ev+'-'+g['home_code']
            op=opener({mu:(200,milestone),qu:(200,quote)});real=pilot.study.OneShotDocuments
            def store(*args,**kw):return real(*args,**kw,opener=op)
            def sleep(seconds):now[0]+=seconds
            with a,b,c,d,patch.object(pilot,'revalidate'),patch.object(pilot.study,'OneShotDocuments',side_effect=store):
                result=market.run(lambda:now[0],sleep);self.assertTrue(result['eligible'],result)
                saved=market.evaluation.verify_source_capture(root/'market','quote');self.assertAlmostEqual(saved['midpoint'],.55)
                self.assertEqual(saved['deviation_seconds'],-5);self.assertFalse(saved['exact_cutoff_observation'])
                self.assertEqual(op.open.call_count,2);self.assertEqual(market.run(lambda:now[0]),result)

    def test_late_market_missing_without_reading_evidence_or_paid_calls(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);job,t=job_fixture(root);a,b,c,d=self.context(root)
            with a,b,c,d,patch.object(pilot,'revalidate',side_effect=AssertionError('No late market retrieval')):
                result=market.run(lambda:t+.01);self.assertFalse(result['eligible']);self.assertIn('missed_source_cutoff',result['missing_reason'])
                self.assertFalse((root/'market/quote.json').exists());self.assertFalse((root/'reservations').exists())


if __name__=='__main__':unittest.main()
