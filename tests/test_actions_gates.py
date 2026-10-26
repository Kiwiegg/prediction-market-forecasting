import contextlib
import io
import json
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from actions_gates import evaluate, main


class GateTests(unittest.TestCase):
    def env(self,**changes):
        return dict(EVENT='workflow_dispatch',MODE='bootstrap',REF='refs/heads/main',
                    SHA='a'*40,REVIEWED_SHA='a'*40,ADMIN_FLAG='true',LIVE_FLAG='false',**changes)

    def test_bootstrap_discover_and_whitespace_admin_authorized_without_live(self):
        for mode in ('bootstrap','discover'):
            env=self.env();env.update(MODE=mode,ADMIN_FLAG='true\r\n')
            result=evaluate(env)
            self.assertTrue(result['private_authorized']);self.assertTrue(result['admin_flag_has_whitespace'])
            self.assertFalse(result['live_enabled']);self.assertFalse(result['live_mode'])

    def test_missing_false_and_noncanonical_flags_fail_closed(self):
        for flag in ('','false',' false\n','1','yes','true false'):
            env=self.env();env['ADMIN_FLAG']=flag
            self.assertFalse(evaluate(env)['private_authorized'])

    def test_sha_remains_exact_full_and_main_only(self):
        for key,value in (('REVIEWED_SHA','a'*7),('REVIEWED_SHA','a'*40+'\n'),('SHA','b'*40),('REF','refs/heads/test')):
            env=self.env();env[key]=value
            self.assertFalse(evaluate(env)['private_authorized'])

    def test_admin_flag_never_authorizes_live_schedule_dry_run_or_unknown(self):
        for event,mode in (('workflow_dispatch','live'),('schedule',''),('workflow_dispatch','dry-run'),('workflow_dispatch','unknown')):
            env=self.env();env.update(EVENT=event,MODE=mode)
            self.assertFalse(evaluate(env)['private_authorized'])
        env=self.env();env.update(MODE='live',LIVE_FLAG='true\n')
        self.assertTrue(evaluate(env)['private_authorized'])

    def test_diagnostics_only_print_boolean_allowlist(self):
        env=self.env();env.update(ANTHROPIC_API_KEY='synthetic-secret',GITHUB_CONTEXT='sensitive-context')
        out=io.StringIO()
        with patch.dict(os.environ,env,clear=True),contextlib.redirect_stdout(out):main()
        result=json.loads(out.getvalue())
        self.assertTrue(all(type(v) is bool for v in result.values()))
        self.assertNotIn('synthetic-secret',out.getvalue());self.assertNotIn('sensitive-context',out.getvalue())


if __name__=='__main__':unittest.main()
