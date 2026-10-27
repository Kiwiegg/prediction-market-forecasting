import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from replay_live_pilot_summary import verify


FOLDER = Path(__file__).resolve().parents[1] / 'reports/prospective_live_pilot_1'


class PublicSummaryTests(unittest.TestCase):
    def test_saved_summary_replays_without_network(self):
        from unittest.mock import patch
        with patch('urllib.request.OpenerDirector.open', side_effect=AssertionError('Offline only')):
            self.assertTrue(verify(FOLDER)['verified'])

    def test_corrupt_hash_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp)
            (p / 'manifest.json').write_bytes((FOLDER / 'manifest.json').read_bytes())
            (p / 'audit.json').write_bytes((FOLDER / 'audit.json').read_bytes() + b' ')
            with self.assertRaisesRegex(ValueError, 'hash mismatch'): verify(p)

    def test_arithmetic_timing_tokens_and_pending_outcome_checked(self):
        changes = [
            lambda a: a['methods']['v2']['probabilities'].update(leap_v2_raw=.1),
            lambda a: a.update(sealed_at_utc='2026-10-26T23:46:00Z'),
            lambda a: a['costs']['forecast_tokens'].update(input_tokens=1),
            lambda a: a.update(outcome_verified=True),
            lambda a: a['methods']['v1'].update(parent_hash='different'),
            lambda a: a['market'].update(retrieved_at_utc='2026-10-26T23:30:01Z'),
        ]
        for change in changes:
            with self.subTest(change=changes.index(change)), tempfile.TemporaryDirectory() as tmp:
                a=json.loads((FOLDER / 'audit.json').read_text());change(a)
                payload=json.dumps(a).encode();m=json.loads((FOLDER / 'manifest.json').read_text())
                m['audit_sha256']=hashlib.sha256(payload).hexdigest()
                (Path(tmp) / 'audit.json').write_bytes(payload)
                (Path(tmp) / 'manifest.json').write_text(json.dumps(m))
                with self.assertRaises(ValueError): verify(tmp)


if __name__ == '__main__': unittest.main()
