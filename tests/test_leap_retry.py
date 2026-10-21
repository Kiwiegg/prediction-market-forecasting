import io
import json
import os
import sys
import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts"))
import leap_forecast as leap
from evidence_documents import digest
from forecast_split import DEFAULT_DATA,DEFAULT_SPLIT
from retry_leap import retry_plan,run_retries,verify_retry,merge_successes
from test_leap_forecast import CONFIG,Response,reply,factory


def denied():
    return urllib.error.HTTPError("https://api.anthropic.com/v1/messages",403,"Forbidden",{},
        io.BytesIO(b'{"error":{"type":"forbidden","message":"Request not allowed"}}'))


class RetryTests(unittest.TestCase):
    def original(self,root,failures=1):
        plan,specs=leap.plan_experiment(DEFAULT_DATA,DEFAULT_SPLIT,CONFIG,limit=1)
        opener=Mock();opener.open.side_effect=[denied() for _ in range(failures)]+[Response(reply()) for _ in range(3-failures)]
        leap.run_experiment(plan,specs,root/"original",root/"original_cache",3,1,True,factory(opener))
        return {str(p):digest(p.read_bytes()) for parent in (root/"original",root/"original_cache") for p in parent.rglob("*") if p.is_file()}

    def test_only_failed_requests_retried_and_successful_merge_preserves_originals(self):
        with tempfile.TemporaryDirectory() as tmp,patch.dict(os.environ,{"ANTHROPIC_API_KEY":"fixture-key"}):
            root=Path(tmp);before=self.original(root)
            identity,_,_,_,failed=retry_plan(root/"original")
            self.assertEqual(len(failed),1)
            opener=Mock();opener.open.return_value=Response(reply(1.7))
            result=run_retries(root/"original",root/"retry",True,1,.1,registry=root/"registry",transport_factory=factory(opener),delay_seconds=0)
            self.assertEqual(result["successful"],1);self.assertEqual(opener.open.call_count,1)
            self.assertEqual(run_retries(root/"original",root/"retry",True,1,.1,registry=root/"registry",transport_factory=factory(opener),delay_seconds=0),result)
            self.assertEqual(opener.open.call_count,1)
            with patch("urllib.request.OpenerDirector.open",side_effect=AssertionError("Merge and verification are offline")):
                merged=merge_successes(root/"original",root/"retry",root/"merged",root/"merged_cache")
                verify_retry(root/"original",root/"retry")
            self.assertEqual(merged["successful_forecasts"],1)
            original=leap.load_experiment(root/"original")[1][0]
            final=leap.load_experiment(root/"merged")[1][0]
            self.assertEqual(final["groups"][0]["likelihood_ratio"],1.7)
            self.assertEqual(final["groups"][1:],original["groups"][1:])
            self.assertEqual(before,{p:digest(Path(p).read_bytes()) for p in before})
            self.assertEqual(merge_successes(root/"original",root/"retry",root/"merged",root/"merged_cache"),merged)

    def test_recurrent_denial_stops_without_retrying_again_or_substituting_neutral(self):
        with tempfile.TemporaryDirectory() as tmp,patch.dict(os.environ,{"ANTHROPIC_API_KEY":"fixture-key"}):
            root=Path(tmp);self.original(root,2)
            opener=Mock();opener.open.side_effect=denied()
            result=run_retries(root/"original",root/"retry",True,2,.2,registry=root/"registry",transport_factory=factory(opener),delay_seconds=0)
            self.assertEqual((result["attempted"],result["failed"],result["not_attempted_after_stop"]),(1,1,1))
            self.assertEqual(opener.open.call_count,1)
            merge_successes(root/"original",root/"retry",root/"merged",root/"merged_cache")
            self.assertEqual(leap.load_experiment(root/"merged")[1],leap.load_experiment(root/"original")[1])

    def test_authorization_budget_and_third_attempt_protection(self):
        with tempfile.TemporaryDirectory() as tmp,patch.dict(os.environ,{"ANTHROPIC_API_KEY":"fixture-key"}):
            root=Path(tmp);self.original(root)
            opener=Mock();opener.open.return_value=Response(reply())
            kwargs={"registry":root/"registry","transport_factory":factory(opener),"delay_seconds":0}
            for allow,calls,cost in ((False,1,.1),(True,0,.1),(True,1,0)):
                with self.assertRaises(ValueError):run_retries(root/"original",root/"retry",allow,calls,cost,**kwargs)
            opener.open.assert_not_called()
            run_retries(root/"original",root/"retry",True,1,.1,**kwargs)
            with self.assertRaises(ValueError):run_retries(root/"original",root/"another_retry",True,1,.1,**kwargs)
            self.assertEqual(opener.open.call_count,1)

    def test_reserved_retries_rejected_before_loading_probabilities(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/"run.json").write_text(json.dumps({"subset":"evaluation"}))
            with patch("retry_leap.leap.verify_experiment",side_effect=AssertionError("Reserved records opened")):
                with self.assertRaises(ValueError):retry_plan(root)


if __name__=="__main__":unittest.main()
