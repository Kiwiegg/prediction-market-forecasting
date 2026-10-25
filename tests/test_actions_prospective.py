import copy
import json
import os
import sys
import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import actions_campaign as campaign
import actions_prospective as actions
import cloud_prospective as cloud
from actions_storage import Checkpoints, RemoteState, StorageStop, S3Objects
from cloud_state import durable_json
from evidence_documents import canonical, digest
from test_cloud_news_pipeline import FixtureBackend
import test_prospective_pipeline as fixtures


class Objects:
    """Atomic conditional-write fixture, NOT a live R2/S3 validation."""
    def __init__(self):self.data={};self.lock=threading.Lock();self.fail=False;self.fail_after_root=False;self.writes=0;self.reads=0
    def read(self,key):
        with self.lock:
            self.reads+=1
            return self.data.get(key,(None,None))
    def write(self,key,body,etag=None,create=False):
        with self.lock:
            if self.fail:raise StorageStop('synthetic storage failure')
            old=self.data.get(key)
            if create and old:
                if old[0]==body:return old[1]
                raise StorageStop('exists')
            if not create and (old is None or old[1]!=etag):raise StorageStop('CAS conflict')
            tag=digest(body);self.data[key]=(body,tag);self.writes+=1
            if self.fail_after_root and key=='root.json':raise StorageStop('Root accepted but response lost')
            return tag


def setup(path):
    cfg=json.loads(cloud.CONFIG.read_text());game=cloud.discovery.project(fixtures.event(start=cloud.iso(fixtures.T+86520)))
    clock=[cloud.windows(game,cfg)['collect']-10]
    objects=Objects();cp=Checkpoints(objects);cp.open('fixture-run',True);cp.restore(path)
    state=campaign.CampaignState(path,cfg,cp,lambda:clock[0],True)
    return state,game,clock,objects,cp


def approve(state,game,clock):
    state.approve([game['game_id']],cloud.iso(clock[0]+86400),mock=True)
    auth=state.authorize([game['game_id']],mock=True);return state.enroll(game,auth)


def simulate_actions(directory,output):
    directory=Path(directory);output=Path(output)
    state,game,clock,objects,cp=setup(directory/'first');key=approve(state,game,clock)
    engine=cloud.Engine(state,FixtureBackend(state),True)
    with patch('urllib.request.OpenerDirector.open',side_effect=AssertionError('No live network')):
        for phase in ('collect','refresh','target'):
            clock[0]=cloud.windows(game,state.config)[phase]+(1 if phase=='target' else 0)
            engine.advance(key)
        before=cloud.replay_job(state,key);state.sync();cp.close()
        resumed=Checkpoints(objects,state.uuid);resumed.open('synthetic-restart');resumed.restore(directory/'restored')
        restored=campaign.CampaignState(directory/'restored',state.config,resumed,lambda:clock[0])
        after=cloud.replay_job(restored,key);cloud.export_replay(restored,key,output/'simulation')
    result={'mode':'offline_mock','live_evaluation_eligible':False,'real_provider_requests':0,'actual_provider_cost_usd':0,
            'before_restore':before,'after_restore':after,'campaign':campaign.campaign_report(restored),
            'fixture_object_operations':{'reads':objects.reads,'writes':objects.writes,'objects':len(objects.data)},
            'scope':'In-memory conditional-write fixture; synthetic raw sources and mock LLM only. Not a live storage or Actions validation.'}
    durable_json(output/'simulation_validation.json',result)
    return result


class ActionsTests(unittest.TestCase):
    def test_remote_claim_before_return_and_restore_without_resend(self):
        with tempfile.TemporaryDirectory() as tmp:
            state,game,clock,objects,cp=setup(Path(tmp)/'first');key=approve(state,game,clock)
            clock[0]+=10;state.reserve('unique',key,'forecast',.01)
            cp.close();cp2=Checkpoints(objects,state.uuid);cp2.open('new-run');cp2.restore(Path(tmp)/'restart')
            restored=campaign.CampaignState(Path(tmp)/'restart',state.config,cp2,lambda:clock[0])
            with restored.db() as c:self.assertEqual(c.execute('SELECT count(*) FROM requests WHERE id="unique"').fetchone()[0],1)
            with self.assertRaises(ValueError):restored.reserve('unique',key,'forecast',.01)

    def test_duplicate_owner_invocations_and_stale_owner_fenced(self):
        objects=Objects();one=Checkpoints(objects);one.open('run-1',True)
        with self.assertRaises(StorageStop):Checkpoints(objects).open('run-2')
        raw,tag=objects.read('root.json');root=json.loads(raw);root['owner']={'run':'external','nonce':'different'}
        objects.write('root.json',canonical(root),tag)
        with self.assertRaises(StorageStop):one.assert_owner()

    def test_crashed_owner_no_expiry_takeover_and_explicit_recovery(self):
        objects=Objects();one=Checkpoints(objects);store=one.open('run-1',True);owner=one.owner
        with self.assertRaises(StorageStop):Checkpoints(objects,store).open('run-2')
        with self.assertRaises(ValueError):actions.recover_owner(objects,store,json.dumps(owner),'unconfirmed')
        actions.recover_owner(objects,store,json.dumps(owner),'CONFIRMED_OLD_RUNNER_TERMINATED')
        Checkpoints(objects,store).open('run-2')
        self.assertTrue(any(k.startswith('recoveries/') for k in objects.data))

    def test_storage_ambiguity_poisoned_before_paid_send(self):
        with tempfile.TemporaryDirectory() as tmp:
            state,game,clock,objects,cp=setup(Path(tmp));key=approve(state,game,clock);clock[0]+=10
            objects.fail=True;sent=[]
            with self.assertRaises(StorageStop):
                state.reserve('will-not-send',key,'forecast',.01);sent.append(True)
            self.assertFalse(sent);self.assertTrue(cp.poisoned)
            with self.assertRaises(StorageStop):state.reserve('also-no-send',key,'forecast',.01)

    def test_accepted_remote_claim_with_lost_ack_never_resends(self):
        with tempfile.TemporaryDirectory() as tmp:
            state,game,clock,objects,cp=setup(Path(tmp)/'one');key=approve(state,game,clock);clock[0]+=10
            objects.fail_after_root=True
            with self.assertRaises(StorageStop):state.reserve('lost-ack',key,'forecast',.01)
            self.assertTrue(cp.poisoned);objects.fail_after_root=False
            owner=json.loads(objects.read('root.json')[0])['owner']
            actions.recover_owner(objects,state.uuid,json.dumps(owner),'CONFIRMED_OLD_RUNNER_TERMINATED')
            new=Checkpoints(objects,state.uuid);new.open('after-confirmed-stop');new.restore(Path(tmp)/'two')
            resumed=campaign.CampaignState(Path(tmp)/'two',state.config,new,lambda:clock[0])
            with self.assertRaises(ValueError):resumed.reserve('lost-ack',key,'forecast',.01)

    def test_expired_missing_and_mode_mismatched_authorization(self):
        with tempfile.TemporaryDirectory() as tmp:
            state,game,clock,objects,cp=setup(Path(tmp))
            with self.assertRaises(ValueError):state.campaign()
            key=approve(state,game,clock)
            live_auth=state.authorize([game['game_id']],mock=False)
            with self.assertRaises(ValueError):state.enroll(game,live_auth)
            clock[0]+=90000
            with self.assertRaises(ValueError):state.reserve('expired',key,'forecast',.01)

    def test_concurrent_atomic_campaign_cap_and_unknown_usage_retained(self):
        with tempfile.TemporaryDirectory() as tmp:
            state,game,clock,objects,cp=setup(Path(tmp));key=approve(state,game,clock);clock[0]+=10
            with state.db() as c:c.execute('INSERT INTO requests VALUES(?,?,?,?,?)',('old-unknown','prior','forecast',49.90,'claimed'))
            def claim(i):
                try:state.reserve(str(i),key,'forecast',.06);return True
                except ValueError:return False
            with ThreadPoolExecutor(max_workers=2) as pool:self.assertEqual(sum(pool.map(claim,range(2))),1)
            with state.db() as c:self.assertAlmostEqual(c.execute('SELECT sum(usd) FROM requests').fetchone()[0],49.96)

    def test_per_game_research_forecast_and_global_budget_caps(self):
        with tempfile.TemporaryDirectory() as tmp:
            state,game,clock,objects,cp=setup(Path(tmp));key=approve(state,game,clock);clock[0]+=10
            state.reserve('research',key,'extraction',.35);state.reserve('forecast',key,'forecast',1)
            with self.assertRaises(ValueError):state.reserve('over-game',key,'search',.01)
            with self.assertRaises(ValueError):state.reserve('over-forecast',key,'forecast',.01)

    def test_denial_journal_survives_runner_restore(self):
        with tempfile.TemporaryDirectory() as tmp:
            state,game,clock,objects,cp=setup(Path(tmp)/'first');key=approve(state,game,clock)
            state.circuit('paid',http_status=403);cp.close()
            cp2=Checkpoints(objects,state.uuid);cp2.open('restart');cp2.restore(Path(tmp)/'second')
            restored=campaign.CampaignState(Path(tmp)/'second',state.config,cp2,lambda:clock[0])
            with self.assertRaises(ValueError):restored.reserve('denied',key,'forecast',.01)
            self.assertTrue(list((restored.root/'circuits').glob('*.json')))

    def test_strict_dispatch_timing_late_and_overlapping_enrollment(self):
        with tempfile.TemporaryDirectory() as tmp:
            state,game,clock,objects,cp=setup(Path(tmp));state.approve([game['game_id']],cloud.iso(clock[0]+86400),mock=True)
            early=actions.timing_plan([game],clock[0],state.config);self.assertEqual(early[0]['status'],'wait_on_runner')
            deferred=campaign.enroll_catalog(state,{'games':[game]},cloud.windows(game,state.config)['forecast']-1)
            self.assertEqual(deferred[0]['reason'],'handoff_to_later_dispatch')
            clock[0]+=11
            self.assertEqual(actions.timing_plan([game],clock[0],state.config)[0]['status'],'missed_no_backfill')
            result=campaign.enroll_catalog(state,{'games':[game]})
            self.assertEqual(result[0]['reason'],'missed_collection_start_no_backfill');self.assertFalse(state.jobs())
        with tempfile.TemporaryDirectory() as tmp:
            state,game,clock,objects,cp=setup(Path(tmp));other=copy.deepcopy(game);other['game_id']='901'
            # Pure enrollment fixture approval: no mock pretends to satisfy live gate.
            state.approve([game['game_id']],cloud.iso(clock[0]+86400),mock=True)
            base=state.campaign();synthetic={**base,'game_ids':['900','901'],'max_games':2,'automatic_enrollment':True}
            with patch.object(state,'campaign',return_value=synthetic):
                results=campaign.enroll_catalog(state,{'games':[other,game]})
            self.assertEqual([r['game_id'] for r in results],['900','901']);self.assertEqual(len(state.jobs()),2)
            self.assertEqual(campaign.enroll_catalog(state,{'games':[game]})[0]['reason'],'already_enrolled')

    def test_delayed_workflow_marks_existing_job_missed_without_backend_calls(self):
        with tempfile.TemporaryDirectory() as tmp:
            state,game,clock,objects,cp=setup(Path(tmp));key=approve(state,game,clock);clock[0]+=11
            with patch.object(actions,'catalog',return_value={'games':[game]}),patch.object(cloud.LiveBackend,'collect',side_effect=AssertionError('No late source call')):
                result=actions.run_worker(state)
            self.assertTrue(state.has(key,'workflow_missed'));self.assertFalse(state.has(key,'baseline'))
            self.assertEqual(result['primary_eligible'],0);self.assertEqual(result['reserved_usd'],0)

    def test_global_circuit_stops_worker_before_discovery(self):
        with tempfile.TemporaryDirectory() as tmp:
            state,game,clock,objects,cp=setup(Path(tmp));approve(state,game,clock);state.circuit('paid',http_status=403)
            with patch.object(actions,'catalog',side_effect=AssertionError('No calls after denial')):
                with self.assertRaises(ValueError):actions.run_worker(state)

    def test_no_multi_game_activation_from_mock_success(self):
        with tempfile.TemporaryDirectory() as tmp:
            state,game,clock,objects,cp=setup(Path(tmp));key=approve(state,game,clock)
            clock[0]=cloud.windows(game,state.config)['collect'];engine=cloud.Engine(state,FixtureBackend(state),True)
            engine.advance(key);clock[0]=cloud.windows(game,state.config)['refresh'];engine.advance(key)
            clock[0]=cloud.windows(game,state.config)['target']+1;engine.advance(key)
            self.assertTrue(cloud.replay_job(state,key)['forecasts']);self.assertFalse(state.first_success())
            with self.assertRaises(ValueError):state.expand(cloud.iso(clock[0]+86400),30,50,True)
            report=campaign.campaign_report(state);self.assertEqual(report['primary_eligible'],0)
            self.assertEqual({r['evidence_sha256'] for r in state.artifact(key,'forecast')['records'].values()},
                             {state.artifact(key,'freeze')['packet_sha256']})

    def test_full_private_checkpoint_restoration_and_sanitized_native_replay(self):
        with tempfile.TemporaryDirectory() as tmp:
            result=simulate_actions(Path(tmp)/'private',Path(tmp)/'public')
            self.assertTrue(result['after_restore']['forecasts']);self.assertEqual(result['before_restore']['packet_sha256'],result['after_restore']['packet_sha256'])
            self.assertTrue(cloud.replay_public(Path(tmp)/'public/simulation')['verified'])
            self.assertEqual(result['campaign']['primary_eligible'],0)

    def test_missing_secrets_and_clock_fail_before_storage_or_provider(self):
        with self.assertRaises(ValueError):actions.preflight({},clock_check=False)
        env={k:'synthetic' for k in ('NBA_ACTIONS_BUCKET','AWS_REGION','NBA_ACTIONS_STORE_UUID','BRAVE_SEARCH_API_KEY','ANTHROPIC_API_KEY')}
        actions.preflight(env,clock_check=False)
        with patch.object(actions.subprocess,'run',return_value=Mock(returncode=0,stdout='no\n')):
            with self.assertRaises(ValueError):actions.preflight(env)

    def test_corrupt_blob_path_and_missing_root_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            state,game,clock,objects,cp=setup(Path(tmp)/'one');cp.close()
            raw,_=objects.read('root.json');snapshot=json.loads(raw)['snapshot'];manifest=json.loads(objects.read('snapshots/'+snapshot)[0])
            sha=next(iter(manifest['files'].values()));objects.data['blobs/'+sha]=(b'changed','tag')
            cp2=Checkpoints(objects,state.uuid);cp2.open('two')
            with self.assertRaises(StorageStop):cp2.restore(Path(tmp)/'two')
        with self.assertRaises(StorageStop):Checkpoints(Objects(),'known').open('run')
        with self.assertRaises(StorageStop):Checkpoints(Objects(),'known').open('run',True)

    def test_stage_interruption_and_completed_native_record_immutable(self):
        with tempfile.TemporaryDirectory() as tmp:
            state,game,clock,objects,cp=setup(Path(tmp)/'one');key=approve(state,game,clock)
            with self.assertRaises(ValueError):state.stage(key,'source',lambda p:(_ for _ in ()).throw(ValueError('interrupted')))
            with self.assertRaises(ValueError):state.stage(key,'source',lambda p:{'retry':True})
            state.stage(key,'done',lambda p:{'fixture':'unchanged'})
            marker=state.job_dir(key)/'done/result.json';before=marker.read_bytes()
            self.assertEqual(state.stage(key,'done',lambda p:1),{'fixture':'unchanged'});self.assertEqual(marker.read_bytes(),before)

    def test_reserved_deadline_elapsed_never_sends(self):
        with tempfile.TemporaryDirectory() as tmp:
            state,game,clock,objects,cp=setup(Path(tmp));key=approve(state,game,clock)
            clock[0]=cloud.windows(game,state.config)['forecast']-.01
            real=state.sync
            def delayed():real();clock[0]+=.1
            with patch.object(state,'sync',side_effect=delayed):
                with self.assertRaises(ValueError):state.reserve('late-checkpoint',key,'forecast',.01)
            with state.db() as c:self.assertEqual(c.execute('SELECT count(*) FROM requests WHERE id="late-checkpoint"').fetchone()[0],1)

    def test_workflow_disabled_secret_free_dry_run_and_public_capture_isolation(self):
        root=Path(__file__).resolve().parents[1];text=(root/'.github/workflows/prospective-nba.yml').read_text()
        self.assertIn("vars.NBA_ACTIONS_LIVE_ENABLED == 'true'",text)
        self.assertIn('cancel-in-progress: false',text);self.assertIn('github.sha == vars.NBA_ACTIONS_REVIEWED_SHA',text)
        offline=text.split('  offline:',1)[1].split('  private-worker:',1)[0]
        self.assertNotIn('secrets.',offline);self.assertNotIn('upload-artifact@',text)
        self.assertNotIn('pull_request',text);self.assertIn('persist-credentials: false',text)
        self.assertNotIn('kalshi', (root/'scripts/actions_campaign.py').read_text().lower())

    def test_sdk_conditional_calls_no_retries_and_endpoint_restrictions(self):
        boto=Mock();botoconfig=Mock();client=boto.client.return_value;client.put_object.return_value={'ETag':'etag'}
        with patch.dict(sys.modules,{'boto3':boto,'botocore.config':botoconfig}):
            store=S3Objects('private','prefix','auto','https://example.r2.cloudflarestorage.com')
            store.write('root.json',b'{}',etag='old')
            self.assertEqual(client.put_object.call_args.kwargs['IfMatch'],'old')
            self.assertNotIn('ServerSideEncryption',client.put_object.call_args.kwargs)
            store.write('blobs/hash',b'data',create=True)
            self.assertEqual(client.put_object.call_args.kwargs['IfNoneMatch'],'*')
            self.assertEqual(botoconfig.Config.call_args.kwargs['retries'],{'total_max_attempts':1})
            with self.assertRaises(ValueError):S3Objects('private','prefix','auto','https://untrusted.example')


if __name__=='__main__':
    if len(sys.argv)>1 and sys.argv[1]=='--export-simulation':
        print(json.dumps(simulate_actions(sys.argv[2],sys.argv[3]),indent=2))
    else:unittest.main()
