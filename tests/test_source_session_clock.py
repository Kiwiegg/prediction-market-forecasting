import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock,patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import cloud_prospective as cloud
import actions_prospective as actions
import inspect_actions_storage as audit
from evidence_documents import canonical,digest
from test_prospective_discovery import Response
import test_inspect_actions_storage as inspection_fixtures


class SourceClockTests(unittest.TestCase):
    def test_real_session_constructor_and_one_shot_transport_share_state_clock(self):
        with tempfile.TemporaryDirectory() as tmp:
            now=[100.0]
            state=SimpleNamespace(root=Path(tmp),clock=lambda:now[0],check_circuit=lambda key:None)
            with patch('urllib.request.OpenerDirector.open',side_effect=AssertionError('No live network')):
                session=cloud.CloudSession(Path(tmp)/'raw',state,'catalog:fixture','discovery',120)
                target=cloud.TargetSession(Path(tmp)/'target',state,'fixture','baseline',120)
                self.assertIsNone(session.target_id);self.assertIsNone(target.target_id)
                self.assertIs(session.store.clock,state.clock)
                self.assertEqual(cloud.SourceBudget(state,'fixture').clock(),100)
                now[0]=101
                opener=Mock();opener.open.return_value=Response({'leagueSchedule':{'gameDates':[]}})
                session.store.opener=opener
                meta,body=session.json(cloud.discovery.NBA_SCHEDULES[0])
                self.assertEqual(meta['http_status'],200);self.assertEqual(body,{'leagueSchedule':{'gameDates':[]}})
                self.assertEqual(cloud.native.aware(meta['retrieved_at_utc']),101)

    def test_recovery_only_exact_audited_zero_request_failure(self):
        objects,data=inspection_fixtures.InspectionTests().fixture()
        root=json.loads(data['root.json']);root['owner']['run']=audit.CLOCK_FAILURE_RUN
        data['root.json']=canonical(root)
        manifest=json.loads(data['snapshots/'+root['snapshot']])
        # Replace synthetic failure with the audited exception; fixtures never
        # mutate the production allowlist or perform remote requests.
        old=manifest['files']['events/failure.json']
        value=json.loads(data['blobs/'+old]);value['reason']="'SourceBudget' object has no attribute 'clock'";value['error_type']='AttributeError'
        new=canonical(value);sha=digest(new);data['blobs/'+sha]=new;manifest['files']['events/failure.json']=sha
        del manifest['files']['jobs/catalog/2026-10-26/raw/source.json']
        body=canonical(manifest);sha=digest(body);data['snapshots/'+sha]=body;root['snapshot']=sha;data['root.json']=canonical(root)
        with patch.object(audit,'CLOCK_FAILURE_SNAPSHOT',sha):
            self.assertEqual(audit.clock_repair_owner(objects,'fixture-store'),root['owner'])
            valid=audit.inspect(objects,'fixture-store')
            for key,value in (('paid_claim_count',1),('circuits',[{'id':'paid'}]),('source_requests',[{'http_status':403}])):
                with patch.object(audit,'inspect',return_value={**valid,key:value}):
                    with self.assertRaises(ValueError):audit.clock_repair_owner(objects,'fixture-store')
            root['owner']['run']='another-run';data['root.json']=canonical(root)
            with self.assertRaises(ValueError):audit.clock_repair_owner(objects,'fixture-store')
        with self.assertRaises(ValueError):audit.clock_repair_owner(objects,'fixture-store')

    def test_completed_repair_catalog_reused_without_source_requests(self):
        state=Mock();state.clock.return_value=cloud.native.aware('2026-10-26T13:00:00Z')
        state.has.return_value=True;state.artifact.return_value={'games':[],'decisions':[]}
        result=actions.catalog(state)
        state.artifact.assert_called_once_with('catalog','2026-10-26-clock-v1')
        state.stage.assert_not_called();self.assertEqual(result['games'],[])
        state.artifact.side_effect=ValueError('failed or uncertain')
        with self.assertRaises(ValueError):actions.catalog(state)
        state.stage.assert_not_called()

    def test_original_public_capture_replay_keeps_original_hash(self):
        root=cloud.ROOT/'reports/prospective_cloud_news_v1/simulation'
        before=(root/'audit.json').read_bytes()
        self.assertTrue(cloud.replay_public(root)['verified'])
        self.assertEqual((root/'audit.json').read_bytes(),before)


if __name__=='__main__':unittest.main()
