import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from audit_live_pilot import ReadOnlyState,audit
from test_cloud_news_pipeline import simulate
from evidence_documents import digest


class AuditTests(unittest.TestCase):
    def test_private_replay_report_reads_each_method_without_mutation(self):
        with tempfile.TemporaryDirectory() as tmp:
            state,key,clock,backend,proof=simulate(Path(tmp)/'state')
            # The plain cloud fixture has no campaign approval or paid ledger.
            (state.root/'campaign.json').write_text(json.dumps({'authorized_at_utc':'2026-01-01T00:00:00Z','expires_at_utc':'2027-01-01T00:00:00Z'}))
            before={str(p.relative_to(state.root)):digest(p.read_bytes()) for p in state.root.rglob('*') if p.is_file() and not p.name.endswith(('-wal','-shm','.lock'))}
            ro=ReadOnlyState(state.root,state.config)
            with patch('urllib.request.OpenerDirector.open',side_effect=AssertionError('Audit must not use network')):
                result=audit(ro,key)
            after={n:digest((state.root/n).read_bytes()) for n in before}
            self.assertEqual(before,after)
            self.assertTrue(result['checks']['private_replay']);self.assertTrue(result['checks']['all_three_methods_successful'])
            self.assertFalse(result['checks']['primary_pair_eligible'])
            self.assertEqual({m['parent_hash'] for m in result['methods'].values()},{result['packet_sha256']})
            self.assertFalse(result['raw_provider_responses_included']);self.assertIsNone(result['brier_score'])
            self.assertFalse(result['market']['eligible']);self.assertIsNone(result['market']['midpoint'])

    def test_read_only_sql_connection_refuses_changes(self):
        with tempfile.TemporaryDirectory() as tmp:
            state,key,clock,backend,proof=simulate(Path(tmp)/'state')
            ro=ReadOnlyState(state.root,state.config)
            with ro.db() as c:
                with self.assertRaises(Exception):c.execute("DELETE FROM requests")

    def test_workflow_has_only_storage_credentials_and_sanitized_artifact(self):
        workflow=(Path(__file__).resolve().parents[1]/'.github/workflows/audit-nba-pilot.yml').read_text()
        self.assertNotIn('BRAVE_SEARCH_API_KEY',workflow);self.assertNotIn('ANTHROPIC_API_KEY',workflow)
        self.assertNotIn('mode=live',workflow);self.assertIn('sanitized-pilot-audit/audit.json',workflow)
        self.assertNotIn('captures/',workflow);self.assertIn("github.sha == vars.NBA_ACTIONS_REVIEWED_SHA",workflow)


if __name__=='__main__':unittest.main()
