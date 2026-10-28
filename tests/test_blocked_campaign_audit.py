import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from audit_blocked_campaign import audit,termination_proof,FAILED_COMMIT,public_response_path
from audit_live_pilot import ReadOnlyState
from test_cloud_news_pipeline import simulate
from evidence_documents import digest


class BlockedAuditTests(unittest.TestCase):
    def test_benchmark_revalidation_claim_matches_independent_market_capture(self):
        from types import SimpleNamespace
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);state=SimpleNamespace(root=root,job_dir=lambda j:root/'jobs'/j)
            rec={'job':'pilot','slot':'market_revalidation','url':'https://example.invalid/schedule'}
            # MarketEngine.capture stores revalidation bytes in market/raw,
            # although the immutable claim deliberately has a different slot.
            meta=root/'jobs/pilot/market/raw'/(digest(rec['url'].encode())+'.json')
            meta.parent.mkdir(parents=True);meta.write_text('{}')
            self.assertTrue(public_response_path(state,rec).exists())

    def test_only_exact_completed_failed_runner_proves_termination(self):
        proof={'id':40600612996,'status':'completed','conclusion':'failure','run_attempt':1,'head_sha':FAILED_COMMIT}
        self.assertEqual(termination_proof(proof),proof)
        for k,v in [('status','in_progress'),('head_sha','changed'),('run_attempt',2)]:
            with self.subTest(k=k),self.assertRaises(ValueError):termination_proof({**proof,k:v})

    def test_mock_capture_replays_read_only_without_provider_calls(self):
        with tempfile.TemporaryDirectory() as tmp:
            state,key,clock,backend,proof=simulate(Path(tmp)/'state')
            before={str(p.relative_to(state.root)):digest(p.read_bytes()) for p in state.root.rglob('*') if p.is_file() and not p.name.endswith(('-wal','-shm','.lock'))}
            with patch('urllib.request.OpenerDirector.open',side_effect=AssertionError('No network')):
                # The mock stores synthetic provider captures without paid claims.
                # Do not mislabel those as reconciled real requests.
                with self.assertRaisesRegex(ValueError,'Unaccounted paid-provider'):
                    audit(ReadOnlyState(state.root,state.config))
            self.assertEqual({n:digest((state.root/n).read_bytes()) for n in before},before)


if __name__=='__main__':unittest.main()
