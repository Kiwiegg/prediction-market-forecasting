"""Authorization transitions only: no real providers, games or paid inference."""
import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import actions_campaign as campaign
import actions_prospective as actions
import cloud_prospective as cloud
from actions_gates import evaluate
from actions_storage import Checkpoints,StorageStop
from evidence_documents import canonical,digest
from test_actions_prospective import setup,approve
from test_cloud_news_pipeline import FixtureBackend


def files(root):
    return {str(p.relative_to(root)):digest(p.read_bytes()) for p in root.rglob('*')
            if p.is_file() and not p.name.endswith(('-wal','-shm','.lock'))}


def legacy(path):
    state,game,clock,objects,cp=setup(path);key=approve(state,game,clock)
    original=json.loads((state.root/'campaign.json').read_text())
    original.update(assets_sha256=campaign.renewal_migration()['from_assets_sha256'],expires_at_utc=cloud.iso(clock[0]+20))
    # A fixture representing the immutable pre-migration pilot; no production edit.
    (state.root/'campaign.json').write_bytes(canonical(original))
    for i,usd in enumerate([.02]*6+[.038331,.01,.01]):
        with state.db() as c:c.execute('INSERT INTO requests VALUES(?,?,?,?,?)',(str(i),key,'forecast' if i<7 else 'search',usd,'claimed'))
    state.sync();clock[0]+=21
    return state,key,game,clock,objects,cp


class RenewalTests(unittest.TestCase):
    def test_expired_legacy_approval_never_spends_and_plan_is_read_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            state,key,game,clock,objects,cp=legacy(Path(tmp)/'private')
            with self.assertRaises(ValueError):state.campaign()
            with self.assertRaises(ValueError):state.reserve('expired',key,'forecast',.01)
            before=files(state.root);cp.close();writes=objects.writes;root=objects.read('root.json')[0]
            plan=actions.renewal_plan(objects,state.uuid,Path(tmp)/'inspection',state.config,lambda:clock[0])
            self.assertEqual(objects.writes,writes);self.assertEqual(objects.read('root.json')[0],root)
            self.assertEqual(files(state.root),before)
            self.assertTrue(plan['expired']);self.assertTrue(plan['migration_required'])
            self.assertEqual(plan['request_count'],9);self.assertAlmostEqual(plan['reserved_usd'],.178331)
            self.assertEqual(plan['new_authorizations'],0);self.assertEqual(plan['remote_writes'],0)
            self.assertFalse(plan['automatic_enrollment']);self.assertEqual(plan['max_games'],1)

    def test_explicit_renewal_preserves_scope_claims_denials_and_old_bytes(self):
        with tempfile.TemporaryDirectory() as tmp:
            state,key,game,clock,objects,cp=legacy(Path(tmp))
            state.circuit('paid',http_status=403);before=files(state.root);plan=state.renewal_plan()
            new=state.renew(cloud.iso(clock[0]+86400),plan['predecessor_sha256'],True,True)
            self.assertEqual(new['previous_sha256'],plan['predecessor_sha256'])
            self.assertEqual(new['operational_migration'],campaign.renewal_migration())
            for k in ('game_ids','max_games','max_usd','per_game_usd','automatic_enrollment'):
                self.assertEqual(new[k],plan[k])
            self.assertEqual({k:files(state.root)[k] for k in before},before)
            self.assertEqual(state.renewal_plan()['request_ledger_sha256'],plan['request_ledger_sha256'])
            self.assertEqual(state.renewal_plan()['denial_journal_sha256'],plan['denial_journal_sha256'])
            with self.assertRaises(ValueError):state.reserve('denied-after-renew',key,'forecast',.01)

    def test_confirmation_migration_predecessor_and_expiry_required(self):
        with tempfile.TemporaryDirectory() as tmp:
            state,key,game,clock,objects,cp=legacy(Path(tmp));sha=state.renewal_plan()['predecessor_sha256'];end=cloud.iso(clock[0]+86400)
            bad=[(end,sha,False,True),(end,sha,True,False),(end,'0'*64,True,True),
                 (cloud.iso(clock[0]),sha,True,True),(cloud.iso(clock[0]+31*86400+1),sha,True,True),
                 ('2026-10-27T12:00:00',sha,True,True)]
            for args in bad:
                with self.subTest(args=args),self.assertRaises(ValueError):state.renew(*args)
            self.assertFalse((state.root/'campaign_amendments').exists())
            state.renew(end,sha,True,True)
            with self.assertRaises(ValueError):state.renew(end,sha,True,True)
            self.assertEqual(len(list((state.root/'campaign_amendments').glob('*.json'))),1)

    def test_renewed_expiry_is_still_enforced_and_duplicate_claim_never_reused(self):
        with tempfile.TemporaryDirectory() as tmp:
            state,key,game,clock,objects,cp=legacy(Path(tmp));sha=state.renewal_plan()['predecessor_sha256']
            state.renew(cloud.iso(clock[0]+60),sha,True,True)
            with self.assertRaises(ValueError):state.reserve('0',key,'forecast',.02)
            clock[0]+=61
            with self.assertRaises(ValueError):state.reserve('expired-again',key,'forecast',.01)
            self.assertEqual(state.renewal_plan()['request_count'],9)
            p=state.renewal_plan()
            # A second same-registry renewal needs fresh approval, not another migration.
            again=state.renew(cloud.iso(clock[0]+60),p['predecessor_sha256'],True)
            self.assertIsNone(again['operational_migration'])
            with self.assertRaises(ValueError):state.reserve('0',key,'forecast',.02)

    def test_expired_live_request_stops_before_http_and_no_claim_is_added(self):
        with tempfile.TemporaryDirectory() as tmp:
            state,game,clock,objects,cp=setup(Path(tmp))
            state.approve([game['game_id']],cloud.iso(clock[0]+1))
            key=state.enroll(game,state.authorize([game['game_id']]))
            clock[0]+=2
            from unittest.mock import Mock
            opener=Mock();opener.open.side_effect=AssertionError('Expired approval cannot send')
            http=cloud.CloudHTTP(state.root/'fixture-http',state,key,'extraction',clock[0]+60,True,opener=opener)
            with self.assertRaises(ValueError):
                http.request('anthropic','POST','https://api.anthropic.com/v1/messages',{'max_tokens':128},{},1000)
            opener.open.assert_not_called()
            self.assertEqual(state.renewal_plan()['request_count'],0)

    def test_expiry_during_checkpoint_keeps_reservation_without_sending(self):
        with tempfile.TemporaryDirectory() as tmp:
            state,game,clock,objects,cp=setup(Path(tmp))
            state.approve([game['game_id']],cloud.iso(clock[0]+1))
            key=state.enroll(game,state.authorize([game['game_id']]))
            real=state.sync
            def delayed():real();clock[0]+=2
            from unittest.mock import Mock
            opener=Mock();opener.open.side_effect=AssertionError('No send after checkpoint expiry')
            http=cloud.CloudHTTP(state.root/'fixture-http',state,key,'extraction',clock[0]+60,True,opener=opener)
            with patch.object(state,'sync',side_effect=delayed),self.assertRaises(ValueError):
                http.request('anthropic','POST','https://api.anthropic.com/v1/messages',{'max_tokens':128},{},1000)
            opener.open.assert_not_called()
            self.assertEqual(state.renewal_plan()['request_count'],1)
            self.assertGreater(state.renewal_plan()['reserved_usd'],0)

    def test_30_cumulative_expansion_is_separate_and_chronological(self):
        with tempfile.TemporaryDirectory() as tmp:
            state,key,game,clock,objects,cp=legacy(Path(tmp));plan=state.renewal_plan()
            state.renew(cloud.iso(clock[0]+86400),plan['predecessor_sha256'],True,True)
            self.assertFalse(state.campaign()['automatic_enrollment']);self.assertEqual(len(state.jobs()),1)
            # Gate substitution tests authorization arithmetic, not genuine live success.
            with self.assertRaises(ValueError):state.expand(cloud.iso(clock[0]+86400),30,50,True)
            with patch.object(state,'first_success',return_value=True):
                expanded=state.expand(cloud.iso(clock[0]+86400),30,50,True)
            self.assertEqual(expanded['max_games'],30);self.assertEqual(expanded['max_usd'],50)
            self.assertTrue(expanded['automatic_enrollment'])
            future=[]
            for i in range(29):
                g=copy.deepcopy(game);g['game_id']=str(1000+i)
                g['recorded_start_utc']=cloud.iso(cloud.native.aware(game['recorded_start_utc'])+3600+i*60)
                future.append(g)
            decisions=campaign.enroll_catalog(state,{'games':list(reversed(future))})
            self.assertEqual([r['game_id'] for r in decisions],[g['game_id'] for g in future])
            self.assertEqual(len(state.jobs()),30)
            extra=copy.deepcopy(future[-1]);extra['game_id']='9999'
            self.assertEqual(campaign.enroll_catalog(state,{'games':[extra]})[0]['reason'],'campaign_game_cap')
            self.assertAlmostEqual(state.renewal_plan()['reserved_usd'],.178331)

    def test_global_and_per_game_caps_not_reset_by_renewal(self):
        with tempfile.TemporaryDirectory() as tmp:
            state,key,game,clock,objects,cp=legacy(Path(tmp));plan=state.renewal_plan()
            state.renew(cloud.iso(clock[0]+86400),plan['predecessor_sha256'],True,True)
            with self.assertRaises(ValueError):state.reserve('over-research',key,'search',.34)
            with self.assertRaises(ValueError):state.reserve('over-forecast',key,'forecast',.85)
            with self.assertRaises(ValueError):state.reserve('over-game',key,'search',1.2)
            with state.db() as c:c.execute('INSERT INTO requests VALUES(?,?,?,?,?)',('other-game','prior','forecast',49.82,'claimed'))
            with self.assertRaises(ValueError):state.reserve('over-global',key,'forecast',.01)
            self.assertAlmostEqual(state.renewal_plan()['reserved_usd'],49.998331)

    def test_migration_cannot_change_evidence_config_or_unknown_assets(self):
        original=json.loads(campaign.REGISTRY.read_text())
        for field in ['experiments/prospective_cloud_news_v1_assets.json','examples/prospective_github_actions_v1.json','new-unreviewed.py']:
            with tempfile.TemporaryDirectory() as tmp:
                changed=dict(original);changed[field]='0'*64;p=Path(tmp)/'assets.json';p.write_text(json.dumps(changed))
                with patch.object(campaign,'REGISTRY',p),self.assertRaises(ValueError):campaign.renewal_migration()

    def test_corrupt_history_scope_migration_and_missing_sequence_fail_closed(self):
        for field,value in [('previous_sha256','bad'),('max_games',30),('store_uuid','other'),('assets_sha256','unknown'),('operational_migration',None)]:
            with self.subTest(field=field),tempfile.TemporaryDirectory() as tmp:
                state,key,game,clock,objects,cp=legacy(Path(tmp));p=state.renewal_plan()
                state.renew(cloud.iso(clock[0]+86400),p['predecessor_sha256'],True,True)
                amendment=state.root/'campaign_amendments/0001.json';value_json=json.loads(amendment.read_text());value_json[field]=value
                amendment.write_text(json.dumps(value_json))
                with self.assertRaises(ValueError):state.campaign_history()
        with tempfile.TemporaryDirectory() as tmp:
            state,key,game,clock,objects,cp=legacy(Path(tmp));p=state.renewal_plan()
            state.renew(cloud.iso(clock[0]+86400),p['predecessor_sha256'],True,True)
            (state.root/'campaign_amendments/0001.json').rename(state.root/'campaign_amendments/0002.json')
            with self.assertRaises(ValueError):state.campaign_history()

    def test_native_replay_and_restore_preserve_prior_forecasts(self):
        with tempfile.TemporaryDirectory() as tmp:
            state,game,clock,objects,cp=setup(Path(tmp)/'first');key=approve(state,game,clock)
            engine=cloud.Engine(state,FixtureBackend(state),True)
            for phase in ('collect','refresh','target'):
                clock[0]=cloud.windows(game,state.config)[phase]+(1 if phase=='target' else 0);engine.advance(key)
            proof=cloud.replay_job(state,key);before=files(state.root)
            clock[0]+=86400;p=state.renewal_plan()
            state.renew(cloud.iso(clock[0]+86400),p['predecessor_sha256'],True)
            self.assertEqual({n:files(state.root)[n] for n in before},before)
            cp.close();new_cp=Checkpoints(objects,state.uuid);new_cp.open('renewal-restore');new_cp.restore(Path(tmp)/'restored')
            restored=campaign.CampaignState(Path(tmp)/'restored',state.config,new_cp,lambda:clock[0])
            self.assertEqual(cloud.replay_job(restored,key),proof);self.assertEqual(restored.uuid,state.uuid)
            self.assertEqual(restored.campaign()['max_games'],1)

    def test_read_only_plan_rejects_owner_and_unknown_registry(self):
        with tempfile.TemporaryDirectory() as tmp:
            state,key,game,clock,objects,cp=legacy(Path(tmp)/'first')
            with self.assertRaises(StorageStop):actions.renewal_plan(objects,state.uuid,Path(tmp)/'inspect',state.config)
            body=json.loads((state.root/'campaign.json').read_text());body['assets_sha256']='unknown'
            (state.root/'campaign.json').write_text(json.dumps(body));state.sync();cp.close()
            with self.assertRaises(ValueError):actions.renewal_plan(objects,state.uuid,Path(tmp)/'inspect',state.config)

    def test_workflow_modes_gated_without_paid_credentials_and_exclusive_cli(self):
        for mode in ('renew','renewal-plan'):
            env=dict(EVENT='workflow_dispatch',MODE=mode,REF='refs/heads/main',SHA='a'*40,REVIEWED_SHA='a'*40,ADMIN_FLAG='true',LIVE_FLAG='false')
            self.assertTrue(evaluate(env)['private_authorized']);env['ADMIN_FLAG']='false'
            self.assertFalse(evaluate(env)['private_authorized'])
        with patch.object(sys,'argv',['actions_prospective.py','--renew','--live']),self.assertRaises(SystemExit):actions.main()
        with patch.object(sys,'argv',['actions_prospective.py','--renew','--state','unused','--allow-network']),self.assertRaises(SystemExit):actions.main()
        workflow=(cloud.ROOT/'.github/workflows/prospective-nba.yml').read_text()
        for key in ('BRAVE_SEARCH_API_KEY','ANTHROPIC_API_KEY'):
            line=next(s for s in workflow.splitlines() if s.strip().startswith(key+':'))
            self.assertNotIn("inputs.mode == 'renew'",line);self.assertIn("inputs.mode == 'live'",line)


if __name__=='__main__':unittest.main()
