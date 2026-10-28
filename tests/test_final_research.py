"""Publication arithmetic and append-only postgame reporting, never paid inference."""
import copy
import csv
import json
import math
import os
import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch
from zoneinfo import ZoneInfo

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import build_final_research as paper
import update_final_prospective as update


def pilot():
    return update.summarize_audit(json.loads((paper.ROOT/'reports/prospective_live_pilot_1/audit.json').read_text()))


class FinalResearchTests(unittest.TestCase):
    def test_historical_sources_pinned_and_paired_denominators_preserved(self):
        with patch('urllib.request.OpenerDirector.open',side_effect=AssertionError('No network')):
            d=paper.assemble(paper.FINAL/'prospective_update_2026_10_28')
        ns={r['cohort']:r['n'] for r in d['scores']}
        self.assertEqual(ns,{'Development A':50,'Development B':40,'Held-out primary':143,'Held-out A':143,'Held-out B':139})
        scores={r['method']:r for r in d['scores'] if r['cohort']=='Held-out primary'}
        difference=scores['leap_v2_raw']['brier_score']-scores['direct']['brier_score']
        self.assertAlmostEqual(difference,.011818688248620765)
        primary=next(r for r in d['intervals'] if r['cohort']=='primary')
        self.assertEqual(primary['n'],143);self.assertEqual(primary['resamples'],10000)
        self.assertEqual(d['prospective_counts'],{'enrolled':7,'eligible':1,'scored':0})

    def test_tables_rebuild_without_source_or_model_access_and_detect_tampering(self):
        with tempfile.TemporaryDirectory() as t,patch('urllib.request.OpenerDirector.open',side_effect=AssertionError('No network')):
            path=Path(t);paper.build(path,draw=False)
            self.assertTrue(paper.verify_generated(path)['verified'])
            rows=list(csv.DictReader((path/'tables/scores.csv').read_text().splitlines()))
            self.assertEqual(len(rows),26)
            self.assertIn('0.011819',(path/'paper.md').read_text())
            self.assertIn('$$',(path/'paper.md').read_text())
            (path/'tables/scores.csv').write_text('changed')
            with self.assertRaisesRegex(ValueError,'artifact changed'):paper.verify_generated(path)

    def test_no_outcome_does_not_silently_become_loss_or_zero_score(self):
        row=pilot();summary=update.score_rows([row]);cohort=next(iter(summary.values()))
        self.assertEqual(cohort['pending_outcomes'],1)
        primary=cohort['comparisons']['primary']
        self.assertEqual(primary['n'],0);self.assertIsNone(primary['v2_minus_direct_brier'])
        self.assertIsNone(primary['methods']['direct']['brier_score'])

    def test_market_and_v1_missingness_do_not_change_primary_intersection(self):
        row=pilot();row.update(outcome=1,outcome_verification={'source_replayed':True})
        row['probabilities']['kalshi']=None;row['probabilities']['leap_v1_raw']=None
        c=next(iter(update.score_rows([row]).values()))['comparisons']
        self.assertEqual(c['primary']['n'],1);self.assertEqual(c['market']['n'],0);self.assertEqual(c['seven_method']['n'],0)
        self.assertAlmostEqual(c['primary']['methods']['direct']['brier_score'],(.92-1)**2)
        self.assertAlmostEqual(c['primary']['methods']['direct']['log_loss'],-math.log(.92))

    def test_dst_and_fixed_exclusive_reporting_boundary(self):
        end=datetime.fromisoformat(update.protocol()['capture_cutoff_exclusive_utc'].replace('Z','+00:00'))
        self.assertEqual(end.astimezone(ZoneInfo('America/New_York')).isoformat(),'2026-11-03T00:00:00-05:00')
        with self.assertRaises(ValueError):update.clock('2026-11-02T00:00:00')
        row=pilot();t=update.clock(row['cutoff_utc'])
        for offset in (300,301):
            r=copy.deepcopy(row);r['frozen_at_utc']=datetime.fromtimestamp(t+offset,ZoneInfo('UTC')).isoformat()
            r['sealed_at_utc']=datetime.fromtimestamp(t+400,ZoneInfo('UTC')).isoformat()
            if offset==300:update.validate_rows([r])
            else:
                with self.assertRaises(ValueError):update.validate_rows([r])
        for offset in (900,901):
            r=copy.deepcopy(row);r['sealed_at_utc']=datetime.fromtimestamp(t+offset,ZoneInfo('UTC')).isoformat()
            if offset==900:update.validate_rows([r])
            else:
                with self.assertRaises(ValueError):update.validate_rows([r])
        r=copy.deepcopy(row);r['cutoff_utc']='2026-11-03T04:59:00Z';r['game']['recorded_start_utc']='2026-11-04T04:59:00Z'
        r['frozen_at_utc']='2026-11-03T04:59:01Z';r['sealed_at_utc']='2026-11-03T05:00:00Z'
        with self.assertRaises(ValueError):update.validate_rows([r])

    def test_audit_future_retrieval_failed_primary_and_parent_hash_rejected(self):
        original=json.loads((paper.ROOT/'reports/prospective_live_pilot_1/audit.json').read_text())
        for check in ('source_retrievals_by_cutoff','primary_pair_eligible','same_packet_all_methods'):
            a=copy.deepcopy(original);a['checks'][check]=False
            self.assertFalse(update.summarize_audit(a)['primary_eligible'])
        a=copy.deepcopy(original);a['methods']['direct']['parent_hash']='bad'
        with self.assertRaises(ValueError):update.summarize_audit(a)
        a=copy.deepcopy(original);a['methods']['direct']['probabilities']['direct']=True
        with self.assertRaises(ValueError):update.summarize_audit(a)
        a=copy.deepcopy(original);a['methods']['v1']['status']='failed';a['checks']['all_three_methods_successful']=False
        r=update.summarize_audit(a);self.assertTrue(r['primary_eligible']);self.assertIsNone(r['probabilities']['leap_v1_raw'])

    def test_append_only_forecasts_and_no_failed_capture_rescue(self):
        with tempfile.TemporaryDirectory() as t:
            base=Path(t)/'original';row=pilot();update.save_bundle([row],base)
            with self.assertRaises(FileExistsError):update.save_bundle([row],base)
            changed=copy.deepcopy(row);changed['probabilities']['direct']=.1
            with self.assertRaises(ValueError):update.save_bundle([changed],Path(t)/'changed',base)
            with self.assertRaises(ValueError):update.save_bundle([],Path(t)/'removed',base)
            invalid=copy.deepcopy(row);invalid.update(primary_eligible=False,exclusion_reason='provider_failure')
            failed=Path(t)/'failed';update.save_bundle([invalid],failed)
            with self.assertRaises(ValueError):update.save_bundle([row],Path(t)/'rescued',failed)

    def test_verified_outcomes_append_but_never_replace_verified_result(self):
        with tempfile.TemporaryDirectory() as t:
            row=pilot();base=Path(t)/'before';update.save_bundle([row],base)
            verified=copy.deepcopy(row);verified.update(outcome=1,outcome_verification={'source_replayed':True,'capture_manifest_sha256':'fixture'})
            after=Path(t)/'after';result=update.save_bundle([verified],after,base)
            self.assertEqual(result['rows'][0]['probabilities'],row['probabilities'])
            self.assertEqual(result['previous_manifest_sha256'],paper.sha(base/'manifest.json'))
            changed=copy.deepcopy(verified);changed['outcome']=0
            with self.assertRaises(ValueError):update.save_bundle([changed],Path(t)/'replaced',after)
            bad=copy.deepcopy(row);bad['outcome']=True
            with self.assertRaises(ValueError):update.save_bundle([bad],Path(t)/'bad')

    def test_reauditing_campaign_state_does_not_change_or_block_existing_forecast(self):
        with tempfile.TemporaryDirectory() as t:
            row=pilot();base=Path(t)/'before';update.save_bundle([row],base)
            fresh=copy.deepcopy(row);fresh['source_audit_sha256']='new-readonly-attestation'
            after=Path(t)/'after';update.save_bundle([fresh],after,base)
            self.assertEqual(update.verify_bundle(after)['rows'][0]['probabilities'],row['probabilities'])

    def test_separate_operational_policy_strata_not_silently_pooled(self):
        row=pilot();new=copy.deepcopy(row);new['game_id']='fixture';new['operational_amendment']='prospective_news_denial_v1'
        self.assertEqual(len(update.score_rows([row,new])),2)

    def test_outcome_join_requires_existing_raw_capture_verification_and_exact_fixture(self):
        row=pilot();out={'game_id':row['game_id'],'game':row['game'],'eligible':True,'reason':None,'outcome':1,'retrieved_at_utc':'2026-10-28T01:00:00Z'}
        with tempfile.TemporaryDirectory() as t:
            (Path(t)/'manifest.json').write_text('{}')
            with patch('prospective_evaluate.verify_source_capture',return_value=out) as check:
                r=update.join_outcome(row,t);self.assertEqual(r['outcome'],1);check.assert_called_once_with(t,'outcome')
            bad={**out,'game_id':'different'}
            with patch('prospective_evaluate.verify_source_capture',return_value=bad):
                with self.assertRaises(ValueError):update.join_outcome(row,t)
            bad={**out,'game':{**out['game'],'recorded_start_utc':'2026-10-28T23:30:00Z'}}
            with patch('prospective_evaluate.verify_source_capture',return_value=bad):
                with self.assertRaises(ValueError):update.join_outcome(row,t)
            with patch('prospective_evaluate.verify_source_capture',side_effect=ValueError('raw hash changed')):
                with self.assertRaises(ValueError):update.join_outcome(row,t)

    def test_r2_reporting_is_get_only_and_requires_stable_idle_original_store(self):
        root={'store_uuid':'fixture-store','owner':None,'snapshot':'fixture-snapshot'}
        class Objects:
            def __init__(self,*a):self.calls=0
            def read(self,key):
                self.calls+=1
                return json.dumps(root).encode(), 'etag'
            def write(self,*a,**k):raise AssertionError('Report cannot mutate R2')
        class Checkpoint:
            def __init__(self,*a):self.files={'saved':update.digest(b'original')}
            def restore(self,path):path.mkdir();(path/'saved').write_bytes(b'original')
        with patch.dict(os.environ,{'NBA_ACTIONS_STORE_UUID':'fixture-store'}),patch('actions_storage.S3Objects',Objects),patch('actions_storage.Checkpoints',Checkpoint),patch.object(update,'collect',return_value=[pilot()]):
            self.assertEqual(len(update.collect_r2()),1)
            root['owner']='active-worker'
            with self.assertRaisesRegex(ValueError,'idle'):update.collect_r2()
            root['owner']=None;root['store_uuid']='different'
            with self.assertRaisesRegex(ValueError,'idle'):update.collect_r2()

    def test_snapshot_hash_and_duplicate_observation_rejection(self):
        with tempfile.TemporaryDirectory() as t:
            p=Path(t)/'snapshot';row=pilot()
            with self.assertRaises(ValueError):update.save_bundle([row,row],p)
            update.save_bundle([row],p)
            (p/'observations.json').write_text('{}')
            with self.assertRaisesRegex(ValueError,'integrity'):update.verify_bundle(p)


if __name__=='__main__':unittest.main()
