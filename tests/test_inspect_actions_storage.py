import json
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from inspect_actions_storage import inspect, sanitized
from evidence_documents import canonical,digest


class InspectionTests(unittest.TestCase):
    def fixture(self):
        data={};files={}
        def add(name,body):
            sha=digest(body);data['blobs/'+sha]=body;files[name]=sha
        add('events/failure.json',canonical({'kind':'stage_failed','stage':'2026-10-26','error_type':'ValueError','reason':'synthetic failure'}))
        add('jobs/catalog/2026-10-26/raw/source.json',canonical({'url':'https://cdn.nba.com/static/json/staticData/scheduleLeagueV2_1.json','http_status':403,'headers':{'sensitive':'do not show'},'source_id':'fixture'}))
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'state.sqlite'
            with sqlite3.connect(path) as db:
                db.executescript('CREATE TABLE stages(job,name,status);CREATE TABLE circuits(id,body);CREATE TABLE requests(kind);')
                db.execute("INSERT INTO stages VALUES('catalog','2026-10-26','failed')")
            db.close()
            add('state.sqlite',path.read_bytes())
        manifest=canonical({'files':files,'previous':None});sha=digest(manifest)
        data['snapshots/'+sha]=manifest
        data['root.json']=canonical({'store_uuid':'fixture-store','owner':{'run':'failed-run','nonce':'private-nonce'},'snapshot':sha})
        class ReadOnly:
            def read(self,key):return data.get(key),None
            def write(self,*a,**kw):raise AssertionError('Never mutate storage')
        return ReadOnly(),data

    def test_saved_failure_and_source_status_with_no_writes(self):
        objects,data=self.fixture();before=dict(data);result=inspect(objects,'fixture-store')
        self.assertEqual(data,before);self.assertEqual(result['owner_run'],'failed-run')
        self.assertEqual(result['stage_errors'][0]['reason'],'synthetic failure')
        self.assertEqual(result['source_requests'][0]['http_status'],403)
        self.assertNotIn('headers',json.dumps(result));self.assertNotIn('private-nonce',json.dumps(result))
        self.assertEqual(result['paid_claim_count'],0)

    def test_mismatch_and_corrupt_checkpoint_fail_closed(self):
        objects,data=self.fixture()
        with self.assertRaises(ValueError):inspect(objects,'wrong-store')
        key=next(k for k in data if k.startswith('snapshots/'));data[key]=b'changed'
        with self.assertRaises(ValueError):inspect(objects,'fixture-store')

    def test_secrets_and_raw_headers_not_printed(self):
        result=sanitized({'reason':'bucketname secretvalue sk-ant-example-key'},
                         {'NBA_ACTIONS_BUCKET':'bucketname','AWS_SECRET_ACCESS_KEY':'secretvalue'})
        self.assertEqual(result,{'reason':'[redacted] [redacted] [redacted]'})


if __name__=='__main__':unittest.main()
